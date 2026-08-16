# -*- coding: utf-8 -*-
"""Хранилище ключей API и настроек прокси.

ГДЕ ЛЕЖИТ. Ключи ОБЩИЕ для всех проектов Godot: пользователь вводит ключ
один раз, а не в каждой игре заново. Поэтому файл живёт не в user:// (это
папка КОНКРЕТНОГО проекта) и тем более не рядом с аддоном, а в личной папке
настроек пользователя:
    Windows: %APPDATA%\\Godot_agent\\api_keys.json
    Linux:   ~/.config/godot_agent/api_keys.json
    macOS:   ~/Library/Application Support/godot_agent/api_keys.json

ПОЧЕМУ НЕ В ПРОЕКТЕ. Папка проекта — это git-репозиторий пользователя и
источник экспортируемой игры. Ключ, попавший туда, рано или поздно уедет
в публичный коммит или в собранную игру. Правило простое: ничего секретного
внутри рабочей области, даже временно.

ЧТО ЭТО НЕ ДЕЛАЕТ. Ключ хранится ОТКРЫТЫМ ТЕКСТОМ — так же, как это делают
большинство инструментов разработчика. Привязка шифротекста к аккаунту ОС
(DPAPI на Windows, keychain на macOS/Linux) описана в ОТЛОЖЕНО.md как
следующий шаг: она защищает от бытовых утечек (случайный коммит, синхронизация
AppData в облако, передача папки другому человеку), но не от программы,
запущенной под тем же пользователем. Своё шифрование с зашитым в код ключом
писать НЕЛЬЗЯ: оно не защищает ни от чего и создаёт ложную уверенность.

ГЛАВНЫЙ ИНВАРИАНТ МОДУЛЯ. Наружу (в панель, в HTTP-ответ, в лог, в консоль)
уходит только маска вида "sk-or-…3f9a". Сырой ключ отдаёт единственная
функция resolve_key(), и её результат имеет право видеть только транспорт.
Причина конкретная: dashboard.py дублирует весь stdout сервера на HTTP-страницу
/dashboard, поэтому напечатанный ключ мгновенно становится доступен по сети.
Для страховки есть redact() — им прогоняются любые тексты ошибок от провайдера
перед печатью.
"""
import json
import os
import sys

_FILE_NAME = "api_keys.json"
_APP_DIR_NAME = "Godot_agent"

# Переменная окружения, задающая папку настроек в обход системной. Нужна
# тестам (чтобы не трогать настоящие ключи разработчика) и переносимым сборкам.
ENV_CONFIG_DIR = "GODOT_AGENT_CONFIG_DIR"

_DEFAULT_CONFIG = {
    "version": 1,
    # provider_id -> {"key": str, "model": str, "base_url": str}
    "providers": {},
    # Что предложить при создании НОВОГО чата (у самого чата провайдер и
    # модель хранятся в его записи и потом не меняются).
    "defaults": {"provider": "", "model": ""},
    "proxy": {"enabled": False, "host": "", "port": 0, "user": "", "password": ""},
    # DNS over HTTPS: адрес доверенного резолвера. Помогает, когда провайдер
    # не разрешается системным DNS (подмена/NXDOMAIN у интернет-провайдера).
    # От блокировки по IP или SNI не спасает — там нужен прокси.
    "dns": {"enabled": False, "url": ""},
}


# ---------------------------------------------------------------------------
# Расположение файла
# ---------------------------------------------------------------------------

def config_dir():
    """Личная папка настроек агента (создаётся при первом обращении)."""
    override = (os.environ.get(ENV_CONFIG_DIR) or "").strip()
    if override:
        base = override
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA")
                            or os.path.expanduser("~"), _APP_DIR_NAME)
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/godot_agent")
    else:
        xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
        base = os.path.join(xdg or os.path.expanduser("~/.config"), "godot_agent")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception as e:
        print("[api_keys] Не удалось создать папку настроек %s (%s)" % (base, e))
    return base


def config_path():
    """Полный путь к файлу настроек — панель показывает его пользователю,
    чтобы было видно, где лежит ключ, и можно было удалить руками."""
    return os.path.join(config_dir(), _FILE_NAME)


# ---------------------------------------------------------------------------
# Чтение и запись
# ---------------------------------------------------------------------------

