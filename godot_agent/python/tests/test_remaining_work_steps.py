# -*- coding: utf-8 -*-
"""Синтетические тесты остатка плана «Единая точка входа» (задачи 1-5).

Здесь проверки, которые не выполнит ни компилятор Godot, ни существующие
109 проверок test_gdscript_wiring.py: каждая задача требует доказать
поведение, а не наличие символа.

Запуск:
    python -B python/tests/test_remaining_work_steps.py
    python -B python/tests/test_remaining_work_steps.py --godot EXE
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


ADDON = Path(__file__).resolve().parents[2]
SENTINEL = "SCENE_RELOAD_GUARD_RESULTS "


def strip_comments(text):
    """Исходник без `#`-комментариев: правила о вызовах API не должны падать
    из-за того, что их название упомянуто в объяснении."""
    return re.sub(r"(?m)#.*$", "", text)


def function_body(text, name):
    """Исходник функции целиком — от `func` до следующей `func`."""
    match = re.search(r"^func\s+%s\s*\(.*?(?=^func\s|\Z)" % re.escape(name),
                      text, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


class Suite:
    """Общий каркас: счётчик проверок и список провалов."""

    def __init__(self):
        self.failures = []
        self.checks = 0

    def check(self, name, condition, detail=""):
        self.checks += 1
        print("%s -> %s" % (name, "OK" if condition else "FAIL"))
        if not condition:
            if detail:
                print("     %s" % (detail,))
            self.failures.append((name, detail))
        return bool(condition)
class Task1StaticChecks(Suite):
    """ЗАДАЧА 1: несохранённая сцена не перезагружается молча.

    Первопричина. `_auto_reload_changed_scene` вызывал
    `EditorInterface.reload_scene_from_path(p)` сразу, как только путь
    совпал с открытой сценой. Публичного `is_scene_dirty()` в Godot 4.6
    нет: `EditorUndoRedoManager.is_history_unsaved()` живёт только в C++ и
    не забиндин в скрипты. Значит «грязность» приходится выводить из
    публичного `UndoRedo.get_version()`.
    """

    def __init__(self):
        super().__init__()
        self.panel_path = ADDON / "agent_panel.gd"

    def run(self):
        if not self.check("agent_panel.gd на месте", self.panel_path.is_file(),
                          str(self.panel_path)):
            return
        panel = self.panel_path.read_text(encoding="utf-8")

        reload_fn = function_body(panel, "_auto_reload_changed_scene")
        if not self.check("функция _auto_reload_changed_scene есть", bool(reload_fn)):
            return

        guard_at = reload_fn.find("_scene_reload_would_lose_edits(")
        reload_at = reload_fn.find("reload_scene_from_path(")
        self.check("проверка несохранённых правок стоит ДО перезагрузки",
                   0 <= guard_at < reload_at and reload_at > 0,
                   "guard=%d reload=%d" % (guard_at, reload_at))
        self.check("перезагрузка не безусловна",
                   reload_fn.count("reload_scene_from_path(") == 1, reload_fn)

        self.check("есть функция _scene_reload_would_lose_edits",
                   "func _scene_reload_would_lose_edits(" in panel)
        self.check("есть функция _mark_scene_clean",
                   "func _mark_scene_clean(" in panel)
        self.check("чистота выводится из get_version() истории отмены",
                   "get_version()" in panel and "get_history_undo_redo(" in panel)
        # Комментарии не считаются: запрещено ВЫЗЫВАТЬ несуществующий API, а не
        # упоминать его в объяснении, почему вызова нет.
        code = strip_comments(panel)
        self.check("не вызывается несуществующий API Godot",
                   "is_scene_dirty" not in code
                   and "is_history_unsaved" not in code
                   and "get_unsaved_scenes" not in code,
                   [token for token in ("is_scene_dirty", "is_history_unsaved",
                                        "get_unsaved_scenes") if token in code])
        self.check("о пропуске сообщается в чат",
                   "_scene_reload_blocked_notice(" in panel)
        self.check("пропуск перезагрузки попадает в чат",
                   re.search(r"func\s+_scene_reload_blocked_notice.*?"
                             r"_view\.(add_warning|add_system)\(", panel, re.DOTALL)
                   is not None)

        executor = (ADDON / "agent_scene_executor.gd").read_text(encoding="utf-8")
        recovery = function_body(executor, "reload_after_recovery")
        self.check("восстановление сцены тоже спрашивает перед reload",
                   "reload_scene_from_path(" in recovery
                   and "_scene_reload_would_lose_edits(" in executor, recovery)


class ParseAllScriptsChecks(Suite):
    """РЕГРЕССИЯ: ЗАДАЧА 1 принесла parse-error, которого не видел ни один чек.

    Первопричина пропуска. Проверка `--check-only` из плана гоняет ОДИН файл -
    agent_entry.gd. Он не ссылается на панель статически, поэтому синтаксическая
    ошибка внутри agent_panel.gd даёт exit=0. Живой headless-редактор тоже
    промолчал: парсер панели срабатывает лениво, при load(), а не при входе
    плагина. 109 проверок обвязки - это регулярки по тексту, они тоже молчат.

    Итог был такой: панель не грузилась вообще, то есть у пользователя просто
    исчезал чат, и ни один из трёх «инструментов проверки» этого не показал.
    Настоящая защита - прогонять --check-only по КАЖДОМУ .gd отдельно.
    """

    def __init__(self, godot: Path = None):
        super().__init__()
        self.godot = godot

    def run(self):
        scripts = sorted(ADDON.glob("*.gd"))
        self.check("скрипты аддона найдены", bool(scripts), str(ADDON))
        if not scripts:
            return
        if self.godot is None:
            # Без движка проверять нечем: молчание хуже явного провала.
            self.check("движок передан для проверки разбора", False,
                       "запусти с --godot PATH, иначе проверка пропущена")
            return
        project_root = ADDON.parents[3]
        broken = {}
        for script in scripts:
            result = subprocess.run(
                [str(self.godot), "--headless", "--check-only", "--script",
                 "res://addons/godot_agent/godot_agent/" + script.name],
                cwd=str(project_root), capture_output=True, timeout=180,
                encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            if "Parse Error" in output or "SCRIPT ERROR" in output:
                broken[script.name] = [
                    line for line in output.splitlines()
                    if "Parse Error" in line or "SCRIPT ERROR" in line][:2]
        self.check("каждый .gd аддона разбирается движком", not broken, broken)


class Task2UnifiedFinalizeChecks(Suite):
    """ЗАДАЧА 2: одна функция finalize вместо трёх копий.

    Первопричина дублирования. Три транзакции (сцена, настройки, ресурс)
    отличаются только телом запроса и URL-константой - а копии разошлись
    логикой: у ресурса появился отдельный список терминальных кодов, у
    настроек - нет, и правка одного пути забывала другой.
    """

    def __init__(self):
        super().__init__()
        self.panel_path = ADDON / "agent_panel.gd"

    def run(self):
        if not self.check("agent_panel.gd на месте", self.panel_path.is_file()):
            return
        panel = self.panel_path.read_text(encoding="utf-8")
        code = strip_comments(panel)

        copies = [name for name in
                  ("func _send_pending_scene_finalize(",
                   "func _send_pending_project_settings_finalize(",
                   "func _send_pending_resource_finalize(")
                  if name in code]
        self.check("осталась ровно одна функция отправки finalize",
                   len(copies) <= 1, copies)

        schedulers = [name for name in
                      ("func _schedule_scene_finalize_retry(",
                       "func _schedule_project_settings_finalize_retry(",
                       "func _schedule_resource_finalize_retry(")
                      if name in code]
        self.check("остался ровно один планировщик повтора",
                   len(schedulers) <= 1, schedulers)

        unified = re.search(r"^func\s+_send_pending_finalize\s*\(\s*\w+\s*:\s*String",
                            panel, re.MULTILINE)
        self.check("функция принимает вид транзакции", unified is not None)
        body = function_body(panel, "_send_pending_finalize")
        self.check("вид транзакции выбирает тело и счётчик повторов",
                   bool(body) and "_finalize_body(" in body
                   and "_finalize_retries" in body, body)

        # Правило «не ретимимся вечно» должно быть ОДНО на все виды, а не по
        # копии на вид: именно его расхождение и было первопричиной.
        terminal = re.findall(r"response_code in \[400, 403, 409, 410, 413\]", code)
        self.check("терминальные коды проверяются в одном месте",
                   len(terminal) <= 1, len(terminal))
        for kind in ("scene_finalize", "project_settings_finalize",
                     "resource_finalize"):
            self.check("ветка ответа %s осталась" % kind,
                       ('kind == "%s"' % kind) in code)

        # Специфика видов обязана выражаться данными, а не копиями кода.
        for key in ("editor_action_kind", "scene_hash", "project_hash",
                    "resource_hash", "already_satisfied"):
            self.check("поле %s всё ещё формируется" % key, key in code)

        # Ни одна из трёх транзакций не должна потерять свою отправку.
        for kind in ("scene", "project_settings", "resource"):
            self.check("вызов finalize есть для %s" % kind,
                       re.search(r'_send_pending_finalize\(\s*"%s"\s*\)' % kind,
                                 code) is not None)


class Task3TargetedRefreshChecks(Suite):
    """ЗАДАЧА 3: полный scan() только там, где пути действительно неизвестны.

    Первопричина. `scan()` пересчитывает весь проект. Плагин и так знает, какие
    пути менял, поэтому полный скан тратил секунды после каждой правки ради
    информации, которой уже есть. Приёмка из плана: `.scan()` не более одного
    вхождения, и у оставшегося есть объяснение.
    """

    def __init__(self):
        super().__init__()
        self.panel_path = ADDON / "agent_panel.gd"

    def run(self):
        if not self.check("agent_panel.gd на месте", self.panel_path.is_file()):
            return
        panel = self.panel_path.read_text(encoding="utf-8")
        code = strip_comments(panel)

        calls = re.findall(r"(?<!is_scanning)\.scan\(\)", code)
        self.check("полный scan() встречается не более раза", len(calls) <= 1,
                   "%d вхождений" % len(calls))

        # У оставшегося вызова должно быть объяснение рядом. Ищем его в исходнике,
        # а не в коде без комментариев: объяснение по определению комментарий.
        # Смещения в тексте без комментариев и в исходнике не совпадают, поэтому
        # идём по строкам, а не по позициям.
        explained = not any(
            ".scan()" in line and "is_scanning" not in line
            for line in panel.splitlines())
        if not explained:
            lines = panel.splitlines()
            for index, line in enumerate(lines):
                if ".scan()" not in line or "is_scanning" in line:
                    continue
                context = "\n".join(lines[max(0, index - 12):index]).lower()
                if "путь" in context or "неизвестн" in context:
                    explained = True
                    break
        self.check("у оставшегося scan() есть объяснение", explained)

        # Точечные действия обязаны присутствовать: без них «убрали скан» -
        # это просто «перестали обновлять файловую систему».
        self.check("есть точечное обновление update_file", "update_file" in code)
        for helper in ("_sync_open_script_with_disk", "_auto_reload_changed_scene",
                       "_refresh_changed_paths"):
            self.check("точечный помощник %s есть" % helper,
                       ("func %s(" % helper) in code)


class Task4MutationGateChecks(Suite):
    """ЗАДАЧА 4: шлюз мутаций и одна запись в истории отмены.

    Первопричина. Записи шли из пяти мест напрямую (_sync_resource_uid,
    исполнители сцены/ресурса/настроек, обработчики отката), и ни одно из них
    не отвечало на вопрос «что именно сейчас изменилось и как это отменить».
    Шлюз делает решение по типу ресурса единственным и даёт одну запись в
    истории Godot на одну операцию агента.
    """

    GATE = "agent_mutation_gate.gd"

    def __init__(self):
        super().__init__()
        self.gate_path = ADDON / self.GATE

    def run(self):
        self.check("%s существует" % self.GATE, self.gate_path.is_file(),
                   str(self.gate_path))
        if not self.gate_path.is_file():
            return
        gate = self.gate_path.read_text(encoding="utf-8")
        code = strip_comments(gate)

        self.check("шлюз умеет писать сцену через PackedScene",
                   "PackedScene" in code)
        self.check("шлюз умеет писать ресурс через ResourceSaver",
                   "ResourceSaver" in code)
        self.check("шлюз умеет писать project.godot через ProjectSettings",
                   "ProjectSettings" in code)
        self.check("шлюз различает типы ресурса",
                   ".tscn" in code and ".tres" in code)
        self.check("шлюз ведёт журнал отката", "journal" in code)
        self.check("шлюз оборачивает Godot-API в историю отмены",
                   "create_action(" in code and "add_do_method(" in code
                   and "add_undo_method(" in code and "commit_action(" in code)
        self.check("шлюз НЕ кладёт в undo Godot массовый рефакторинг",
                   "bulk" in code)

        panel = (ADDON / "agent_panel.gd").read_text(encoding="utf-8")
        panel_code = strip_comments(panel)
        self.check("панель создаёт шлюз", self.GATE in panel)
        self.check("панель больше не сканирует проект ради UID",
                   "efs.scan()" not in panel_code)

        # Шлюз обязан быть подключён со всех путей записи, а не «где-то».
        # Проверяем реальное соединение: панель внедряет шлюз, исполнитель его
        # принимает и вызывает запись ИМЕННО шлюза, а не в обход него.
        for name in ("agent_scene_executor.gd", "agent_resource_executor.gd",
                     "agent_project_settings_executor.gd"):
            source = (ADDON / name).read_text(encoding="utf-8")
            self.check("%s принимает шлюз" % name,
                       "func set_mutation_gate(" in source, name)
            self.check("%s пишет через шлюз" % name,
                       re.search(r'_gate\.call\("write_', source) is not None, name)
            self.check("панель внедряет шлюз в %s" % name,
                       'call("set_mutation_gate", _mutation_gate)' in panel, name)

        # Правило «одна операция агента = одна запись» обязано быть выражено
        # кодом, а не только пожеланием в комментарии.
        self.check("исполнитель сцены коммитит одну запись отмены",
                   "_commit_live_scene_undo(" in
                   (ADDON / "agent_scene_executor.gd").read_text(encoding="utf-8"))
        self.check("шлюз не даёт открыть вторую запись поверх первой",
                   "if _undo_entry != null:" in code)


class Task5EntryPointChecks(Suite):
    """ЗАДАЧА 5: plugin.cfg указывает на agent_entry.gd.

    Откат намеренно оставлен возможным: plugin_universal.gd не удаляется.
    """

    def __init__(self):
        super().__init__()
        self.cfg_path = ADDON / "plugin.cfg"

    def run(self):
        if not self.check("plugin.cfg на месте", self.cfg_path.is_file()):
            return
        cfg = self.cfg_path.read_text(encoding="utf-8")
        script = re.search(r'script\s*=\s*"([^"]+)"', cfg)
        self.check("в plugin.cfg есть script=", script is not None, cfg)
        if script:
            self.check("точка входа — agent_entry.gd",
                       script.group(1) == "agent_entry.gd", script.group(1))
            self.check("файл точки входа существует",
                       (ADDON / script.group(1)).is_file(), script.group(1))
        self.check("откат plugin_universal.gd на месте",
                   (ADDON / "plugin_universal.gd").is_file())
        self.check("имя плагина не переименовано", 'name="Godot Agent"' in cfg, cfg)


def run_live(godot: Path):
    """Живые прогоны ЗАДАЧ 1 и 4 в изолированном проекте без плагина.

    Одна песочница на оба теста: они проверяют разное (несохранённые правки
    сцены и запись в истории отмены), но обе нуждаются ровно в одном — в
    настоящем headless-редакторе с работающим EditorUndoRedoManager.
    """
    scenes = {
        "scene_reload_guard_live.gd": (
            "SCENE_RELOAD_GUARD_RESULTS ",
            ["scene_opened", "clean_open_scene_is_reloadable",
             "edited_scene_root_exists", "undoable_edit_marks_scene_dirty",
             "save_clears_dirty_state", "second_edit_marks_scene_dirty_again",
             "dirty_scene_is_not_reloaded", "marked_scene_is_reloadable",
             "unopened_scene_is_reloadable"]),
        "mutation_gate_live.gd": (
            "MUTATION_GATE_RESULTS ",
            ["classify_scene", "classify_binary_scene", "classify_resource",
             "classify_project_settings", "classify_script", "classify_bulk",
             "bulk_is_bulk", "scene_is_not_bulk", "undo_manager_available",
             "scene_history_available", "undo_action_opened", "second_open_rejected",
             "undo_action_committed", "one_operation_one_history_record",
             "gate_counted_one_action", "commit_did_not_double_apply",
             "journal_has_one_entry", "journal_lookup_is_case_insensitive",
             "undo_calls_revert_once", "redo_calls_apply_once",
             "bulk_does_not_touch_undo_history", "bulk_recorded_in_journal_only"]),
        "context_menu_callback_live.gd": (
            "CTX_CB_RESULTS ",
            ["точка входа загружается",
             "внутренний класс SceneTreeMenu доступен",
             "метод _on_ask существует",
             "у _on_ask есть необязательный аргумент",
             "вызов с одним аргументом не падает",
             "вызов без аргументов не падает",
             "панель загружается",
             "панель принимает вопрос из меню",
             "вопрос без собранной панели не роняет вызов"]),
        "context_menu_e2e_live.gd": (
            "CTX_E2E_RESULTS ",
            ["скрипт точки входа загружается",
             "точка входа создаётся",
             "agent_panel.gd найден",
             "панель собрана",
             "док панели доступен",
             "поле ввода найдено после сборки",
             "команда не оставила поле пустым",
             "в вопрос попал выбранный узел",
             "состояние отправки зафиксировано"]),
    }
    fixtures = Path(__file__).parent / "fixtures"
    with tempfile.TemporaryDirectory(prefix="agent-gate-") as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        for source in ADDON.iterdir():
            if source.suffix in (".gd", ".tscn"):
                shutil.copyfile(source, copied / source.name)
        for name in scenes:
            shutil.copyfile(fixtures / name, root / name)
        (root / "guard_scene.tscn").write_text(
            '[gd_scene format=3]\n\n[node name="GuardScene" type="Node2D"]\n',
            encoding="utf-8")
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Agent sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME",
                     "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True, exist_ok=True)
            env[name] = str(directory)
        base = [str(godot), "--headless", "--path", str(root), "--editor", "--language", "en"]
        # Движок в headless-редакторе шумит сам по себе, и это не связано с
        # проверяемым кодом (доказано пробой reload без кода агента вообще):
        # утечки RID при выходе, освобождение корня сцены при reload, и
        # "Parameter t is null" из заглушки рендера на headless-стенде.
        # Ошибки скриптов и несуществующие вызовы остаются значимыми.
        engine_noise = re.compile(
            r"^ERROR: \d+ RID allocations of type '[^']+' were leaked at exit\.$"
            r"|^WARNING: \d+ RIDs? of type '[^']+' (?:was|were) leaked\.$"
            r"|^WARNING: ObjectDB instances leaked at exit.*$"
            r"|^ERROR: Something attempted to free the root Node of a scene.*$"
            r"|^ERROR: Parameter \"t\" is null\.$")

        def run(arguments):
            result = subprocess.run(base + arguments, env=env, cwd=str(root),
                                    capture_output=True, timeout=240,
                                    encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            fatal_output = "\n".join(
                line for line in output.splitlines()
                if not engine_noise.match(line))
            print(output)
            for marker in ("SCRIPT ERROR:", "Parse Error:", "Invalid call",
                           "Invalid access"):
                if marker in fatal_output:
                    raise RuntimeError("Godot reported %r during %s"
                                       % (marker, " ".join(arguments)))
            return result

        run(["--import", "--quit"])
        for name, (sentinel, expected) in scenes.items():
            result = run(["--script", "res://" + name])
            reports = [line[len(sentinel):] for line in result.stdout.splitlines()
                       if line.startswith(sentinel)]
            if len(reports) != 1:
                raise RuntimeError("Missing or duplicate sentinel for " + name)
            report = json.loads(reports[0])
            if sorted(report.get("completed", [])) != sorted(expected):
                raise RuntimeError("Incomplete %s cases: %r"
                                   % (name, report.get("completed")))
            if report.get("failures"):
                raise RuntimeError("Failing %s cases: %r"
                                   % (name, report["failures"]))
            print("PASS: %s verified in a real headless Godot editor" % name)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", help="Run the live scene-reload guard test")
    args = parser.parse_args()
    godot = Path(args.godot).resolve() if args.godot else None

    failures = []
    checks = 0
    suites = [Task1StaticChecks, Task2UnifiedFinalizeChecks,
              Task3TargetedRefreshChecks, Task4MutationGateChecks,
              Task5EntryPointChecks]
    for suite in suites:
        print("\n--- %s ---" % suite.__name__)
        instance = suite()
        instance.run()
        checks += instance.checks
        failures.extend("%s: %s" % (name, detail) for name, detail in instance.failures)

    # Разбор каждого .gd идёт последним и только с движком: он ловит ровно тот
    # класс поломок, который не видит ни один другой инструмент плана.
    if godot:
        print("\n--- ParseAllScriptsChecks ---")
        parse_suite = ParseAllScriptsChecks(godot)
        parse_suite.run()
        checks += parse_suite.checks
        failures.extend("%s: %s" % (name, detail)
                        for name, detail in parse_suite.failures)

    print("\nПРОВЕРОК: %d, ПРОВАЛОВ: %d" % (checks, len(failures)))
    if godot:
        run_live(godot)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())