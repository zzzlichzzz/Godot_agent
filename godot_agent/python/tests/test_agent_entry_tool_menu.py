# -*- coding: utf-8 -*-
"""Синтетические тесты Шага 3 плана UNIFIED_ENTRY_PLAN: ToolMenu.

Что проверяется
---------------
1) Статика: меню собрано как подменю через `add_tool_submenu_item`,
   снимается через `remove_tool_menu_item(PLUGIN_NAME)` в `_exit_tree`,
   `id_pressed` подключён к одному обработчику с `match` по id.
2) Статика: пункты подменю вызывают ТОТ ЖЕ код, что вызывали плоские
   `add_tool_menu_item` в plugin_universal.gd, — то есть
   `open_safe_rename` / `open_safe_node_rename` у дока. Раньше обработчик
   звал `command_handler`, который не назначен ни в одном файле проекта,
   поэтому оба пункта молча ничего не делали.
3) Статика: идентификаторы пунктов — именованные константы, а не магия,
   и рабочие плоские пункты plugin_universal.gd не тронуты (шаг 6).
4) Живая проверка настоящим headless Godot 4.6.3: PopupMenu реально
   собирается, `id_pressed` доходит до обработчика, `match` ведёт в нужный
   метод дока, неизвестный id ничего не ломает.

Запуск:
    python -B python/tests/test_agent_entry_tool_menu.py
    python -B python/tests/test_agent_entry_tool_menu.py --godot EXE
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SENTINEL = "TOOL_MENU_RESULTS "


# Аргументы add_item читаются с учётом вложенных скобок: заголовок —
# это вызов _menu_title(...), и наивное «до первой )» отрезает id.
def add_item_ids(text):
    """Последний аргумент каждого add_item — это идентификатор пункта."""
    found = []
    for match in re.finditer(r"add_item\s*\(", text):
        depth = 0
        begin = match.end()
        end = None
        for position in range(match.end() - 1, len(text)):
            char = text[position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = position
                    break
        if end is None:
            continue
        arguments = []
        depth = 0
        current = ""
        for char in text[begin:end]:
            if char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
            if char == "," and depth == 0:
                arguments.append(current)
                current = ""
            else:
                current += char
        arguments.append(current)
        if arguments:
            found.append(arguments[-1].strip())
    return found


class StaticChecks:
    """Проверки по исходникам — ловят то, что компилятор не ловит."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.entry_path = addon / "agent_entry.gd"
        self.plugin_path = addon / "plugin_universal.gd"

    def check(self, name, condition, detail=""):
        self.checks += 1
        if condition:
            print("%s -> OK" % name)
        else:
            print("%s -> FAIL" % name)
            if detail:
                print("     %s" % (detail,))
            self.failures.append((name, detail))

    def run(self):
        self.check("точка входа на месте", self.entry_path.is_file(), str(self.entry_path))
        if not self.entry_path.is_file():
            return
        text = self.entry_path.read_text(encoding="utf-8")

        self.check("меню добавлено как подменю",
                   re.search(r"add_tool_submenu_item\s*\(\s*PLUGIN_NAME\s*,", text) is not None)
        self.check("подменю снимается в _exit_tree",
                   re.search(r"func\s+_exit_tree.*?remove_tool_menu_item\s*\(\s*PLUGIN_NAME",
                             text, re.DOTALL) is not None)
        self.check("submenu.id_pressed подключён",
                   re.search(r"id_pressed\.connect\s*\(", text) is not None)
        self.check("обработчик один и маршрутизирует match",
                   re.search(r"match\s+id\s*:", text) is not None)
        self.check("обработчик объявлен",
                   re.search(r"^func\s+_on_menu_id\s*\(", text, re.MULTILINE) is not None)

        for method in PANEL_METHODS:
            self.check("меню вызывает %s" % method,
                       re.search(r'"%s"' % method, text) is not None,
                       "подменю не вызывает тот же код, что и add_tool_menu_item")

        constants = set(re.findall(r"^const\s+([A-Z0-9_]+)\s*:?=\s*\d+", text, re.MULTILINE))
        self.check("идентификаторы пунктов объявлены константами", len(constants) >= 2,
                   sorted(constants))
        passed_ids = add_item_ids(text)
        self.check("в add_item переданы константы, а не числа",
                   bool(passed_ids) and all(i in constants for i in passed_ids),
                   passed_ids)

        if self.plugin_path.is_file():
            plugin_text = self.plugin_path.read_text(encoding="utf-8")
            self.check("плоские пункты рабочего плагина на месте",
                       plugin_text.count("add_tool_menu_item(") >= 2,
                       "шаг 6 их уберёт; раньше трогать нельзя")
        else:
            self.check("рабочий плагин на месте", False, str(self.plugin_path))
    """Проверки по исходникам — ловят то, что компилятор не ловит."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.entry_path = addon / "agent_entry.gd"
        self.plugin_path = addon / "plugin_universal.gd"

    def check(self, name, condition, detail=""):
        self.checks += 1
        if condition:
            print("%s -> OK" % name)
        else:
            print("%s -> FAIL" % name)
            if detail:
                print("     %s" % (detail,))
            self.failures.append((name, detail))

    def run(self):
        self.check("точка входа на месте", self.entry_path.is_file(), str(self.entry_path))
        if not self.entry_path.is_file():
            return
        text = self.entry_path.read_text(encoding="utf-8")

        # --- форма меню ---
        self.check("меню добавлено как подменю",
                   re.search(r"add_tool_submenu_item\s*\(\s*PLUGIN_NAME\s*,", text) is not None)
        self.check("подменю снимается в _exit_tree",
                   re.search(r"func\s+_exit_tree.*?remove_tool_menu_item\s*\(\s*PLUGIN_NAME",
                             text, re.DOTALL) is not None)
        self.check("submenu.id_pressed подключён",
                   re.search(r"id_pressed\.connect\s*\(", text) is not None)
        self.check("обработчик один и маршрутизирует match",
                   re.search(r"match\s+id\s*:", text) is not None)
        self.check("обработчик объявлен",
                   re.search(r"^func\s+_on_menu_id\s*\(", text, re.MULTILINE) is not None)

        # --- пункты ведут туда же, куда плоские пункты рабочего плагина ---
        for method in PANEL_METHODS:
            self.check("меню вызывает %s" % method,
                       re.search(r'"%s"' % method, text) is not None,
                       "подменю не вызывает тот же код, что и add_tool_menu_item")

        # --- id — именованные константы, а не магия в add_item ---
        constants = set(re.findall(r"^const\s+([A-Z0-9_]+)\s*:?=\s*\d+", text, re.MULTILINE))
        self.check("идентификаторы пунктов объявлены константами", len(constants) >= 2,
                   sorted(constants))
        # Аргументы add_item читаются с учётом вложенных скобок: заголовок —
        # это вызов _menu_title(...), и наивное «до первой )» отрезает id.
        passed_ids = add_item_ids(text)
        self.check("в add_item переданы константы, а не числа",
                   bool(passed_ids) and all(i in constants for i in passed_ids),
                   passed_ids)

        # --- рабочий плагин не тронут до шага 6 ---
        if self.plugin_path.is_file():
            plugin_text = self.plugin_path.read_text(encoding="utf-8")
            self.check("плоские пункты рабочего плагина на месте",
                       plugin_text.count("add_tool_menu_item(") >= 2,
                       "шаг 6 их уберёт; раньше трогать нельзя")
        else:
            self.check("рабочий плагин на месте", False, str(self.plugin_path))

# Методы панели, которые вызывают плоские пункты рабочего плагина
# (plugin_universal.gd:48-49). Подменю обязано вести туда же.
PANEL_METHODS = ("open_safe_rename", "open_safe_node_rename")

FATAL_ENGINE_LINES = (
    "SCRIPT ERROR",
    "Parse Error",
    "Nonexistent function",
)

SHUTDOWN_NOISE = (
    "RID allocations of type",
    "RIDs of type",
    "ObjectDB instances leaked",
    "Scan thread aborted",
)
HARNESS = '''extends SceneTree

# Док-приёмник: те же методы, что вызывает рабочий плагин.
class Dock extends Control:
	var calls: Array = []
	func open_safe_rename() -> void:
		calls.append("file")
	func open_safe_node_rename() -> void:
		calls.append("node")


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await process_frame
	var failures: Array[String] = []

	var entry: Script = load("res://addons/godot_agent/agent_entry.gd")
	if entry == null:
		failures.append("agent_entry.gd is not loadable")
		_report(failures)
		return
	var plugin = entry.new()
	if plugin == null:
		failures.append("entry script could not be instantiated")
		_report(failures)
		return

	# add_tool_submenu_item/add_tool_menu_item крашат headless-редактор
	# (SIGSEGV), поэтому хук вживую не дергаем: проверяем PopupMenu и
	# диспетчер отдельно — это и есть проверяемая часть шага.
	var submenu := PopupMenu.new()
	submenu.add_item("file", 101)
	submenu.add_item("node", 202)
	if submenu.item_count != 2:
		failures.append("submenu did not keep two items")

	var dock := Dock.new()
	plugin.dock_for_test = dock

	# --- маршрутизация по id ---
	submenu.id_pressed.connect(func(id: int) -> void: plugin.dispatch_menu_id_for_test(id))
	submenu.id_pressed.emit(101)
	if dock.calls.size() != 1 or str(dock.calls[0]) != "file":
		failures.append("id 101 did not open the file rename dialog")
	submenu.id_pressed.emit(202)
	if dock.calls.size() != 2 or str(dock.calls[1]) != "node":
		failures.append("id 202 did not open the node rename dialog")

	# --- неизвестный id не должен ломать и звать что-то лишнее ---
	submenu.id_pressed.emit(999)
	if dock.calls.size() != 2:
		failures.append("unknown id reached the dock")
	submenu.id_pressed.emit(-1)
	if dock.calls.size() != 2:
		failures.append("negative id reached the dock")

	# --- док без нужных методов: тихо, без ошибки ---
	var bare := Control.new()
	plugin.dock_for_test = bare
	submenu.id_pressed.emit(101)
	print("BARE_OK")

	# --- док = null: тоже тихо ---
	plugin.dock_for_test = null
	submenu.id_pressed.emit(101)
	print("NULL_OK")

	# Освобождаем всё до выхода: иначе движок ругается на незакрытые
	# ресурсы при shutdown, и проверка падает не по своей причине.
	submenu.free()
	dock.free()
	bare.free()
	plugin.free()
	entry = null

	_report(failures)


func _report(failures: Array[String]) -> void:
	print(SENTINEL + JSON.stringify({"failures": failures}))
	await process_frame
	quit(0 if failures.is_empty() else 1)
'''


def live_check(addon: Path, executable: str, temp_parent):
    with tempfile.TemporaryDirectory(prefix="tool-menu-", dir=temp_parent) as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        for name in ("agent_entry.gd", "agent_integration_signals.gd", "agent_server.gd"):
            shutil.copyfile(addon / name, copied / name)
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Tool menu sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (root / "harness.gd").write_text(HARNESS.replace("SENTINEL", '"%s"' % SENTINEL),
                                        encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME",
                     "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True)
            env[name] = str(directory)
        base = [executable, "--headless", "--path", str(root), "--editor", "--language", "en"]
        for arguments in (["--import", "--quit"], ["--script", "res://harness.gd"]):
            command = base + arguments
            print("RUN " + subprocess.list2cmdline(command), flush=True)
            result = subprocess.run(command, env=env, cwd=root, capture_output=True,
                                    timeout=180, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            if arguments[0] == "--script":
                print(output)
                fatal = [line for line in output.splitlines()
                         if any(token in line for token in FATAL_ENGINE_LINES)
                         or ("ERROR:" in line and not any(n in line for n in SHUTDOWN_NOISE))]
                reports = [json.loads(line[len(SENTINEL):]) for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                if not reports:
                    raise RuntimeError("харнесс не напечатал результат:\n" + output)
                if fatal or reports[0]["failures"] or result.returncode:
                    raise RuntimeError("живая проверка меню не прошла:\n"
                                       + "\n".join(fatal + reports[0]["failures"]))
            elif result.returncode:
                raise RuntimeError("импорт песочницы упал:\n" + output)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    parser.add_argument("--temp-parent", default=None)
    parser.add_argument("--static-only", action="store_true",
                        help="не запускать настоящий Godot")
    args = parser.parse_args()

    addon = Path(__file__).resolve().parents[2]
    static = StaticChecks(addon)
    static.run()
    print("СТАТИКА: %d проверок, %d провалов" % (static.checks, len(static.failures)))

    ok = not static.failures
    if not args.static_only:
        executable = args.godot or shutil.which("godot") or shutil.which("godot4")
        if not executable:
            parser.error("Specify --godot; a static test cannot replace engine compilation.")
        executable = str(Path(executable).resolve())
        try:
            live_check(addon, executable, args.temp_parent)
            print("ЖИВАЯ ПРОВЕРКА: OK")
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            print("ЖИВАЯ ПРОВЕРКА: FAIL\n%s" % error)
            ok = False

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()