def _load():
    """Настройки с диска. Любая проблема чтения — пустая конфигурация:
    сервер обязан подняться даже с испорченным файлом настроек."""
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))  # глубокая копия
    p = config_path()
    if not os.path.isfile(p):
        return cfg
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("[api_keys] Файл настроек не читается (%s) — работаю с пустым." % e)
        return cfg
    if not isinstance(data, dict):
        return cfg
    if isinstance(data.get("providers"), dict):
        for pid, rec in data["providers"].items():
            if isinstance(rec, dict):
                cfg["providers"][str(pid)] = {
                    "key": str(rec.get("key") or ""),
                    "model": str(rec.get("model") or ""),
                    "base_url": str(rec.get("base_url") or ""),
                }
    if isinstance(data.get("defaults"), dict):
        cfg["defaults"]["provider"] = str(data["defaults"].get("provider") or "")
        cfg["defaults"]["model"] = str(data["defaults"].get("model") or "")
    if isinstance(data.get("proxy"), dict):
        pr = data["proxy"]
        try:
            port = int(pr.get("port") or 0)
        except Exception:
            port = 0
        cfg["proxy"] = {
            "enabled": bool(pr.get("enabled")),
            "host": str(pr.get("host") or "").strip(),
            "port": port,
            "user": str(pr.get("user") or ""),
            "password": str(pr.get("password") or ""),
        }
    if isinstance(data.get("dns"), dict):
        cfg["dns"] = {
            "enabled": bool(data["dns"].get("enabled")),
            "url": str(data["dns"].get("url") or "").strip(),
        }
    return cfg


def _save(cfg):
    """Запись через временный файл + os.replace: обрыв на середине не
    оставляет полуфабрикат вместо настроек. На posix права 0600."""
    p = config_path()
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        if os.name != "nt":
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
        os.replace(tmp, p)
        return True
    except Exception as e:
        print("[api_keys] Не удалось сохранить настройки (%s)" % e)
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Маскирование
# ---------------------------------------------------------------------------

def mask(key):
    """Безопасное представление ключа: начало и последние 4 символа.

    Начало у ключей осмысленное ("sk-or-", "gsk_", "AIza") — по нему
    пользователь узнаёт свой ключ, а восстановить его по маске нельзя.

    Многоточие строго ASCII ("..."), а не символ U+2026: маска попадает в
    print, а в кодировке консоли Windows (cp866) U+2026 отсутствует — вывод
    сервера не должен падать на печати служебного сообщения.
    """
    k = str(key or "")
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    head = k[:6] if len(k) > 14 else k[:3]
    return "%s...%s" % (head, k[-4:])


def redact(text):
    """Убирает из произвольного текста все известные секреты.

    Через эту функцию проходит ВЕСЬ вывод сервера (dashboard._Tee), а не только
    сообщения об ошибках. Причина: журнал stdout дублируется на HTTP-страницу
    /dashboard, и одного случайного print с заголовками запроса достаточно,
    чтобы ключ стал доступен по сети. Полагаться на аккуратность каждого
    будущего print нельзя — надёжнее один барьер на выходе.

    Список секретов кэшируется: функция вызывается на каждой строке вывода, а
    чтение файла настроек на каждую строку сделало бы сервер заметно медленнее.
    Кэш сбрасывается при любом изменении ключа или пароля прокси.
    """
    s = str(text or "")
    if not s:
        return s
    for secret in _secrets():
        if secret in s:
            s = s.replace(secret, mask(secret))
    return s


# Кэш секретов для redact(). None означает «надо перечитать».
_secrets_cache = {"list": None}


def _invalidate_secrets():
    _secrets_cache["list"] = None


def _secrets():
    """Все известные секреты, от длинных к коротким.

    Порядок важен: короткий секрет может оказаться подстрокой длинного, и
    замена в обратном порядке испортила бы маску длинного.
    """
    cached = _secrets_cache["list"]
    if cached is not None:
        return cached
    found = []
    try:
        cfg = _load()
        for rec in (cfg.get("providers") or {}).values():
            if rec.get("key"):
                found.append(rec["key"])
        pwd = (cfg.get("proxy") or {}).get("password")
        if pwd:
            found.append(pwd)
    except Exception:
        pass
    for name, value in os.environ.items():
        # Ключи из окружения: наши собственные и общепринятые имена вида
        # OPENROUTER_API_KEY / GROQ_API_KEY / GEMINI_API_KEY.
        if not value or len(value) <= 12:
            continue
        up = name.upper()
        if (up.startswith("GODOT_AGENT_") and up.endswith("_KEY")) \
                or up.endswith("_API_KEY"):
            found.append(value)
    result = sorted({s for s in found if len(s) > 8}, key=len, reverse=True)
    _secrets_cache["list"] = result
    return result


