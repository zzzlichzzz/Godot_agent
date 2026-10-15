# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты port_guard: распознавание состояния порта :5000 и защита от «призрака».

Регрессия 13.10.2026: осиротевший chromedriver держал слушающий сокет сервера
(наследование хендлов: werkzeug делает сокет наследуемым, selenium на Windows
запускает chromedriver с close_fds=False). Панель в Godot «не соединялась».
Здесь проверяем, что защита честно различает состояния порта и не трогает
живой сервер.
"""
import socket
import sys
import threading
import time

import port_guard as PG

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


HOST = "127.0.0.1"


def free_port():
    """Свободный TCP-порт (получаем у ОС и сразу отпускаем)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def listening_socket(port, serve_reply=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, port))
    s.listen(5)
    if serve_reply:
        def _once():
            try:
                conn, _ = s.accept()
                try:
                    conn.recv(1024)
                    conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok")
                finally:
                    conn.close()
            except OSError:
                pass
        threading.Thread(target=_once, daemon=True).start()
    return s


# ---------------------------------------------------------------------------
# 1) Свободный порт
# ---------------------------------------------------------------------------
free_p = free_port()
check(u"свободный порт распознаётся как 'free'", PG.probe_port(free_p, HOST) == "free")

# ---------------------------------------------------------------------------
# 2) «Призрак»: кто-то слушает, но не отвечает (как осиротевший chromedriver)
# ---------------------------------------------------------------------------
ghost_p = free_port()
ghost_sock = listening_socket(ghost_p)  # никто не принимает — намеренно
try:
    t0 = time.time()
    state = PG.probe_port(ghost_p, HOST, timeout=1.0)
    elapsed = time.time() - t0
    check(u"молчащий слушающий сокет распознаётся как 'ghost'", state == "ghost", state)
    check(u"проверка завершается быстро (таймаут + запас < 5 c)", elapsed < 5.0, elapsed)
finally:
    ghost_sock.close()

# ---------------------------------------------------------------------------
# 3) Живой сервер: принимает соединение и отвечает
# ---------------------------------------------------------------------------
live_p = free_port()
live_sock = listening_socket(live_p, serve_reply=True)
try:
    state = PG.probe_port(live_p, HOST, timeout=2.0)
    check(u"отвечающий сокет распознаётся как 'live'", state == "live", state)
finally:
    live_sock.close()

# ---------------------------------------------------------------------------
# 4) recover на свободном порту: ничего не делает и ничего не пишет
# ---------------------------------------------------------------------------
free_p2 = free_port()
log_lines = []
state = PG.recover_ghost_port(free_p2, HOST, log=log_lines.append)
check(u"recover на свободном порту -> 'free'", state == "free", state)
check(u"recover на свободном порту молчит в лог", log_lines == [], log_lines)

# ---------------------------------------------------------------------------
# 5) recover на призраке: сообщает причину и не падает. Наш собственный сокет
# держит порт, поэтому лечение порт не освободит — состояние остаётся 'ghost',
# и в логе есть понятное объяснение. Живые chromedriver проверка не трогает.
# ---------------------------------------------------------------------------
ghost_p2 = free_port()
ghost_sock2 = listening_socket(ghost_p2)
try:
    log_lines = []
    state = PG.recover_ghost_port(ghost_p2, HOST, log=log_lines.append)
    check(u"recover на призраке не падает и сообщает состояние", state in ("ghost", "free"), state)
    check(u"recover объясняет причину внятным текстом",
          any(u"не отвечает" in ln for ln in log_lines), log_lines)
finally:
    ghost_sock2.close()

# ---------------------------------------------------------------------------
# 6) Поиск осиротевших chromedriver: возвращает список и не падает
# ---------------------------------------------------------------------------
killed = PG.kill_orphan_chromedrivers()
check(u"kill_orphan_chromedrivers возвращает список", isinstance(killed, list), killed)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
