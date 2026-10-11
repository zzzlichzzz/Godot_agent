# -*- coding: utf-8 -*-
"""Синтетические проверки ЗАДАЧИ 3: перехват переименования узла человеком.

Автоматически эту задачу целиком не проверить — окончательное слово за живым
редактором (test_remaining_work_steps.py --godot). Здесь закрепляется то, что
проверяемо статикой: подписка на Node.renamed со снимком имён, подавление
собственных переименований, режим scripts_only и уведомление в панели.

Запуск:
    python -B python/tests/test_node_rename_intercept.py
"""
import argparse
from pathlib import Path
import re
import sys


class StaticChecks:
    """Статика перехвата: сигналы, панель, точка входа, локализация."""

    def __init__(self, addon):
        self.addon = addon
        self.failures = []
        self.checks = 0

    def check(self, name, condition, detail=""):
        self.checks += 1
        print("%s -> %s" % (name, "OK" if condition else "FAIL"))
        if not condition and detail:
            print("     %s" % (detail,))
        if not condition:
            self.failures.append((name, detail))

    @staticmethod
    def function_body(text, name):
        match = re.search(r"^func\s+%s\s*\(.*?(?=^func\s|\Z)" % re.escape(name),
                          text, re.MULTILINE | re.DOTALL)
        return match.group(0) if match else ""

    def run(self):
        signals_path = self.addon / "agent_integration_signals.gd"
        panel_path = self.addon / "agent_panel.gd"
        entry_path = self.addon / "agent_entry.gd"
        locale_path = self.addon / "agent_locale.gd"
        for name, path in (("модуль сигналов", signals_path),
                           ("панель", panel_path),
                           ("точка входа", entry_path),
                           ("локализация", locale_path)):
            self.check("%s на месте" % name, path.is_file(), str(path))
        if self.failures:
            return
        signals = signals_path.read_text(encoding="utf-8")
        panel = panel_path.read_text(encoding="utf-8")
        entry = entry_path.read_text(encoding="utf-8")
        locale = locale_path.read_text(encoding="utf-8")

        # --- модуль сигналов: подписка на renamed + снимок имён -----------
        self.check("модуль сигналов умеет принять обработчик перехвата",
                   "func set_node_rename_handler(" in signals)
        watch = self.function_body(signals, "_watch_node")
        self.check("_watch_node подписывается на Node.renamed",
                   "renamed.connect(" in watch, watch)
        self.check("_watch_node запоминает имя в снимке",
                   "_node_names" in watch, watch)
        self.check("_watch_node отписывается при уходе узла со сцены",
                   "tree_exiting.connect(" in watch, watch)
        scene_changed = self.function_body(signals, "_on_scene_changed")
        self.check("_on_scene_changed пересобирает снимок имён",
                   "_watch_subtree(" in scene_changed, scene_changed)
        # Обход обязан быть рекурсивным: плоский get_children(true) видел
        # только прямых детей корня, и переименование узла глубже терялось.
        self.check("_on_scene_changed обходит ПОДДЕРЕВО, а не только детей корня",
                   "root.get_children(true)" not in scene_changed, scene_changed)
        watch_tree = self.function_body(signals, "_watch_subtree")
        self.check("_watch_subtree рекурсивен и подписывает каждый узел",
                   "_watch_subtree(" in watch_tree and "_watch_node(" in watch_tree,
                   watch_tree)
        # Узел, добавленный в уже открытую сцену, тоже обязан попасть под
        # наблюдение — иначе его переименование пройдёт незамеченным.
        self.check("_watch_node подписывается на child_entered_tree",
                   "child_entered_tree.connect(" in watch, watch)
        self.check("подписка на child_entered_tree учтена для detach",
                   "node.child_entered_tree, \"callable\"" in watch, watch)
        added = self.function_body(signals, "_on_child_entered_tree")
        self.check("новый узел сразу попадает под наблюдение поддеревом",
                   "_watch_subtree(" in added, added)
        renamed_handler = self.function_body(signals, "_on_node_renamed")
        self.check("_on_node_renamed достаёт ПРЕЖНЕЕ имя из снимка",
                   "_node_names.get(" in renamed_handler, renamed_handler)
        self.check("_on_node_renamed зовёт обработчик панели",
                   "_node_handler.call(" in renamed_handler, renamed_handler)


        # --- панель: очередь, scripts_only, подавление, уведомление --------
        self.check("панель принимает событие переименования узла",
                   "func handle_scene_node_renamed(" in panel)
        self.check("перехват идёт через очередь, как перемещения файлов",
                   "_node_rename_queue" in panel
                   and "func _process_node_rename_queue(" in panel)
        sync_body = self.function_body(panel, "_send_node_rename_sync")
        self.check("запрос идёт через узел связи коротким каналом",
                   "post_now(\"node_rename_sync\"" in panel, sync_body)
        # Тело запроса собирается ровно в одном месте — _node_rename_body:
        # так preview и apply гарантированно получают идентичный запрос.
        body_fn = self.function_body(panel, "_node_rename_body")
        self.check("регистрация scripts_only=true в теле запроса",
                   "\"scripts_only\": true" in body_fn, body_fn)
        self.check("прежнее имя передаётся серверу (двойное переименование)",
                   "\"previous_name\"" in body_fn, body_fn)
        # ЗАДАЧА 3 (повторные переименования): node_path строится по ДИСКОВОМУ
        # ПУТИ (.tscn не переписывается), панель помнит пары «редактор → диск».
        # Лист не годится: при двух узлах с одним именем сервер отказывается
        # искать узел по листу («имя неоднозначно»).
        self.check("в тело запроса попадает дисковый ПУТЬ узла (disk_path)",
                   "disk_path" in body_fn and "disk_leaf" not in body_fn, body_fn)
        self.check("синхронизация ищет дисковый путь и в истории перехватов",
                   "_node_disk_path_for_sync(" in sync_body, sync_body)
        # ВНУК уже переименованного предка: точного ключа в истории нет (в
        # редакторе "ActorPanel/StatsLabel", на диске "PlayerPanel/StatsLabel").
        # Без подъёма к самому длинному предку-префиксу перехват такого узла
        # молча пропускался («нет узла — синхронизация пропущена»).
        disk_fn = self.function_body(panel, "_node_disk_path_for_sync")
        self.check("путь внука переводится через предка: редактор → диск",
                   "best_disk" in disk_fn and "begins_with(" in disk_fn
                   and "_scene_has_node_path(" in disk_fn, disk_fn)
        self.check("дисковая история — карта путей, лист отставляется в прошлое",
                   "_node_path_with_leaf(" in panel and "_node_leaf_for_sync(" not in panel,
                   sync_body)
        self.check("есть подсчёт одноимённых узлов (признак неоднозначного листа)",
                   "_scene_node_name_count(" in panel)
        self.check("пути узлов считаются из секций .tscn с parent",
                   "_scene_node_paths(" in panel and '"[node "' in panel)
        apply_body = self.function_body(panel, "_on_node_rename_apply_response")
        self.check("после успешного применения запоминается пара имён",
                   "_note_node_disk_name(" in apply_body, apply_body)
        # Одноимённые узлы — молчать нельзя: «нет ссылок» неотличимо от
        # правки «не того» узла.
        sync_response = self.function_body(panel, "_on_node_rename_sync_response")
        self.check("для не-уникального имени есть предупреждение в панели",
                   "non_unique" in sync_response and "add_warning(" in sync_response,
                   sync_response)
        self.check("не-уникальность помечается до отправки запроса",
                   'item["non_unique"]' in sync_body, sync_body)
        self.check("после применения есть уведомление в панели",
                   "add_agent_message(" in apply_body, apply_body)
        self.check("сцена НЕ перезагружается авто-перезагрузкой при перехвате",
                   "_auto_reload_changed_scene(" not in apply_body, apply_body)
        self.check("есть флаг подавления собственных переименований",
                   "_node_rename_suppress" in panel)
        dialog_body = self.function_body(panel, "_on_safe_node_rename_apply")
        self.check("диалог безопасного переименования тоже подавляет перехват",
                   "_node_rename_suppress" in dialog_body, dialog_body)
        short_body = self.function_body(panel, "_on_short_response")
        for kind in ("node_rename_sync", "node_rename_apply"):
            self.check("короткий канал раздаёт ответ %s" % kind,
                       "\"%s\"" % kind in short_body, short_body)

        # --- точка входа: связка сигналов и панели -------------------------
        self.check("точка входа прокидывает обработчик в модуль сигналов",
                   "set_node_rename_handler(" in entry)

        # --- локализация: ключ уведомления в обоих языках ------------------
        ru_start = locale.find("const RU :=")
        en_start = locale.find("const EN :=")
        ru = locale[ru_start:en_start] if ru_start >= 0 and en_start > ru_start else ""
        en = locale[en_start:] if en_start >= 0 else ""
        for lang, block in (("ru", ru), ("en", en)):
            self.check("ключ node_rename_intercept_success есть в %s" % lang,
                       "node_rename_intercept_success" in block)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    addon = Path(__file__).resolve().parents[2]
    static = StaticChecks(addon)
    static.run()
    print("СТАТИКА: %d проверок, %d провалов" % (static.checks, len(static.failures)))
    raise SystemExit(0 if not static.failures else 1)


if __name__ == "__main__":
    main()

