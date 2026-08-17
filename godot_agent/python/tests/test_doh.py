# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты DNS over HTTPS (doh).

Зачем это нужно. Если интернет-провайдер подменяет DNS, адрес провайдера API
не разрешается и запрос падает до соединения. DoH спрашивает адрес у
доверенного сервера по HTTPS.

Границы возможностей проверяются тоже: DoH меняет ТОЛЬКО разрешение имени, к
локальным адресам не применяется, а при недоступности DoH-сервера работа
продолжается через системный DNS — сломать всю сеть из-за него нельзя.

Тест офлайновый: DoH-сервер поднимается локально и отвечает настоящими
DNS-пакетами формата RFC 8484.
"""
import shutil
import socket
import struct
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CFG = tempfile.mkdtemp(prefix="agent_cfg_doh_")
_os0.environ["GODOT_AGENT_CONFIG_DIR"] = CFG

import api_keys
import doh

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Локальный DoH-сервер
# ---------------------------------------------------------------------------
ANSWERS = {"example.test": "203.0.113.7", "second.test": "198.51.100.9"}
SEEN = {"queries": [], "mode": "ok"}


def _read_qname(data, i=12):
    labels = []
    while True:
        n = data[i]
        if n == 0:
            return ".".join(labels), i + 1
        labels.append(data[i + 1:i + 1 + n].decode("ascii"))
        i += 1 + n


def _build_response(query, ip, ttl=60):
    tid = query[:2]
    qname, end = _read_qname(query)
    question = query[12:end + 4]
    header = tid + struct.pack(">HHHHH", 0x8180, 1, 1, 0, 0)
    # Имя в ответе — указателем на вопрос (сжатие), как делают настоящие серверы.
    rr = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, ttl, 4)
    rr += bytes(int(p) for p in ip.split("."))
    return header + question + rr


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        query = self.rfile.read(n)
        qname, _ = _read_qname(query)
        SEEN["queries"].append(qname)
        if SEEN["mode"] == "down":
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if SEEN["mode"] == "nxdomain":
            body = query[:2] + struct.pack(">HHHHH", 0x8183, 1, 0, 0, 0) + query[12:]
        elif qname in ANSWERS:
            body = _build_response(query, ANSWERS[qname])
        else:
            body = query[:2] + struct.pack(">HHHHH", 0x8180, 1, 0, 0, 0) + query[12:]
        self.send_response(200)
        self.send_header("Content-Type", "application/dns-message")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
DOH_URL = "http://127.0.0.1:%d/dns-query" % PORT

# ---------------------------------------------------------------------------
# 1) Проверка адреса DoH-сервера
# ---------------------------------------------------------------------------
check(u"схема достраивается до https",
      doh.validate_url(u"dns.example.com/dns-query")
      == (u"https://dns.example.com/dns-query", u""))
check(u"https принимается как есть",
      doh.validate_url(u"https://xbox-dns.ru/dns-query")
      == (u"https://xbox-dns.ru/dns-query", u""))
check(u"http отклоняется с объяснением",
      u"https" in doh.validate_url(u"http://dns.example.com/dns-query")[1])
check(u"пустой адрес — не ошибка", doh.validate_url(u"") == (u"", u""))
check(u"адрес без хоста отклонён", doh.validate_url(u"https:///dns-query")[1] != u"")
check(u"пробел в адресе отклонён",
      doh.validate_url(u"https://dns example.com/q")[1] != u"")

# ---------------------------------------------------------------------------
# 2) Сборка и разбор DNS-пакетов
# ---------------------------------------------------------------------------
q = doh._build_query(u"example.test")
check(u"в запросе один вопрос", struct.unpack(">H", q[4:6])[0] == 1)
check(u"рекурсия разрешена", (struct.unpack(">H", q[2:4])[0] & 0x0100) != 0)
check(u"имя закодировано метками", b"\x07example\x04test\x00" in q)

resp = _build_response(q, u"203.0.113.7", ttl=120)
ips, ttl = doh.parse_answer(resp)
check(u"адрес разобран из ответа", ips == [u"203.0.113.7"], ips)
check(u"TTL разобран", ttl == 120, ttl)

nx = q[:2] + struct.pack(">HHHHH", 0x8183, 1, 0, 0, 0) + q[12:]
try:
    doh.parse_answer(nx)
    check(u"NXDOMAIN распознан как ошибка", False)
except ValueError as e:
    check(u"NXDOMAIN распознан как ошибка", u"не найдено" in str(e), str(e))
try:
    doh.parse_answer(b"\x00\x01")
    check(u"обрезанный ответ распознан", False)
except ValueError:
    check(u"обрезанный ответ распознан", True)

# ---------------------------------------------------------------------------
# 3) Запрос к серверу и кэш
# ---------------------------------------------------------------------------
doh.configure(True, DOH_URL)
check(u"DoH включён", doh.is_enabled())
SEEN["queries"] = []
check(u"имя разрешено через DoH", doh.resolve(u"example.test") == [u"203.0.113.7"])
check(u"к серверу был один запрос", SEEN["queries"] == [u"example.test"], SEEN["queries"])
check(u"повторный вызов берётся из кэша",
      doh.resolve(u"example.test") == [u"203.0.113.7"] and len(SEEN["queries"]) == 1,
      SEEN["queries"])
check(u"другое имя запрашивается отдельно",
      doh.resolve(u"second.test") == [u"198.51.100.9"] and len(SEEN["queries"]) == 2)

# ---------------------------------------------------------------------------
# 4) Что через DoH НЕ разрешается
# ---------------------------------------------------------------------------
SEEN["queries"] = []
check(u"localhost не идёт в DoH", doh.resolve(u"localhost") == [])
check(u"127.0.0.1 не идёт в DoH", doh.resolve(u"127.0.0.1") == [])
check(u"IP-адрес не идёт в DoH", doh.resolve(u"203.0.113.7") == [])
check(u"сам DoH-сервер не разрешается через себя",
      doh.resolve(doh.doh_host()) == [])
check(u"лишних запросов к серверу не было", SEEN["queries"] == [], SEEN["queries"])

# ---------------------------------------------------------------------------
# 5) Отказ DoH не ломает сеть
# ---------------------------------------------------------------------------
doh.clear_cache()
SEEN["mode"] = "down"
check(u"недоступный DoH -> пустой ответ, а не исключение",
      doh.resolve(u"example.test") == [])
SEEN["mode"] = "nxdomain"
doh.clear_cache()
check(u"NXDOMAIN -> пустой ответ (откат на системный DNS)",
      doh.resolve(u"example.test") == [])
SEEN["mode"] = "ok"
doh.clear_cache()

# ---------------------------------------------------------------------------
# 6) Подмена системного резолвера
# ---------------------------------------------------------------------------
check(u"резолвер подменён после включения", doh.is_installed())
info = socket.getaddrinfo(u"example.test", 443)
check(u"getaddrinfo отдаёт адрес от DoH",
      info and info[0][4][0] == u"203.0.113.7", info)
check(u"порт сохранён", info[0][4][1] == 443)
check(u"семейство и тип пригодны для соединения",
      info[0][0] == socket.AF_INET and info[0][1] == socket.SOCK_STREAM, info[0])

# Локальные имена по-прежнему разрешает система.
local = socket.getaddrinfo(u"localhost", 80)
check(u"localhost разрешает система", bool(local))

# Выключение возвращает системный резолвер по имени, которого нет в ANSWERS.
doh.configure(False, DOH_URL)
check(u"после выключения DoH resolve пустой", doh.resolve(u"example.test") == [])
try:
    socket.getaddrinfo(u"example.test", 443)
    check(u"выключенный DoH не подменяет ответы", False)
except socket.gaierror:
    check(u"выключенный DoH не подменяет ответы", True)

doh.uninstall()
check(u"резолвер возвращён системе", not doh.is_installed())

# ---------------------------------------------------------------------------
# 7) Настройки через api_keys
# ---------------------------------------------------------------------------
check(u"для новой конфигурации DoH включён по умолчанию",
      api_keys.get_dns() == {"enabled": True,
                             "url": u"https://xbox-dns.ru/dns-query"},
      api_keys.get_dns())
ok, err = api_keys.set_dns(url=u"http://dns.example.com/dns-query", enabled=True)
check(u"http-адрес DoH не сохраняется", not ok and err != u"", (ok, err))
check(u"неверный адрес не изменил стандартный DoH",
      api_keys.get_dns()["enabled"] is True
      and api_keys.get_dns()["url"] == u"https://xbox-dns.ru/dns-query")

ok, err = api_keys.set_dns(url=u"xbox-dns.ru/dns-query", enabled=True)
check(u"адрес без схемы принят и достроен", ok and err == u"", (ok, err))
check(u"сохранён https-адрес",
      api_keys.get_dns()["url"] == u"https://xbox-dns.ru/dns-query",
      api_keys.get_dns())
check(u"DoH включён в настройках", api_keys.get_dns()["enabled"] is True)

ok, err = api_keys.set_dns(url=u"", enabled=True)
check(u"включить DoH без адреса нельзя", not ok and u"без адреса" in err, err)

api_keys.set_dns(enabled=False)
check(u"явное выключение стандартного DoH сохраняется",
      api_keys.get_dns()["enabled"] is False)
doh.configure(False, "")
doh.uninstall()
srv.shutdown()
shutil.rmtree(CFG, ignore_errors=True)
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
