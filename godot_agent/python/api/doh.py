# -*- coding: utf-8 -*-
"""DNS over HTTPS (DoH) для запросов к провайдерам API.

ЗАЧЕМ. Если провайдер (например openrouter.ai) не разрешается системным DNS —
интернет-провайдер отдаёт NXDOMAIN или подменённый адрес, — обычный запрос
падает ещё до соединения. DoH спрашивает адрес у доверенного сервера по HTTPS,
и такую подмену обойти нельзя.

ЧЕСТНО О ГРАНИЦАХ. DoH меняет ТОЛЬКО разрешение имени. Он помогает, когда
блокировка сделана на уровне DNS. Если сервис блокируется по IP-адресу или по
имени в TLS-рукопожатии (SNI), DoH не поможет — там нужен прокси или VPN.
Обещать «DoH обходит любые блокировки» было бы неправдой.

КАК ЭТО РАБОТАЕТ. Подменяется socket.getaddrinfo: имя разрешается через DoH, а
дальше всё идёт как обычно. Важное следствие — TLS не ломается: urllib
подставляет в рукопожатие ИСХОДНОЕ имя хоста (SNI) и проверяет сертификат по
нему, меняется только адрес, куда идёт соединение. Проверка сертификатов
остаётся включённой.

ЧТО НЕ ТРОГАЕТСЯ. Локальные адреса (127.0.0.1, localhost, ::1) через DoH не
разрешаются никогда: там работает свой сервер, будущий llama-server и порт
отладки браузера. Сам DoH-сервер тоже разрешается системным резолвером —
иначе получилась бы рекурсия.

ФОРМАТ. Реализован RFC 8484 (POST, application/dns-message) — он обязателен
для любого DoH-сервера. JSON-API (dns-json) поддерживают не все, поэтому он
здесь не используется.
"""
import os
import socket
import struct
import threading
import time
import urllib.request

# Настройки резолвера. Заполняются из api_keys через configure().
_cfg = {"enabled": False, "url": ""}

# Кэш: host -> (список_адресов, время_истечения).
_cache = {}
_cache_lock = threading.Lock()

# Пока идёт сам DoH-запрос, подменённый резолвер обязан молчать: адрес
# DoH-сервера разрешается системой. Флаг на поток, а не глобальный, чтобы
# параллельные запросы не глушили резолвер друг у друга.
_busy = threading.local()

_orig_getaddrinfo = None
_install_lock = threading.Lock()

DEFAULT_TTL = 300
MIN_TTL = 30
MAX_TTL = 3600
TIMEOUT = 8.0

_LOCAL = ("localhost", "::1", "0.0.0.0")


def configure(enabled, url):
    """Включает/выключает DoH и задаёт адрес сервера. Смена адреса сбрасывает
    кэш: иначе остались бы адреса, полученные от прежнего резолвера."""
    url = str(url or "").strip()
    changed = (bool(enabled) != _cfg["enabled"]) or (url != _cfg["url"])
    _cfg["enabled"] = bool(enabled) and bool(url)
    _cfg["url"] = url
    if changed:
        clear_cache()
        if _cfg["enabled"]:
            install()
    return _cfg["enabled"]


def is_enabled():
    return bool(_cfg["enabled"] and _cfg["url"])


def clear_cache():
    with _cache_lock:
        _cache.clear()


def validate_url(raw):
    """Проверяет адрес DoH-сервера. Возвращает (url, ошибка).

    Требуем https: DoH по обычному http бессмысленен — подменить ответ сможет
    тот же, кто подменял DNS.
    """
    s = str(raw or "").strip()
    if not s:
        return "", ""
    if "://" not in s:
        # Частый ввод «dns.example.com/dns-query» — дополняем схему сами.
        s = "https://" + s
    scheme, rest = s.split("://", 1)
    if scheme.lower() != "https":
        return "", (u"адрес DoH должен начинаться с https:// (по http подмену "
                    u"ответа никто не помешает сделать)")
    if not rest or rest.startswith("/"):
        return "", u"в адресе DoH не указан хост"
    host = rest.split("/", 1)[0]
    if " " in rest:
        return "", u"в адресе DoH не может быть пробелов"
    if "." not in host and not host.startswith("["):
        return "", u"похоже, это не адрес сервера: %s" % host
    return "https://" + rest, ""


def doh_host():
    """Хост самого DoH-сервера — его нельзя разрешать через себя же."""
    url = _cfg["url"]
    if "://" not in url:
        return ""
    return url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0].lower()


# ---------------------------------------------------------------------------
# Разбор DNS-пакетов (RFC 1035)
# ---------------------------------------------------------------------------

def _build_query(host, qtype=1):
    """Минимальный DNS-запрос: один вопрос, рекурсия разрешена."""
    header = struct.pack(">HHHHHH",
                         int.from_bytes(os.urandom(2), "big"),  # ID
                         0x0100,  # flags: RD
                         1, 0, 0, 0)
    qname = b""
    for label in host.rstrip(".").split("."):
        try:
            raw = label.encode("idna") if any(ord(c) > 127 for c in label) \
                else label.encode("ascii")
        except Exception:
            raise ValueError("недопустимое имя хоста: %s" % host)
        if not raw or len(raw) > 63:
            raise ValueError("недопустимая метка в имени: %s" % host)
        qname += bytes([len(raw)]) + raw
    return header + qname + b"\x00" + struct.pack(">HH", qtype, 1)


