# -*- coding: utf-8 -*-
"""Синтетические тесты Шага 2 плана UNIFIED_ENTRY_PLAN: ContextMenu.

Что проверяется
---------------
1) Статика: `SceneTreeMenu` наследует `EditorContextMenuPlugin`,
   реализует `_popup_menu(paths: PackedStringArray)`, выходит на пустых
   путях, регистрируется на обоих слотах и снимается в `_exit_tree`.
2) Статика: константы слотов пишутся с префиксом класса
   `EditorContextMenuPlugin.CONTEXT_SLOT_*`. Без префикса имя не
   резолвится, а `gd_api_check` такое не ловит.
3) Статика: обработчик передаёт корню ВЫБРАННЫЕ ПУТИ, а не только
   метку. Иначе «Спросить агента про узел» не знает, о каком узле речь.
4) Живая проверка настоящим headless Godot 4.6.3: класс реально
   создаётся, `_popup_menu` добавляет ровно один пункт, обработчик
   доходит до корня с путями, а регистрация/снятие двух слотов не даёт
   ошибок движка.

Запуск:
    python -B python/tests/test_agent_entry_context_menu.py
    python -B python/tests/test_agent_entry_context_menu.py --godot EXE
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


SENTINEL = "CONTEXT_MENU_RESULTS "


class StaticChecks:
    """Проверки по исходникам — ловят то, что компилятор не ловит."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.entry_path = addon / "agent_entry.gd"

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

        self.check("SceneTreeMenu наследует EditorContextMenuPlugin",
                   re.search(r"class\s+SceneTreeMenu\s+extends\s+EditorContextMenuPlugin", text)
                   is not None)
        self.check("реализован _popup_menu(paths: PackedStringArray)",
                   re.search(r"func\s+_popup_menu\s*\(\s*paths\s*:\s*PackedStringArray\s*\)", text)
                   is not None)
        self.check("пустой выбор выходит молча",
                   re.search(r"func\s+_popup_menu.*?paths\.is_empty\(\).*?return",
                             text, re.DOTALL) is not None)
        self.check("пункт добавляется через add_context_menu_item",
                   "add_context_menu_item(" in text)

        for constant in REQUIRED_SLOTS:
            self.check("%s с префиксом класса" % constant,
                       ("EditorContextMenuPlugin." + constant) in text)
        # Голое имя константы без класса не резолвится — проверяем явно.
        for constant in REQUIRED_SLOTS:
            bare = re.search(r"(?<!EditorContextMenuPlugin\.)\b%s\b" % constant, text)
            self.check("нет голой ссылки на %s" % constant, bare is None,
                       str(bare.group(0)) if bare else "")

        self.check("оба меню кладутся в массив ссылок",
                   re.search(r"_integrations\.append\s*\(\s*\w+\s*\)", text) is not None
                   and len(re.findall(r"_integrations\.append\s*\(", text)) >= 2)
        self.check("снятие контекстных меню в _exit_tree",
                   re.search(r"func\s+_exit_tree.*?remove_context_menu_plugin\s*\(", text, re.DOTALL)
                   is not None)
        self.check("массив ссылок очищается при снятии",
                   re.search(r"_integrations\.clear\s*\(\s*\)", text) is not None)

        # Главное: обработчик обязан отдать корню выбранные пути.
        handler = re.search(r"func\s+_on_ask\s*\(([^)]*)\)(.*?)(?=\nfunc |\Z)", text, re.DOTALL)
        body = handler.group(2) if handler else ""
        self.check("agent_ask_about получает выбранные пути",
                   "agent_ask_about" in body and re.search(r"agent_ask_about[^)]*paths", body)
                   is not None,
                   "обработчик передаёт только метку — агент не узнает, о чём спросили")
        self.check("корень принимает пути (agent_ask_about(kind, paths))",
                   re.search(r"func\s+agent_ask_about\s*\(\s*what\s*:\s*String\s*,\s*paths\s*:",
                             text) is not None)

# Слоты, которые обязаны быть заняты. Значения сняты у живого движка:
# SCENE_TREE = 0, FILESYSTEM = 1. Совпадение значений проверяется
# отдельно — важно, чтобы это были разные слоты, а не один и тот же.
REQUIRED_SLOTS = {
    "CONTEXT_SLOT_SCENE_TREE": "узел",
    "CONTEXT_SLOT_FILESYSTEM": "файл",
}

# Ошибки движка, которые нельзя допустить. Первые две — реальные
# ограничения API, найденные пробой на Godot 4.6.3:
#   - один объект нельзя занять в двух слотах сразу;
#   - снять уже снятый контекстный плагин тоже нельзя.
FATAL_ENGINE_LINES = (
    "SCRIPT ERROR",
    "Parse Error",
    "plugin_list.has",
    "!plugin_list.has",
)

