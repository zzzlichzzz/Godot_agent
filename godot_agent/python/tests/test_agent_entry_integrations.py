# -*- coding: utf-8 -*-
"""Синтетические тесты Шага 1 плана UNIFIED_ENTRY_PLAN: EditorSignals.

Что проверяется
---------------
1) Статика: `agent_integration_signals.gd` существует, наследует RefCounted,
   принимает EditorPlugin в конструкторе, умеет attach()/detach(), хранит
   Callable для отписки, подписывается ровно на 6 сигналов EditorPlugin.
2) Статика: арность обработчика совпадает с реальной сигнатурой сигнала
   движка. Это ровно тот класс ошибок, который gd_api_check НЕ ловит:
   обработчик `_on_script_changed(_script)` подписывается на сигнал без
   аргументов и падает в рантайме при первом же emit.
3) Статика: agent_entry.gd создаёт интеграцию в _enter_tree и отключает
   её в _exit_tree.
4) Живая проверка настоящим headless Godot: attach() даёт ровно 6 связей,
   повторный attach() не создаёт дублей, detach() обнуляет все подписки,
   а emit каждого из 6 сигналов НЕ даёт ошибок вызова обработчика.

Запуск:
    python -B python/tests/test_agent_entry_integrations.py
    python -B python/tests/test_agent_entry_integrations.py --godot EXE
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


SENTINEL = "EDITOR_SIGNALS_RESULTS "


class StaticChecks:
    """Проверки по исходникам — ловят то, что компилятор не ловит."""

    def __init__(self, addon: Path):
        self.addon = addon
        self.failures = []
        self.checks = 0
        self.signals_path = addon / "agent_integration_signals.gd"
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
        self.check("файл интеграции сигналов существует", self.signals_path.is_file(),
                   str(self.signals_path))
        self.check("точка входа на месте", self.entry_path.is_file(), str(self.entry_path))
        if not self.signals_path.is_file():
            return
        text = self.signals_path.read_text(encoding="utf-8")
        entry = self.entry_path.read_text(encoding="utf-8")

        self.check("наследует RefCounted",
                   re.search(r"^extends\s+RefCounted\s*$", text, re.MULTILINE) is not None)
        self.check("конструктор принимает EditorPlugin",
                   re.search(r"func\s+_init\s*\(\s*plugin\s*:\s*EditorPlugin", text) is not None)
        self.check("есть attach()", re.search(r"^func\s+attach\s*\(", text, re.MULTILINE) is not None)
        self.check("есть detach()", re.search(r"^func\s+detach\s*\(", text, re.MULTILINE) is not None)
        self.check("отписка реализована через disconnect()", ".disconnect(" in text)
        self.check("ссылки на Callable хранятся в поле",
                   re.search(r"^var\s+_[A-Za-z0-9_]*(callable|subscription)", text, re.MULTILINE) is not None)
        self.check("attach() вызывается в _enter_tree",
                   re.search(r"func\s+_enter_tree.*?\.attach\s*\(", entry, re.DOTALL) is not None)
        self.check("detach() вызывается в _exit_tree",
                   re.search(r"func\s+_exit_tree.*?\.detach\s*\(", entry, re.DOTALL) is not None)

        # Подписка должна идти по сигналам EditorPlugin, а не через строки.
        self.check("подписка идёт по объектам, а не по строковым именам",
                   'emit_signal("' not in text and 'connect("' not in text)

        for signal_name, arity in EDITOR_PLUGIN_SIGNALS.items():
            handler = HANDLER_FOR[signal_name]
            if signal_name not in text:
                self.check("сигнал %s упомянут" % signal_name, False)
                continue
            if handler not in text:
                self.check("обработчик %s объявлен" % handler, False)
                continue
            match = re.search(r"^func\s+%s\s*\(([^)]*)\)" % re.escape(handler), text, re.MULTILINE)
            params = [p for p in match.group(1).split(",") if p.strip()] if match else []
            self.check("арность %s равна %d" % (handler, arity), len(params) == arity,
                       "ожидалось %d, в коде %d" % (arity, len(params)))
            # Подписка выглядит как _bind(<сигнал>, <обработчик>) либо
            # как signal.connect(<обработчик>) — обе формы валидны,
            # важно лишь, что обработчик передан туда. Скобки обязательны:
            # без них `%` связывается раньше `or` и в re.search уходит
            # только первая альтернатива.
            direct = r"\.connect\s*\(\s*%s\b" % re.escape(handler)
            via_bind = r"_bind\s*\(\s*[^,]+,\s*%s\b" % re.escape(handler)
            self.check("%s подписан" % signal_name,
                       re.search("(?:%s)|(?:%s)" % (direct, via_bind), text) is not None)

        # Старый ошибочный обработчик не должен остаться в точке входа.
        old = re.search(r"^func\s+_on_script_changed\s*\(\s*_[A-Za-z0-9_]+\s*:\s*Script",
                        entry, re.MULTILINE)
        self.check("в точке входа нет обработчика script_changed с лишним аргументом", old is None)

# Реальные сигнатуры сигналов EditorPlugin в Godot 4.6.3, сняты запросом
# get_signal_list() у живого экземпляра (не из памяти и не из документации).
EDITOR_PLUGIN_SIGNALS = {
    "script_changed": 0,
    "scene_changed": 1,
    "scene_saved": 1,
    "resource_saved": 1,
    "project_settings_changed": 0,
    "editor_state_changed": 0,
}

HANDLER_FOR = {
    "script_changed": "_on_script_changed",
    "scene_changed": "_on_scene_changed",
    "scene_saved": "_on_scene_saved",
    "resource_saved": "_on_resource_saved",
    "project_settings_changed": "_on_project_settings_changed",
    "editor_state_changed": "_on_editor_state_changed",
}

# Шум, который headless-редактор оставляет при любом shutdown.
# Его наличие не связано с проверяемым поведением.
SHUTDOWN_NOISE = (
    "RID allocations of type",
    "RIDs of type",
    "ObjectDB instances leaked",
    "Scan thread aborted",
)
HARNESS = '''extends SceneTree

class StandIn extends EditorPlugin:
\tpass


func _initialize() -> void:
\tcall_deferred("_run")


func _run() -> void:
\tawait process_frame
\tvar failures: Array[String] = []
\tvar plugin := StandIn.new()
\tvar script: Script = load("res://addons/godot_agent/agent_integration_signals.gd")
\tif script == null:
\t\tfailures.append("agent_integration_signals.gd is not loadable")
\t\t_report(failures)
\t\treturn
\tvar integration = script.new(plugin)
\tif integration == null:
\t\tfailures.append("constructor did not accept the plugin")
\t\t_report(failures)
\t\treturn

\t# --- attach: ровно шесть подписок ---
\tintegration.attach()
\tvar after_attach: Dictionary = _connections(plugin)
\tfor name in NAMES:
\t\tif int(after_attach.get(name, -1)) != 1:
\t\t\tfailures.append("attach left connections on " + str(name) + ": " + str(after_attach.get(name, -1)))
\tif after_attach.size() != COUNT:
\t\tfailures.append("attach subscribed to unexpected signals: " + str(after_attach.keys()))

\t# --- повторный attach не обязан дублировать подписки ---
\tintegration.attach()
\tvar after_second: Dictionary = _connections(plugin)
\tfor name in NAMES:
\t\tif int(after_second.get(name, -1)) != 1:
\t\t\tfailures.append("second attach duplicated " + str(name))

\t# --- detach обнуляет всё ---
\tintegration.detach()
\tvar after_detach: Dictionary = _connections(plugin)
\tfor name in after_detach:
\t\tif int(after_detach[name]) != 0:
\t\t\tfailures.append("detach left connections on " + str(name) + ": " + str(after_detach[name]))

\t# --- emit после detach больше не зовёт обработчики ---
\t_emit_all(plugin)

\t# --- attach/detach переживают повторный цикл ---
\tintegration.attach()
\tintegration.detach()
\tintegration.detach()
\tvar after_cycle: Dictionary = _connections(plugin)
\tfor name in after_cycle:
\t\tif int(after_cycle[name]) != 0:
\t\t\tfailures.append("second detach left connections on " + str(name) + ": " + str(after_cycle[name]))

\t# --- emit под живой подпиской: обработчики должны принять реальные аргументы ---
\tintegration.attach()
\t_emit_all(plugin)
\tvar final_counts: Dictionary = _connections(plugin)
\tfor name in NAMES:
\t\tif int(final_counts.get(name, -1)) != 1:
\t\t\tfailures.append("reattach lost " + str(name))

\t_report(failures)


func _connections(plugin: Object) -> Dictionary:
\tvar counts := {}
\tfor name in NAMES:
\t\tcounts[name] = plugin.get_signal_connection_list(name).size()
\treturn counts


func _emit_all(plugin: Object) -> void:
\tplugin.emit_signal("script_changed")
\tplugin.emit_signal("scene_changed", Node.new())
\tplugin.emit_signal("scene_saved", "res://probe.tscn")
\tplugin.emit_signal("resource_saved", Resource.new())
\tplugin.emit_signal("project_settings_changed")
\tplugin.emit_signal("editor_state_changed")


func _report(failures: Array[String]) -> void:
\tprint(SENTINEL + JSON.stringify({"failures": failures}))
\tawait process_frame
\tquit(0 if failures.is_empty() else 1)
'''


def build_harness():
    """Харнесс — сценарий на живом движке вместо разбора исходников."""
    names = json.dumps(sorted(EDITOR_PLUGIN_SIGNALS))
    return (HARNESS
            .replace("SENTINEL + ", '"%s" + ' % SENTINEL)
            .replace("NAMES", names)
            .replace("COUNT", str(len(EDITOR_PLUGIN_SIGNALS))))


def live_check(addon: Path, executable: str, temp_parent):
    with tempfile.TemporaryDirectory(prefix="editor-signals-", dir=temp_parent) as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        # Интеграция сигналов не тянет за собой другие модули аддона,
        # поэтому в песочницу уходит ровно один файл.
        shutil.copyfile(addon / "agent_integration_signals.gd",
                        copied / "agent_integration_signals.gd")
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Editor signals sandbox"\n'
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
                # Любая строка про ошибку вызова обработчика — это ровно тот баг,
                # ради которого написан шаг 1: подпись не совпала с сигнатурой.
                fatal = [line for line in output.splitlines()
                         if "SCRIPT ERROR" in line or "Parse Error" in line
                         or "Error calling from signal" in line
                         or ("ERROR:" in line and not any(n in line for n in SHUTDOWN_NOISE))]
                reports = [json.loads(line[len(SENTINEL):]) for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                if not reports:
                    raise RuntimeError("харнесс не напечатал результат:\n" + output)
                if fatal or reports[0]["failures"] or result.returncode:
                    raise RuntimeError("живая проверка подписок не прошла:\n"
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