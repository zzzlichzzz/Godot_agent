"""tests/py/live/test_editor_branch_live.py - редакторская ветка моста (`needs_live`).

Долг части A: в режиме `--headless -s` `Engine.is_editor_hint() = false`, поэтому
`EditorInterface` - заглушка и ветка `open_scenes` / `active_scene` / выделения
живым прогоном не покрывалась. Здесь мост поднимается **из плагина внутри
редактора** (`godot --headless --editor`): `plugin.gd` -> `editor/core/lifecycle.gd`
-> `bridge/server/socket_server.gd`, адрес и токен редактор пишет сам в
`user://godot_agent/port.json`.

Сцена `zz_editor_branch_probe.tscn` создаётся тестом на время прогона и удаляется:
она - признак того, что ответил редактор, а не заглушка. При `has_editor() = false`
снимок пуст, `open_scenes` станет `[]`, и тест краснеет (мутация M1 из промпта).

Вторая половина теста - уборка адреса: `_exit_tree()` плагина останавливает сервер
и удаляет `port.json`. Подложенный заранее «старый» `port.json` после штатного
`--quit-after` остаться не должен (мутация M3).

Третья часть - живой батч `editing.scene_ops` (политика корпуса `live`):
`editor_scene_plan` ничего не пишет, `editor_scene_apply` правит открытую сцену
одним undo-шагом (две операции - ровно +1 к ревизии), повтор того же
плана даёт `stale_plan`, а сбой на втором шаге - типизированный отказ
без изменения сцены. Сам Ctrl+Z снаружи не вызвать: в словаре нет
примитива undo (`verbs_version` заморожен) - это
открытый долг D-3, записанный в листе механики.

Без бинаря Godot тест пропускается: «редактор отвечает» без движка не
утверждается (R-18, R-22).
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from python.kernel.errors import AppError
from python.kernel.schema import validate
from python.modules.editing.scene_ops import app as scene_ops_app
from python.modules.editing.scene_ops.domain import core as scene_core
from python.substrate.editor import verbs_catalog
from python.substrate.editor.client import EditorClient

#: Корень аддона (`.../addons/godot_agent`).
ROOT = Path(__file__).resolve().parents[3]
#: Корень проекта Godot (`res://`) - на уровень выше `addons/`.
PROJECT = ROOT.parents[1]
#: Примитивы словаря, которые обязана отдать редакторская ветка.
VERBS = ("editor_ping", "editor_state", "editor_selection")
#: Сцена-признак: открывается редактором по аргументу командной строки.
SCENE_FILE = PROJECT / "zz_editor_branch_probe.tscn"
SCENE_RES = "res://zz_editor_branch_probe.tscn"
SCENE_TEXT = ('[gd_scene format=3]\n\n[node name="Probe" type="Node2D"]\n\n'
              '[node name="Body" type="Node2D" parent="."]\n')
#: Сколько кадров живёт второй запуск редактора: он должен успеть поднять мост и
#: штатно выйти, убрав `port.json`.
QUIT_FRAMES = 60

#: Где искать движок: переменная окружения, известные установки, затем `PATH`.
GODOT_BIN_ENV = "GODOT_BIN"
GODOT_CANDIDATES = (
    Path(r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.6\Godot_v4.6-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.5.1\Godot_v4.5.1-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.5\Godot_v4.5-stable_win64_console.exe"),
)
#: Сколько ждать подъёма моста из плагина (первый запуск импортирует проект).
START_TIMEOUT = 75.0
#: Сколько ждать выхода движка.
EXIT_TIMEOUT = 60.0
#: Сколько ждать, пока редактор откроет сцену из аргумента командной строки:
#: плагины поднимаются раньше (первое сканирование), сцена - в конце старта.
SCENE_TIMEOUT = 40.0

pytestmark = pytest.mark.needs_live


class _Ctx:
    """Минимум порта для механики: единственный порт `editor` - клиент моста."""

    def __init__(self, client):
        self._client = client

    def port(self, name):
        assert name == "editor", name
        return self._client


def _set(node, prop, value):
    """Одна операция `set_property`: батч из двух таких и проверяет «один undo»."""
    return {"op": "set_property", "node": node, "property": prop,
            "value": value}


def _scene(client):
    """Сцена-проба из `editor_state`: ревизия, `dirty`, путь."""
    return client.call("editor_state")["open_scenes"][0]


def _scene_ops(client, revision, operations, **extra):
    """Вызов механики `scene_ops`: план по умолчанию, `apply=True` - запись."""
    args = {"scene": SCENE_RES, "expected_revision": revision,
            "operations": operations}
    args.update(extra)
    return scene_ops_app.call("scene_ops", args, _Ctx(client))


def _undo(client, revision):
    """Откат одного действия истории: примитив `editor_scene_undo` (часть B.3)."""
    answer = client.call("editor_scene_undo",
                         {"scene": SCENE_RES, "expected_revision": revision})
    problems = validate(answer, verbs_catalog.result_schema("editor_scene_undo"))
    assert problems == [], problems
    return answer


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


def _project_name():
    """`config/name` из `project.godot` - по нему Godot строит `user://`."""
    for line in (PROJECT / "project.godot").read_text(encoding="utf-8").splitlines():
        if line.startswith("config/name="):
            return line.split("=", 1)[1].strip().strip('"')
    return PROJECT.name


def _user_data():
    """Каталог `user://` проекта на текущей платформе."""
    appdata = os.environ.get("APPDATA", "")
    if os.name == "nt" and appdata:
        base = Path(appdata) / "Godot" / "app_userdata"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Godot" / "app_userdata"
    else:
        share = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        base = Path(share) / "godot" / "app_userdata"
    return base / _project_name()


def _port_file():
    """Адрес, который пишет `socket_server.gd` (его константа `PORT_FILE`)."""
    return _user_data() / "godot_agent" / "port.json"


def _start_editor(binary, *extra):
    """Запустить редактор и вернуть (процесс, очередь строк, лог)."""
    command = [str(binary), "--headless", "--editor", "--path", str(PROJECT)]
    command.extend(extra)
    proc = subprocess.Popen(command, cwd=str(PROJECT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", bufsize=1)
    lines: queue.Queue = queue.Queue()
    log: list = []

    def _pump():
        for raw in proc.stdout or ():
            line = raw.rstrip("\r\n")
            log.append(line)
            lines.put(line)
        lines.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    return proc, lines, log


def _wait_port(port_file, lines, log):
    """Дождаться `port.json` из плагина и вернуть его содержимое."""
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if port_file.is_file():
            try:
                info = json.loads(port_file.read_text(encoding="utf-8"))
            except ValueError:
                info = None
            if isinstance(info, dict) and isinstance(info.get("port"), int):
                return info
        while not lines.empty():
            lines.get_nowait()
        time.sleep(0.25)
    raise AssertionError("мост не поднялся: port.json не появился\n" + "\n".join(log))


def _stop(proc):
    """Погасить редактор, дождавшись выхода."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=EXIT_TIMEOUT)