# ---------------------------------------------------------------------------
# Ключи
# ---------------------------------------------------------------------------

def _env_name(provider_id):
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id or ""))
    return "GODOT_AGENT_%s_KEY" % safe.upper()


def resolve_key(provider_id, env_names=()):
    """СЫРОЙ ключ провайдера. Единственная функция, отдающая секрет.

    Порядок: переменные окружения, затем файл настроек. Окружение выигрывает
    намеренно — так тесты и CI подставляют свой ключ, не трогая файл
    разработчика, и так можно запустить агента вообще без записи ключа на диск.

    Результат нельзя печатать, логировать и возвращать в HTTP-ответе.
    """
    for name in (_env_name(provider_id),) + tuple(env_names or ()):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    rec = (_load().get("providers") or {}).get(str(provider_id)) or {}
    return str(rec.get("key") or "").strip()


def key_source(provider_id, env_names=()):
    """Откуда взялся ключ: "env", "file" или "" (не задан). Нужно панели,
    чтобы не предлагать удалить ключ, заданный переменной окружения."""
    for name in (_env_name(provider_id),) + tuple(env_names or ()):
        if (os.environ.get(name) or "").strip():
            return "env"
    rec = (_load().get("providers") or {}).get(str(provider_id)) or {}
    return "file" if str(rec.get("key") or "").strip() else ""


def has_key(provider_id, env_names=()):
    return bool(resolve_key(provider_id, env_names))


def set_key(provider_id, key):
    """Сохраняет ключ. Пустое значение равносильно удалению."""
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    k = str(key or "").strip()
    cfg = _load()
    rec = (cfg["providers"].get(pid) or {"key": "", "model": "", "base_url": ""})
    rec["key"] = k
    cfg["providers"][pid] = rec
    ok = _save(cfg)
    _invalidate_secrets()
    if ok:
        print("--> Ключ провайдера %s %s (%s)"
              % (pid, "сохранён" if k else "удалён", mask(k) if k else "пусто"))
    return ok


def delete_key(provider_id):
    return set_key(provider_id, "")


# ---------------------------------------------------------------------------
# Модель, свой адрес, значения по умолчанию
# ---------------------------------------------------------------------------

def get_model(provider_id):
    rec = (_load().get("providers") or {}).get(str(provider_id)) or {}
    return str(rec.get("model") or "")


def set_model(provider_id, model):
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    cfg = _load()
    rec = (cfg["providers"].get(pid) or {"key": "", "model": "", "base_url": ""})
    rec["model"] = str(model or "").strip()
    cfg["providers"][pid] = rec
    return _save(cfg)


def get_base_url(provider_id):
    """Свой адрес endpoint'а — для провайдера "custom" и для локального
    llama-server, когда до него дойдёт дело. Пусто = адрес из реестра."""
    rec = (_load().get("providers") or {}).get(str(provider_id)) or {}
    return str(rec.get("base_url") or "").strip()


def set_base_url(provider_id, base_url):
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    cfg = _load()
    rec = (cfg["providers"].get(pid) or {"key": "", "model": "", "base_url": ""})
    rec["base_url"] = str(base_url or "").strip()
    cfg["providers"][pid] = rec
    return _save(cfg)


def get_defaults():
    d = _load().get("defaults") or {}
    return {"provider": str(d.get("provider") or ""),
            "model": str(d.get("model") or "")}


def set_defaults(provider_id, model=""):
    cfg = _load()
    cfg["defaults"] = {"provider": str(provider_id or "").strip(),
                       "model": str(model or "").strip()}
    return _save(cfg)


# ---------------------------------------------------------------------------
# Прокси
# ---------------------------------------------------------------------------