def _skip_name(data, i):
    """Пропускает доменное имя, учитывая сжатие указателем (RFC 1035, 4.1.4)."""
    while True:
        if i >= len(data):
            raise ValueError("ответ DNS обрезан")
        length = data[i]
        if length == 0:
            return i + 1
        if length & 0xC0 == 0xC0:
            return i + 2  # указатель — дальше имя не продолжается
        i += 1 + length


def parse_answer(data, want_type=1):
    """Адреса и TTL из ответа DNS. Возвращает (список_адресов, ttl)."""
    if len(data) < 12:
        raise ValueError("слишком короткий ответ DNS")
    rcode = data[3] & 0x0F
    if rcode != 0:
        names = {1: "ошибка формата", 2: "сбой сервера", 3: "имя не найдено",
                 4: "не поддерживается", 5: "отказано"}
        raise ValueError("DNS ответил кодом %d (%s)"
                         % (rcode, names.get(rcode, "неизвестно")))
    qd, an = struct.unpack(">H", data[4:6])[0], struct.unpack(">H", data[6:8])[0]
    i = 12
    for _ in range(qd):
        i = _skip_name(data, i) + 4  # + QTYPE и QCLASS
    ips, ttls = [], []
    for _ in range(an):
        i = _skip_name(data, i)
        if i + 10 > len(data):
            raise ValueError("ответ DNS обрезан")
        rtype, rclass, ttl, rdlen = struct.unpack(">HHIH", data[i:i + 10])
        i += 10
        rdata = data[i:i + rdlen]
        i += rdlen
        if rtype == want_type and rclass == 1 and len(rdata) == 4:
            ips.append(".".join(str(b) for b in rdata))
            ttls.append(ttl)
    ttl = min(ttls) if ttls else DEFAULT_TTL
    return ips, max(MIN_TTL, min(MAX_TTL, ttl))


# ---------------------------------------------------------------------------
# Запрос к DoH-серверу
# ---------------------------------------------------------------------------

def query(host, url=None, timeout=TIMEOUT):
    """Спрашивает адреса host у DoH-сервера. Бросает исключение при неудаче."""
    endpoint = url or _cfg["url"]
    if not endpoint:
        raise ValueError("адрес DoH-сервера не задан")
    payload = _build_query(host)
    req = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={"Content-Type": "application/dns-message",
                 "Accept": "application/dns-message",
                 "User-Agent": "GodotAgent/0.6"})
    _busy.on = True
    try:
        # ProxyHandler({}) намеренно: DoH идёт напрямую. Гнать его через
        # HTTP-прокси незачем — прокси и так разрешает имена сам.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
    finally:
        _busy.on = False
    return parse_answer(data)


def resolve(host):
    """Адреса host через DoH с кэшем. [] — если DoH выключен или не смог."""
    if not is_enabled():
        return []
    h = str(host or "").strip().lower().rstrip(".")
    if not h or _is_local(h) or h == doh_host():
        return []
    if _looks_like_ip(h):
        return []
    now = time.time()
    with _cache_lock:
        hit = _cache.get(h)
        if hit and hit[1] > now:
            return list(hit[0])
    try:
        ips, ttl = query(h)
    except Exception as e:
        # Тихо откатываемся на системный резолвер: сломать ВСЮ сеть из-за
        # недоступного DoH-сервера нельзя.
        print("[doh] %s не разрешён через DoH (%s) — использую системный DNS."
              % (h, e))
        return []
    if not ips:
        return []
    with _cache_lock:
        _cache[h] = (list(ips), now + ttl)
    return list(ips)


def _is_local(host):
    if host in _LOCAL or host.endswith(".localhost"):
        return True
    return host.startswith("127.")


def _looks_like_ip(host):
    if host.startswith("[") or ":" in host:
        return True  # IPv6-литерал
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# Подмена системного резолвера
# ---------------------------------------------------------------------------

def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if not getattr(_busy, "on", False) and is_enabled():
        try:
            ips = resolve(host)
        except Exception:
            ips = []
        if ips:
            stype = type or socket.SOCK_STREAM
            sproto = proto or socket.IPPROTO_TCP
            return [(socket.AF_INET, stype, sproto, "", (ip, port)) for ip in ips]
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


def install():
    """Ставит подмену резолвера один раз за жизнь процесса."""
    global _orig_getaddrinfo
    with _install_lock:
        if _orig_getaddrinfo is not None:
            return True
        _orig_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _patched_getaddrinfo
        print("--> DoH включён: имена провайдеров разрешаются через %s"
              % _cfg["url"])
        return True


def uninstall():
    """Возвращает системный резолвер. Нужно тестам."""
    global _orig_getaddrinfo
    with _install_lock:
        if _orig_getaddrinfo is None:
            return
        socket.getaddrinfo = _orig_getaddrinfo
        _orig_getaddrinfo = None


def is_installed():
    return _orig_getaddrinfo is not None
