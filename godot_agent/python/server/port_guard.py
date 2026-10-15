# -*- coding: utf-8 -*-
"""Защита порта :5000 от «призрачных» сокетов (Windows).

Как появляется призрак (найдено 13.10.2026 на реальном случае):
1. werkzeug при app.run() делает слушающий сокет НАСЛЕДУЕМЫМ
   (serving.py: srv.socket.set_inheritable(True)).
2. selenium на Windows запускает chromedriver с наследованием хендлов
   (close_fds=False по умолчанию) — chromedriver получает копию сокета :5000.
3. Сервер умирает (os._exit из /server/shutdown или taskkill), а осиротевший
   chromedriver продолжает держать сокет: порт в состоянии LISTENING, но
   отвечать НЕКОМУ — панель в Godot подключается и не получает ответа.

Профилактика призраков живёт в browser/ (запуск Chrome и chromedriver без
наследования хендлов) и в /server/shutdown (chromedriver гасится до выхода).
Этот модуль лечит уже появившееся: при старте сервер проверяет порт и, если
порт занят неотвечающим сокетом, закрывает ОСИРОТЕВШИЕ chromedriver.exe
(у которых родительский процесс уже мёртв) и повторяет проверку.
"""

import os
import socket
import subprocess

__all__ = ["probe_port", "kill_orphan_chromedrivers", "recover_ghost_port"]

_HOST = "127.0.0.1"

# Убиваем только chromedriver, чей родитель уже мёртв. Живые chromedriver
# (например, свои Selenium-скрипты пользователя) НЕ трогаем.
_PS_KILL_ORPHANS = (
    "$ids = (Get-Process -ErrorAction SilentlyContinue | "
    "Select-Object -ExpandProperty Id); "
    "Get-CimInstance Win32_Process -Filter \"Name='chromedriver.exe'\" | "
    "Where-Object { $_.ParentProcessId -ne 0 -and "
    "$ids -notcontains $_.ParentProcessId } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction "
    "SilentlyContinue; Write-Output ('killed chromedriver ' + $_.ProcessId) }"
)


def probe_port(port=5000, host=_HOST, timeout=2.0):
    """Состояние порта: 'free' | 'live' | 'ghost'.

    'live'  — порт слушает кто-то ЖИВОЙ: TCP соединяется и присылает хотя бы
              байты ответа (сервер уже запущен).
    'ghost' — TCP соединяется, но ответа нет: сокет держит «мёртвая» копия
              (обычно осиротевший chromedriver) — именно это ломает панель.
    """
    # Свободен ли порт: эксклюзивная привязка не даёт «двойного bind».
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind((host, port))
        return "free"
    except OSError:
        pass
    # Порт занят — проверяем, отвечает ли на него кто-нибудь.
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(b"GET /dashboard HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            s.settimeout(timeout)
            try:
                data = s.recv(64)
            except (socket.timeout, OSError):
                data = b""
            return "live" if data else "ghost"
    except OSError:
        return "ghost"


def kill_orphan_chromedrivers(timeout=25.0):
    """Закрывает chromedriver.exe, чей родитель уже мёртв (осиротевшие).

    Живые chromedriver не трогаем — у пользователя могут быть свои
    Selenium-скрипты. Возвращает список убитых PID (может быть пустым).
    На не-Windows — пустой список.
    """
    if os.name != "nt":
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _PS_KILL_ORPHANS],
            capture_output=True, text=True, timeout=timeout,
            creationflags=flags, encoding="utf-8", errors="replace",
        )
    except Exception:
        return []
    killed = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("killed chromedriver "):
            try:
                killed.append(int(line.rsplit(" ", 1)[1]))
            except ValueError:
                pass
    return killed


def recover_ghost_port(port=5000, host=_HOST, log=print):
    """Проверяет порт перед app.run() и лечит «призрак», если он есть.

    Возвращает итоговое состояние порта после попытки лечения:
    'free' | 'live' | 'ghost'. Никогда не бросает исключений —
    запуск сервера не должен ломаться из-за самой проверки.
    """
    try:
        state = probe_port(port, host)
        if state == "free":
            return "free"
        if state == "live":
            log("--> Порт %d уже слушает живой сервер — похоже, второй "
                "экземпляр уже запущен." % port)
            return "live"
        log("--> Порт %d занят, но никто не отвечает (зависший сокет — обычно "
            "осиротевший chromedriver от прошлого запуска)." % port)
        killed = kill_orphan_chromedrivers()
        if killed:
            log("--> Закрыл осиротевшие chromedriver.exe: %s"
                % ", ".join(str(p) for p in killed))
        state = probe_port(port, host)
        if state == "free":
            log("--> Порт %d освобождён — продолжаю запуск." % port)
        elif state == "ghost":
            log("--> Порт %d всё ещё занят неотвечающим сокетом. Закройте "
                "держащий его процесс:\n    taskkill /F /IM chromedriver.exe\n"
                "    (или найдите его: netstat -ano | findstr :%d, затем "
                "завершите PID в Диспетчере задач)" % (port, port))
        return state
    except Exception as e:
        log("--> Проверка порта %d не удалась (не критично): %s" % (port, e))
        return "ghost"
