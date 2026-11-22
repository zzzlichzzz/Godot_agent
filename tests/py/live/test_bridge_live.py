"""tests/py/live/test_bridge_live.py - живой прогон моста редактора (`needs_live`).

Доказательство, которого у части A не было: GDScript-сервер моста действительно
компилируется движком и отвечает по проводу. Godot запускается headless с
харнессом `editor/harness/bridge_probe.gd` (тот же `socket_server.gd`, что и в
редакторе), Python-клиент `EditorClient` проходит handshake и получает три
примитива словаря; каждый ответ сверяется `kernel.schema.validate` по
`result_schema` из `contract/editor_verbs.json`.

Долг `needs_live`: без бинаря Godot тест пропускается - «мост работает» без
движка не утверждается (R-18, R-22).

Второй половиной того же теста проверяется одиночный режим: харнесс, к которому
никто не подключился, обязан написать `ok:false / failure.reason = "no_client"`
(exit 1, с подсказкой про pytest), а не `timeout`. Приёмка живой ветки - именно
этот pytest-прогон, а не `-s` без клиента.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from python.kernel.schema import validate
from python.substrate.editor import verbs_catalog
from python.substrate.editor.client import EditorClient

#: Корень аддона (`.../addons/godot_agent`).
ROOT = Path(__file__).resolve().parents[3]
#: Корень проекта Godot (`res://`) - на уровень выше `addons/`.
PROJECT = ROOT.parents[1]
#: Харнесс моста: поднимает сервер и пишет `harness_result.json`.
PROBE = "res://addons/godot_agent/editor/harness/bridge_probe.gd"
VERBS = ("editor_ping", "editor_state", "editor_selection")

#: Где искать движок: переменная окружения, известные установки, затем `PATH`.
GODOT_BIN_ENV = "GODOT_BIN"
GODOT_CANDIDATES = (
    Path(r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.6\Godot_v4.6-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.5.1\Godot_v4.5.1-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.5\Godot_v4.5-stable_win64_console.exe"),
)
#: Сколько ждать подъёма моста (первый запуск импортирует проект).
START_TIMEOUT = 60.0
#: Сколько ждать выхода движка после третьего примитива.
EXIT_TIMEOUT = 40.0

pytestmark = pytest.mark.needs_live


def _binary():
    """Путь к Godot или `None`: без движка живой прогон невозможен."""
    chosen = os.environ.get(GODOT_BIN_ENV, "")
    if chosen and Path(chosen).is_file():
        return Path(chosen)
    for candidate in GODOT_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("godot") or shutil.which("godot4")
    return Path(found) if found else None


def _next_line(lines, timeout):
    """Следующая строка stdout движка; `None` - поток закрылся или истёк таймаут."""
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return None


def _start(binary):
    """Запустить харнесс и вернуть (процесс, адрес моста, очередь строк, лог)."""
    proc = subprocess.Popen(
        [str(binary), "--headless", "--path", str(PROJECT), "-s", PROBE],
        cwd=str(PROJECT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    lines: queue.Queue = queue.Queue()
    log: list = []

    def _pump():
        for raw in proc.stdout or ():
            lines.put(raw.rstrip("\r\n"))
        lines.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    while True:
        line = _next_line(lines, START_TIMEOUT)
        if line is None:
            break
        log.append(line)
        if line.startswith("BRIDGE_PORT "):
            return proc, json.loads(line[len("BRIDGE_PORT "):]), lines, log
    proc.terminate()
    proc.wait(timeout=EXIT_TIMEOUT)
    pytest.fail("мост не поднялся:\n" + "\n".join(log))

def _solo(binary, timeout_ms=1200):
    """Одиночный запуск без клиента: харнесс обязан признаться `no_client`.

    Возвращает (код выхода, payload из `BRIDGE_RESULT`, весь stdout). Таймаут
    сокращён через `HARNESS_TIMEOUT_MS`, чтобы тест не ждал 20 с.
    """
    run = subprocess.run(
        [str(binary), "--headless", "--path", str(PROJECT), "-s", PROBE],
        cwd=str(PROJECT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, HARNESS_TIMEOUT_MS=str(timeout_ms)),
        timeout=START_TIMEOUT + EXIT_TIMEOUT)
    stdout = run.stdout or ""
    payload = None
    for line in stdout.splitlines():
        if line.startswith("BRIDGE_RESULT "):
            payload = json.loads(line[len("BRIDGE_RESULT "):])
    return run.returncode, payload, stdout


def test_bridge_answers_three_verbs_from_real_godot(tmp_path):
    binary = _binary()
    if binary is None:
        pytest.skip("Godot не найден: живой прогон моста остаётся долгом needs_live")
    proc, address, lines, log = _start(binary)
    client = None
    try:
        port_file = tmp_path / "port.json"
        port_file.write_text(json.dumps({"port": address["port"],
                                         "token": address["token"],
                                         "protocol": 1,
                                         "verbs_version": verbs_catalog.version()}),
                             encoding="utf-8")
        client = EditorClient(port_file=str(port_file))
        answers = {verb: client.call(verb) for verb in VERBS}

        for verb, answer in answers.items():
            assert isinstance(answer, dict), verb
            assert validate(answer, verbs_catalog.result_schema(verb)) == [], verb

        ping = answers["editor_ping"]
        assert ping["godot"].startswith("4."), ping["godot"]
        assert ping["verbs_version"] == verbs_catalog.version()
        assert ping["protocol"] == 1
        assert ping["open_scenes"] == 0  # headless: редактора нет
        assert ping["uptime_s"] >= 0

        scan = address["scripts"]
        assert scan["total"] > 0, scan
        assert scan["broken"] == [], scan

        state = answers["editor_state"]
        assert state["open_scenes"] == [] and state["active_scene"] is None
        assert isinstance(state["project_hash"], str) and state["project_hash"]

        selection = answers["editor_selection"]
        assert selection == {"node_path": None, "scene": None, "script": None,
                             "properties": []}

        client.close()
        client = None
        assert proc.wait(timeout=EXIT_TIMEOUT) == 0, "\n".join(log)

        result_path = Path(address["result"])
        assert result_path.is_file(), result_path
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        assert payload["ok"] is True, payload
        assert set(payload["verbs"]) == set(VERBS)
        assert payload["engine"].startswith("4."), payload["engine"]
        assert payload["protocol"] == 1
        assert payload["verbs_version"] == verbs_catalog.version()
        assert payload["scripts"]["broken"] == [], payload["scripts"]
        assert payload["scripts"]["total"] == scan["total"]
        for verb in VERBS:
            assert payload["verbs"][verb]["ok"] is True, verb
        assert payload["verbs"]["editor_ping"]["result"] == ping
        assert payload["verbs"]["editor_selection"]["result"] == selection

        # Одиночный запуск (клиента нет) обязан честно сказать `no_client`, а не
        # `timeout`: иначе доказательством пришлось бы считать одну и ту же
        # команду, снятую из двух разных прогонов (R-22). Файл харнесс
        # перезаписывает - сверяем и его, а не только stdout.
        code, solo, stdout = _solo(binary)
        assert solo is not None, stdout
        assert code == 1, (code, stdout)
        assert solo["ok"] is False, solo
        assert solo["verbs"] == {}, solo
        assert solo["failure"]["reason"] == "no_client", solo
        assert solo["failure"]["served"] == [], solo
        assert "pytest tests/py/live" in solo["failure"]["hint"], solo
        written = json.loads(result_path.read_text(encoding="utf-8"))
        assert written["ok"] is False and written["failure"] == solo["failure"], written
    finally:
        if client is not None:
            client.close()
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=EXIT_TIMEOUT)