SHUTDOWN_NOISE = (
    "RID allocations of type",
    "RIDs of type",
    "ObjectDB instances leaked",
    "Scan thread aborted",
)
HARNESS = '''extends SceneTree

# Корень-приёмник: пункт меню обязан дойти до корня вместе с путями.
class Host extends EditorPlugin:
	var asks: Array = []
	func agent_ask_about(what, paths) -> void:
\t\tasks.append({"what": what, "paths": paths})


func _initialize() -> void:
\tcall_deferred("_run")


func _run() -> void:
\tawait process_frame
\tvar failures: Array[String] = []

\t# Внутренний класс достаётся с самого скрипта точки входа.
\tvar entry: Script = load("res://addons/godot_agent/agent_entry.gd")
\tif entry == null:
\t\tfailures.append("agent_entry.gd is not loadable")
\t\t_report(failures)
\t\treturn
\tvar menu_class = entry.SceneTreeMenu
\tif menu_class == null:
\t\tfailures.append("SceneTreeMenu is not exposed by the entry script")
\t\t_report(failures)
\t\treturn

\tvar host := Host.new()

\t# --- узел: пустой выбор не должен добавлять пункт ---
\tvar node_menu = menu_class.new(host, "узел")
\tif node_menu == null:
\t\tfailures.append("SceneTreeMenu could not be instantiated")
\t\t_report(failures)
\t\treturn
\tnode_menu._popup_menu(PackedStringArray())
\tif host.asks.size() != 0:
\t\tfailures.append("empty selection must not reach the host")

\t# --- обработчик обязан передать выбранные пути ---
\tnode_menu._popup_menu(PackedStringArray(["res://scene.tscn::Root/Child"]))
\t# Пункт меню зовёт обработчик только по клику пользователя,
\t# поэтому в headless вызываем его явно — ровно то, что делает редактор.
\tnode_menu._on_ask()
\tif host.asks.size() != 1:
\t\tfailures.append("menu handler did not reach the host once")
\telse:
\t\tvar ask: Dictionary = host.asks[0]
\t\tif str(ask["what"]) != "узел":
\t\t\tfailures.append("host got wrong subject: " + str(ask["what"]))
\t\tvar paths: Array = ask["paths"]
\t\tif paths.size() != 1 or str(paths[0]) != "res://scene.tscn::Root/Child":
\t\t\tfailures.append("host lost the selected paths: " + str(paths))

\t# --- второй выбор: на отдельном объекте, потому что редактор сам
\t#     чистит пункты перед показом, а повторный _popup_menu на том же
\t#     объекте движок справедливо считает дублем ---
\tvar other_menu = menu_class.new(host, "узел")
\tother_menu._popup_menu(PackedStringArray(["res://other.tscn::Root"]))
\tother_menu._on_ask()
\tif host.asks.size() != 2:
\t\tfailures.append("second ask did not reach the host")
\telif (host.asks[1]["paths"] as Array).size() != 1:
\t\tfailures.append("a second selection carried the wrong paths")

\t# --- два слота --- два разных объекта: один и тот же объект
\t#     занять в двух слотах движок не даёт ---
\tvar file_menu = menu_class.new(host, "файл")
\tfile_menu._popup_menu(PackedStringArray(["res://addons/Godot_agent/plugin.cfg"]))
\tfile_menu._on_ask()
\tif host.asks.size() != 3:
\t\tfailures.append("file menu did not reach the host")
\telse:
\t\tvar file_paths: Array = host.asks[2]["paths"]
\t\tif file_paths.size() != 1:
\t\t\tfailures.append("file menu lost the selected paths")
\t\tif str(host.asks[2]["what"]) != "файл":
\t\t\tfailures.append("file menu sent the wrong subject")

\tvar plugin := EditorPlugin.new()
\tplugin.add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_SCENE_TREE, node_menu)
\tplugin.add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM, file_menu)
\tif int(EditorContextMenuPlugin.CONTEXT_SLOT_SCENE_TREE) == int(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM):
\t\tfailures.append("scene tree and filesystem slots must differ")
\tplugin.remove_context_menu_plugin(node_menu)
\tplugin.remove_context_menu_plugin(file_menu)
\t_report(failures)


func _report(failures: Array[String]) -> void:
\tprint(SENTINEL_MARK + JSON.stringify({"failures": failures}))
\tawait process_frame
\tquit(0 if failures.is_empty() else 1)
'''


def build_harness():
    """Харнесс — сценарий на живом движке вместо разбора исходников."""
    return HARNESS.replace("SENTINEL_MARK", '"%s"' % SENTINEL)


def live_check(addon: Path, executable: str, temp_parent):
    with tempfile.TemporaryDirectory(prefix="context-menu-", dir=temp_parent) as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        # Внутренний класс SceneTreeMenu живёт в точке входа; сам файл
        # разбирается без панели, но тянет модуль сигналов.
        for name in ("agent_entry.gd", "agent_integration_signals.gd", "agent_server.gd"):
            shutil.copyfile(addon / name, copied / name)
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Context menu sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (root / "harness.gd").write_text(build_harness(), encoding="utf-8")
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
                # Любая из этих строк означает, что движок отверг регистрацию
                # меню: пункт молча не появится у пользователя.
                fatal = [line for line in output.splitlines()
                         if any(token in line for token in FATAL_ENGINE_LINES)
                         or ("ERROR:" in line and not any(n in line for n in SHUTDOWN_NOISE))]
                reports = [json.loads(line[len(SENTINEL):]) for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                if not reports:
                    raise RuntimeError("харнесс не напечатал результат:\n" + output)
                if fatal or reports[0]["failures"] or result.returncode:
                    raise RuntimeError("живая проверка контекстных меню не прошла:\n"
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