def get_proxy():
    """Настройки прокси БЕЗ пароля — этот вид уходит в панель."""
    pr = _load().get("proxy") or {}
    return {"enabled": bool(pr.get("enabled")),
            "host": str(pr.get("host") or ""),
            "port": int(pr.get("port") or 0),
            "user": str(pr.get("user") or ""),
            "has_password": bool(pr.get("password"))}


def parse_proxy_host(raw):
    """Разбирает введённый адрес прокси. Возвращает (host, port, ошибка).

    Зачем разбор, а не «как ввели». Пользователь легко путает прокси с другими
    сетевыми адресами. Реальный случай: в поле хоста ввели адрес
    DNS-over-HTTPS «https://xbox-dns.ru/dns-query», из него собиралось
    «http://https://xbox-dns.ru/dns-query», и ВСЕ запросы к провайдеру падали
    с непонятной ошибкой разрешения имени. Такой ввод надо отклонять сразу и
    объяснять, что не так.

    Принимаем: «host», «host:port», «http://host:port». Путь в адресе для
    прокси невозможен — это признак, что человек вставил адрес сервиса.
    """
    s = str(raw or "").strip()
    if not s:
        return "", 0, ""
    if "://" in s:
        scheme, s = s.split("://", 1)
        if scheme.lower() not in ("http", "https"):
            return "", 0, (u"схема «%s://» не поддерживается: нужен обычный "
                           u"HTTP-прокси (SOCKS пока не поддержан)" % scheme)
    tail = ""
    for sep in ("/", "?", "#"):
        if sep in s:
            s, rest = s.split(sep, 1)
            tail = sep + rest
            break
    if tail and tail.strip("/"):
        return "", 0, (u"адрес прокси не может содержать путь («%s»). Похоже, "
                       u"это адрес сетевого сервиса, а не прокси: нужны только "
                       u"хост и порт, например 127.0.0.1:8080" % tail)
    port = 0
    if s.startswith("["):
        # IPv6 в скобках: [::1]:8080
        end = s.find("]")
        if end > 0:
            hostpart, rest = s[:end + 1], s[end + 1:]
            if rest.startswith(":") and rest[1:].isdigit():
                port = int(rest[1:])
            s = hostpart
    elif ":" in s:
        head, maybe_port = s.rsplit(":", 1)
        if maybe_port.isdigit():
            s, port = head, int(maybe_port)
        else:
            return "", 0, (u"после двоеточия ожидается номер порта, а не «%s»"
                           % maybe_port)
    if not s:
        return "", 0, u"пустой адрес прокси"
    if " " in s:
        return "", 0, u"в адресе прокси не может быть пробелов"
    if port and not (0 < port < 65536):
        return "", 0, u"номер порта вне диапазона 1–65535"
    return s, port, ""


def set_proxy(enabled=None, host=None, port=None, user=None, password=None):
    """Обновляет только переданные поля. password=None оставляет прежний
    пароль (панель не должна пересылать его при каждом изменении хоста).

    Возвращает (ok, ошибка). Ошибка непустая — настройки НЕ сохранены: лучше
    отказать с объяснением, чем принять заведомо нерабочий адрес и оставить
    пользователя с падающими запросами и невнятной сетевой ошибкой.
    """
    cfg = _load()
    pr = cfg.get("proxy") or {}
    if host is not None:
        parsed_host, parsed_port, err = parse_proxy_host(host)
        if err:
            return False, err
        pr["host"] = parsed_host
        # Порт из адреса («host:8080») имеет приоритет над отдельным полем:
        # человек написал его явно.
        if parsed_port:
            pr["port"] = parsed_port
            port = None
    if port is not None:
        try:
            pr["port"] = int(port or 0)
        except Exception:
            pr["port"] = 0
    if user is not None:
        pr["user"] = str(user or "")
    if password is not None:
        pr["password"] = str(password or "")
    if enabled is not None:
        want = bool(enabled)
        if want and not str(pr.get("host") or "").strip():
            return False, (u"нельзя включить прокси без адреса: укажите хост "
                           u"и порт, например 127.0.0.1:8080")
        pr["enabled"] = want
    cfg["proxy"] = pr
    ok = _save(cfg)
    _invalidate_secrets()
    if ok:
        print("--> Прокси: %s %s:%s"
              % ("включён" if pr.get("enabled") else "выключен",
                 pr.get("host") or "-", pr.get("port") or "-"))
    return ok, ("" if ok else u"не удалось сохранить настройки прокси")