def _run_and_wait(binary, frames):
    """Штатный запуск редактора на N кадров: вернуть (код, лог)."""
    proc, _lines, log = _start_editor(binary, "--quit-after", str(frames))
    try:
        code = proc.wait(timeout=EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        _stop(proc)
        raise AssertionError("редактор не вышел за %s с\n%s" % (EXIT_TIMEOUT, "\n".join(log)))
    return code, log


def _wait_scene(client):
    """Дождаться, пока редактор откроет сцену, и вернуть последний снимок."""
    deadline = time.monotonic() + SCENE_TIMEOUT
    state = {}
    while time.monotonic() < deadline:
        state = client.call("editor_state")
        if isinstance(state, dict) and len(state.get("open_scenes") or []) == 1:
            return state
        time.sleep(0.5)
    return state


def test_editor_branch_answers_and_cleans_up():
    """Редакторская ветка отвечает как редактор, а выход убирает адрес моста."""
    binary = _binary()
    if binary is None:
        pytest.skip("Godot не найден: редакторская ветка остаётся долгом needs_live")

    port_file = _port_file()
    port_file.parent.mkdir(parents=True, exist_ok=True)
    if port_file.exists():
        port_file.unlink()
    SCENE_FILE.write_text(SCENE_TEXT, encoding="utf-8", newline="\n")
    proc = None
    client = None
    try:
        proc, lines, log = _start_editor(binary, SCENE_RES)
        info = _wait_port(port_file, lines, log)
        assert info["protocol"] == 1, info
        assert info["verbs_version"] == verbs_catalog.version(), info
        assert 1 <= info["port"] <= 65535, info

        client = EditorClient(port_file=str(port_file))
        # Плагин поднимается в первом сканировании, а сцена открывается в конце
        # старта редактора - поэтому сначала дожидаемся сцены, иначе гонка.
        state = _wait_scene(client)
        answers = {verb: client.call(verb) for verb in VERBS}
        answers["editor_state"] = state
        for verb, answer in answers.items():
            assert isinstance(answer, dict), verb
            problems = validate(answer, verbs_catalog.result_schema(verb))
            assert problems == [], (verb, problems)

        ping = answers["editor_ping"]
        assert ping["godot"].startswith("4."), ping["godot"]
        assert ping["protocol"] == 1, ping
        assert ping["verbs_version"] == verbs_catalog.version(), ping
        assert ping["uptime_s"] > 0, ping
        assert ping["open_scenes"] == 1, ping

        scenes = state["open_scenes"]
        assert isinstance(scenes, list) and len(scenes) == 1, scenes
        scene = scenes[0]
        assert scene["path"] == SCENE_RES, scene
        assert isinstance(scene["revision"], int), scene
        assert scene["dirty"] is False, scene
        assert isinstance(scene["active"], bool), scene
        # Признак редактора: заглушка `-s` отдаёт здесь `None`, живой редактор -
        # строку (в `--headless --editor` наблюдается `"res://"`, корень проекта).
        assert state["active_scene"] not in (None, ""), state["active_scene"]
        assert isinstance(state["project_hash"], str) and state["project_hash"], state

        selection = answers["editor_selection"]
        assert selection == {"node_path": None, "scene": None, "script": None,
                             "properties": []}, selection

        # --- часть B: живой батч на открытой сцене ---
        # План не пишет: ревизия и `dirty` те же. Применение идёт одним undo-шагом:
        # две операции батча дают ровно +1 к ревизии. Значение действительно
        # изменилось - следующий батч читает его как `before`.
        ops = [_set("Body", "position", {"x": 3, "y": 4}),
               _set("Body", "visible", False)]
        planned = _scene_ops(client, scene["revision"], ops)
        assert planned["applied"] is False, planned
        assert planned["plan_digest"] and planned["would_change"], planned
        assert planned["revision"] == scene["revision"], planned
        quiet = _scene(client)
        assert quiet["revision"] == scene["revision"], quiet
        assert quiet["dirty"] is False, quiet

        applied = _scene_ops(client, scene["revision"], ops, apply=True,
                             plan_digest=planned["plan_digest"],
                             undo_label="agent: B.2")
        assert applied["applied"] is True, applied
        assert applied["applied_revision"] == scene["revision"] + 1, applied
        assert [item["applied"] for item in applied["receipts"]] == [True, True], applied
        assert applied["undo_label"] == "agent: B.2", applied
        dirty = _scene(client)
        assert dirty["revision"] == applied["applied_revision"], dirty
        assert dirty["dirty"] is True, dirty

        # План одноразовый: тот же отпечаток уже не примут. Ревизия берётся
        # текущая (после apply она выросла), иначе раньше проверки плана
        # сработает конфликт ревизии и `stale_plan` не проверить.
        with pytest.raises(AppError) as stale:
            _scene_ops(client, dirty["revision"], ops, apply=True,
                       plan_digest=planned["plan_digest"])
        assert stale.value.kind == "stale_plan", stale.value
        assert (stale.value.details or {}).get("reason") == "stale_plan", stale.value

        # Значение в сцене правда новое: следующий батч читает его как `before`.
        # Сверка ревизии: отпечаток считается для «чужой» ревизии, мост обязан
        # ответить `revision_mismatch`, а сцена при отказе не меняется.
        foreign = dirty["revision"] + 5
        with pytest.raises(AppError) as conflict:
            _scene_ops(client, foreign, ops, apply=True,
                       plan_digest=scene_core.digest_of(SCENE_RES, foreign, ops))
        assert conflict.value.kind == "conflict", conflict.value
        assert (conflict.value.details or {}).get("reason") == "revision_mismatch", (
            conflict.value)
        assert _scene(client) == dirty, "сцена изменилась при отказе ревизии"

        second_ops = [_set("Body", "position", {"x": 7, "y": 8})]
        second_plan = _scene_ops(client, dirty["revision"], second_ops)
        second = _scene_ops(client, dirty["revision"], second_ops, apply=True,
                            plan_digest=second_plan["plan_digest"])
        assert second["applied_revision"] == dirty["revision"] + 1, second
        assert second["changes"][0]["before"] == applied["changes"][0]["after"], (
            "значение не сохранилось", second["changes"], applied["changes"])

        # Сбой на втором шаге (узла нет): типизированный отказ на плане,
        # сцена не менялась - ревизия и `dirty` те же, что до попытки.
        before_failure = _scene(client)
        broken = [_set("Body", "visible", True), _set("NoSuchNode", "visible", True)]
        with pytest.raises(AppError) as failed_plan:
            _scene_ops(client, before_failure["revision"], broken)
        assert failed_plan.value.kind == "invalid_input", failed_plan.value
        details = failed_plan.value.details or {}
        assert details.get("reason") == "plan_invalid", (details,
                                                         chr(10).join(log[-25:]))
        assert _scene(client) == before_failure, "сцена изменилась после отказа"

        # --- B.3: один undo на батч и откат истории ---
        # Сбойный батч выше записей не оставил: опустошение истории снимает
        # ровно два успешных батча (`applied` и `second`), третий откат
        # упирается в пустую историю - это отказ `nothing_to_undo`, не молчание.
        drained = 0
        current = before_failure["revision"]
        while True:
            try:
                step = _undo(client, current)
            except AppError as error:
                assert error.kind == "conflict", error
                assert (error.details or {}).get("reason") == "nothing_to_undo", error
                break
            assert step["undone"] is True, step
            assert step["history_version"] == step["history_version_before"] - 1, step
            current = step["revision"]
            drained += 1
            assert drained <= 5, "история не пустеет"
        assert drained == 2, ("откат снял не два батча", drained)

        # Один undo на батч: две операции одного плана снимаются одним откатом,
        # оба свойства возвращаются к исходным значениям.
        base = _scene(client)
        ops3 = [_set("Body", "position", {"x": 41, "y": 42}),
                _set("Body", "visible", True)]
        plan3 = _scene_ops(client, base["revision"], ops3)
        batch3 = _scene_ops(client, base["revision"], ops3, apply=True,
                            plan_digest=plan3["plan_digest"], undo_label="agent: B.3")
        assert [item["applied"] for item in batch3["receipts"]] == [True, True], batch3
        originals = [item["before"] for item in batch3["changes"]]
        assert len(originals) == 2, batch3

        undo3 = _undo(client, batch3["applied_revision"])
        assert undo3["undone"] is True, undo3
        assert undo3["undo_label"] == "agent: B.3", undo3
        assert undo3["revision"] == batch3["applied_revision"] + 1, undo3
        assert _scene(client)["revision"] == undo3["revision"]

        # Оба свойства вернулись: повторный батч читает те же `before`.
        plan4 = _scene_ops(client, undo3["revision"], ops3)
        batch4 = _scene_ops(client, undo3["revision"], ops3, apply=True,
                            plan_digest=plan4["plan_digest"], undo_label="agent: B.3")
        assert [item["before"] for item in batch4["changes"]] == originals, (
            "откат вернул не оба свойства", batch4["changes"], batch3["changes"])

        # N -> N+1: версия истории растёт на 1 за батч и убывает на 1 за откат.
        # У обоих батчей одна и та же версия до отката, значит каждый добавил
        # ровно одно действие, а откат снял ровно одно.
        assert undo3["history_version"] == undo3["history_version_before"] - 1, undo3
        undo4 = _undo(client, batch4["applied_revision"])
        assert undo4["history_version_before"] == undo3["history_version_before"], (
            undo4, undo3)
        assert undo4["history_version"] == undo3["history_version"], (undo4, undo3)

        # После отката повторный откат снова упирается в пустую историю.
        with pytest.raises(AppError) as twice:
            _undo(client, undo4["revision"])
        assert twice.value.kind == "conflict", twice.value
        assert (twice.value.details or {}).get("reason") == "nothing_to_undo", twice.value

        client.close()
        client = None
    finally:
        if client is not None:
            client.close()
        _stop(proc)
        SCENE_FILE.unlink(missing_ok=True)

    # Уборка адреса: штатный выход редактора обязан удалить `port.json`
    # (`stop()` в `socket_server.gd`). Подложенный «старый» файл не должен
    # пережить запуск - иначе после закрытия редактора клиент пойдёт на мёртвый порт.
    port_file.write_text(json.dumps({"port": 1, "token": "stale", "protocol": 1,
                                     "verbs_version": verbs_catalog.version()}),
                         encoding="utf-8")
    code, log = _run_and_wait(binary, QUIT_FRAMES)
    assert code == 0, "\n".join(log)
    assert not port_file.exists(), "port.json остался после штатного выхода редактора"



def test_scene_undo_refuses_empty_history_and_foreign_revision():
    """Откат истории: пустая история и чужая ревизия - типизированные отказы."""
    binary = _binary()
    if binary is None:
        pytest.skip("Godot не найден: редакторская ветка остаётся долгом needs_live")
    port_file = _port_file()
    SCENE_FILE.write_text(SCENE_TEXT, encoding="utf-8", newline="\n")
    port_file.unlink(missing_ok=True)
    proc = None
    client = None
    try:
        proc, lines, log = _start_editor(binary, SCENE_RES)
        info = _wait_port(port_file, lines, log)
        assert info["verbs_version"] == verbs_catalog.version(), info
        client = EditorClient(port_file=str(port_file))
        scene = _wait_scene(client)["open_scenes"][0]
        assert scene["path"] == SCENE_RES, scene

        # История открытой сцены пуста: откат обязан назвать причину, а не молчать.
        with pytest.raises(AppError) as empty:
            _undo(client, scene["revision"])
        assert empty.value.kind == "conflict", empty.value
        assert (empty.value.details or {}).get("reason") == "nothing_to_undo", empty.value

        # Чужая ревизия: мост не угадывает, он отказывает и сцену не трогает.
        with pytest.raises(AppError) as foreign:
            _undo(client, scene["revision"] + 3)
        assert foreign.value.kind == "conflict", foreign.value
        assert (foreign.value.details or {}).get("reason") == "revision_mismatch", (
            foreign.value)
        assert _scene(client) == scene, "сцена изменилась при отказе истории"

        client.close()
        client = None
    finally:
        if client is not None:
            client.close()
        _stop(proc)
        SCENE_FILE.unlink(missing_ok=True)
        port_file.unlink(missing_ok=True)