def proxy_url():
    """Адрес прокси для транспорта или None.

    Только HTTP(S) CONNECT-прокси: он поддерживается стандартным urllib без
    новых зависимостей, а HTTPS через него остаётся сквозным — прокси видит
    лишь имя хоста и не может прочитать ключ. SOCKS5 потребовал бы PySocks
    в сборке, поэтому отложен до появления реальной потребности.

    ВАЖНО: применять этот адрес только к трафику провайдера. Обращения к
    127.0.0.1 (свой сервер, будущий llama-server, порт отладки браузера)
    через прокси гнать нельзя — за это отвечает транспорт.
    """
    pr = _load().get("proxy") or {}
    if not pr.get("enabled"):
        return None
    host = str(pr.get("host") or "").strip()
    if not host:
        return None
    port = int(pr.get("port") or 0)
    auth = ""
    user = str(pr.get("user") or "")
    if user:
        from urllib.parse import quote
        pwd = str(pr.get("password") or "")
        auth = "%s:%s@" % (quote(user, safe=""), quote(pwd, safe=""))
    hostport = "%s:%d" % (host, port) if port else host
    return "http://%s%s" % (auth, hostport)


# ---------------------------------------------------------------------------
# DNS over HTTPS
# ---------------------------------------------------------------------------

def get_dns():
    d = _load().get("dns") or {}
    return {"enabled": bool(d.get("enabled")), "url": str(d.get("url") or "")}


def set_dns(enabled=None, url=None):
    """Адрес доверенного DoH-резолвера. Возвращает (ok, ошибка).

    Проверка адреса — здесь, а не в панели: неверный адрес молча превратил бы
    все запросы к провайдеру в непонятные сетевые ошибки, как это уже вышло с
    прокси.
    """
    import doh
    cfg = _load()
    d = cfg.get("dns") or {}
    if url is not None:
        clean, err = doh.validate_url(url)
        if err:
            return False, err
        d["url"] = clean
    if enabled is not None:
        want = bool(enabled)
        if want and not str(d.get("url") or "").strip():
            return False, (u"нельзя включить DoH без адреса сервера: укажите "
                           u"его, например https://dns.example.com/dns-query")
        d["enabled"] = want
    cfg["dns"] = d
    ok = _save(cfg)
    if ok:
        print("--> DoH: %s %s" % ("включён" if d.get("enabled") else "выключен",
                                  d.get("url") or "-"))
        doh.configure(d.get("enabled"), d.get("url"))
    return ok, ("" if ok else u"не удалось сохранить настройки DNS")


def apply_dns_settings():
    """Применяет сохранённые настройки DoH к текущему процессу. Вызывается при
    старте сервера: настройки могли быть заданы в прошлой сессии."""
    import doh
    d = get_dns()
    doh.configure(d["enabled"], d["url"])
    return d


# ---------------------------------------------------------------------------
# Безопасный отчёт для панели
# ---------------------------------------------------------------------------

def status(provider_ids=(), env_map=None):
    """Состояние ключей для панели. Сырых ключей здесь не бывает.

    provider_ids — какие провайдеры показать (реестр знает только
    вызывающая сторона, чтобы этот модуль не зависел от providers.py).
    env_map — provider_id -> кортеж дополнительных имён переменных окружения
    (общепринятые вроде OPENROUTER_API_KEY).
    """
    env_map = env_map or {}
    cfg = _load()
    out = {}
    ids = list(provider_ids) or list((cfg.get("providers") or {}).keys())
    for pid in ids:
        extra = tuple(env_map.get(pid) or ())
        src = key_source(pid, extra)
        raw = resolve_key(pid, extra) if src else ""
        rec = (cfg.get("providers") or {}).get(pid) or {}
        out[pid] = {
            "configured": bool(src),
            "source": src,
            "masked": mask(raw),
            "model": str(rec.get("model") or ""),
            "base_url": str(rec.get("base_url") or ""),
        }
    return {"providers": out,
            "defaults": get_defaults(),
            "proxy": get_proxy(),
            "dns": get_dns(),
            "config_path": config_path()}
