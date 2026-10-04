# -*- coding: utf-8 -*-
"""Синтетика Этапа 1 «Гранулярность отказа» — вариант (Б), флаг allow_unverified.

Требование, которое зафиксировано этим файлом:

  * `allow_unverified` НЕ в действии (дефолт движка) -> поведение прежнее:
    недоказанная ссылка отменяет переименование (strict). Это защищает
    сторонние скрипты и MCP-клиентов, которые флаг не передают.
  * `allow_unverified: true` (его шлёт панель, когда галочка в настройках
    стоит) -> доказанные И недоказанные ссылки переименовываются, а каждая
    недоказанная попадает в отчёт с путём, координатами и ПРИЧИНОЙ, по
    которой доказать её не удалось.

Ключевая честность: недоказанная ссылка переименовывается, но ОБЯЗАТЕЛЬНО
показывается. Иначе это молчаливая правка, ради которой весь этап и затевался.

Красный сейчас по делу: поля allow_unverified нет в _validate_action (287-314),
счётчиков renamed_count/unverified_count нет в отчёте (1676-1682), группировки
отчёта по причинам нет. Регресс (47 существующих тестов) обязан остаться зелёным.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from godot_tools import symbol_refactor
from minilich import ml_project_index


PLAYER = """class_name Player
extends Node2D

func hit() -> void:
\tpass
"""

# Прямой наследник: `extends Player` доказуемо связан с нашим class_name.
SUBCLASS = """extends Player

func take_damage(amount: int) -> int:
\treturn amount - 1
"""

# Доказанная ссылка: ресивер типизирован явно (тип берётся из _typed_receivers).
TYPED = """extends Node

var unit: Player
"""

# Посторонний файл с ОДНОЙ недоказанной ссылкой: ресивер target не типизирован.
# Именно её при новом режиме мы переименовываем и показываем в отчёте.
UNPROVEN = """extends Node

func fire(target):
\ttarget.spawn(Player)
"""

# Динамическая ссылка по строке: вызов API Godot по имени. Её нельзя ни
# доказать, ни переписать, поэтому она обязана остаться отказом при любом
# значении allow_unverified (иначе проект гарантированно падает в рантайме).
# Локальная переменная, названная как класс. Раньше такая ссылка попадала в
# недоказанные, и это давало безопасный ОТКАЗ. С переименованием недоказанных
# она обязана молча пропускаться: иначе `var Enemy = 1` рядом с `return Enemy`
# — это уже не наш символ, и код ломается.
SHADOW_OF_CLASS = """extends Node

func other() -> int:
\tvar Player = 1
\treturn Player
"""

# НЕДОКАЗУЕМАЯ строковая ссылка: имя ЧЛЕНА объекта по строке.
# ВНИМАНИЕ: здесь НЕльзя писать ClassDB.instantiate("X") — с Этапом 5 такой
# вызов признан доказуемым (API принимает имя класса) и переименовывается
# вместе с классом, а strict больше не отказывает. Подробности — в
# test_rename_class_name_strings.
DYNAMIC = ("extends Node\n\nfunc make(node: Node) -> Node:\n"
           "\treturn node.call(\"Player\")\n")

# Объявление нашего символа. Тень НЕ может быть в этом же файле: там два
# объявления с одним именем, и _locate_declaration справедливо ругается
# LocatorError ещё ДО анализа ссылок — это другой случай.
DECLARATION = """extends Node

var score := 0

func add() -> int:
\tscore += 1
\treturn score
"""

# Тень в постороннем файле: одноимённая локальная переменная. Это доказанно
# ДРУГАЯ сущность (ветка 1534) — молча пропускается и в недоказанные не
# попадает. Проверено замером: guard.gd остаётся байт-в-байт прежним.
SHADOW = """extends Node

func helper() -> int:
\tvar score = 9
\treturn score
"""

UNPROVEN_SCORE = """extends Node

func fire(target):
\ttarget.spawn(score)
"""
# __APPEND__
class GranularityBase(unittest.TestCase):
    """Общий контракт этапа для включённого allow_unverified."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_granularity_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER)
        self._reindex()

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r", encoding="utf-8") as handle:
            return handle.read()

    def _reindex(self):
        # Кэш индекса живёт между тестами: без сброса следующий тест получил бы
        # разбор ПРЕДЫДУЩЕГО временного проекта и падал бы не по делу.
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(self.root)

    def _action(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar",
                  "allow_unverified": True}
        action.update(extra)
        return action

    def _mixed_project(self):
        """Доказанные ссылки (наследник + типизированный ресивер) + ОДНА
        недоказанная ссылка в постороннем файле."""
        self._write("src/slime.gd", SUBCLASS)
        self._write("src/typed.gd", TYPED)
        self._write("src/arena.gd", UNPROVEN)
        self._reindex()

    # --- 1.1 переименование ПРОХОДИТ и включает недоказанную ссылку ---
    def test_unverified_reference_is_renamed_too(self):
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn("var unit: Avatar", self._read("src/typed.gd"))
        self.assertIn("extends Avatar", self._read("src/slime.gd"))
        # Ключевое требование: недоказанная ссылка ТОЖЕ переименована.
        self.assertIn("target.spawn(Avatar)", self._read("src/arena.gd"))
        self.assertNotIn("Player", self._read("src/arena.gd"))

    # --- 1.2 БЕЗ ФЛАГА поведение прежнее: отказ, ничего не изменено ---
    def test_without_flag_strict_still_refuses(self):
        """Дефолт движка обязан остаться strict: сторонний скрипт или MCP-клиент
        не передаёт флаг и не должен молча получить небезопасное переименование."""
        self._mixed_project()
        before = self._read("src/typed.gd")
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action(allow_unverified=None))
        message = str(ctx.exception)
        # Отказ обязан называть недоказанные ссылки и показывать их: раньше
        # здесь было слово «неоднозначные», теперь термин «недоказанные» —
        # он точнее, потому что доказуемо-чужие ссылки отказом не являются.
        self.assertIn("недоказанные", message)
        self.assertIn("res://src/arena.gd", message)
        self.assertEqual(self._read("src/typed.gd"), before)
        self.assertIn("class_name Player", self._read("src/player.gd"))

    def test_explicit_false_also_refuses(self):
        """Снятая галочка — это явное False, и оно обязано вести себя как strict,
        а не как «мусорное значение, которое мы не проверили»."""
        self._mixed_project()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(
                self.root, self._action(allow_unverified=False))

    # --- 1.3 недоказанная ссылка ПОКАЗАНА с путём, координатами и причиной ---
    def test_unverified_is_reported_with_reason(self):
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        notes = prepared.get("unverified_references") or []
        self.assertTrue(notes, "недоказанная ссылка обязана быть в отчёте")
        joined = " ".join(str(item) for item in notes)
        self.assertIn("res://src/arena.gd", joined)
        self.assertTrue(re.search(r"res://src/arena\.gd:\d+", joined), joined)
        # Причина обязана быть названа: «почему не доказали» — это то, что
        # позволяет пользователю решить, доверять ли такой правке.
        self.assertRegex(joined.lower(), r"тип|receiver|вызов|не доказан|причин")

    def test_unverified_reaches_public_payload(self):
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        public = symbol_refactor.public_prepared(prepared)
        self.assertTrue(public.get("unverified_references"))
        self.assertIs(public.get("allow_unverified"), True)

    # --- 1.4 счётчики ---
    def test_report_has_renamed_and_unverified_counters(self):
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        public = symbol_refactor.public_prepared(prepared)
        for payload in (prepared, public):
            self.assertIn("renamed_count", payload, list(payload.keys()))
            self.assertIn("unverified_count", payload, list(payload.keys()))
            self.assertIsInstance(payload["unverified_count"], int)
            self.assertEqual(payload["unverified_count"], 1, payload)

    def test_renamed_counter_counts_the_unproven_one(self):
        """Счётчик обязан отражать факт, включая переименованное без
        доказательства, иначе отчёт недооценивает объём правки."""
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        count = symbol_refactor.public_prepared(prepared)["renamed_count"]
        # Объявление + extends + тип + недоказанная ссылка в arena.gd.
        self.assertGreaterEqual(count, 4, count)

    # __APPEND_2__
# --- 1.5 нет недоказанных ссылок => отчёт без пустых секций ---
    def test_clean_project_has_no_empty_sections(self):
        self._write("src/typed.gd", TYPED)
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        public = symbol_refactor.public_prepared(prepared)
        self.assertEqual(public.get("unverified_references") or [], [])
        self.assertEqual(public.get("unverified_count"), 0, public)
        import main
        public["action"] = "rename_symbol"
        # ВНИМАНИЕ без риска — шум: пользователь не должен видеть тревогу,
        # когда переименовано всё и проверено всё.
        self.assertNotIn("ВНИМАНИЕ", main._describe_action(public))

    # --- 1.6 РЕГРЕССИЯ: тень остаётся нетронутой и НЕ попадает в отчёт ---
    def _shadow_project(self):
        self._write("src/unit.gd", DECLARATION)
        self._write("src/guard.gd", SHADOW)
        self._write("src/arena.gd", UNPROVEN_SCORE)
        self._reindex()

    def _score_action(self):
        return {"action": "rename_symbol", "kind": "variable",
                "declaration": "res://src/unit.gd:3",
                "old_name": "score", "new_name": "points",
                "allow_unverified": True}

    def test_local_shadow_is_never_renamed(self):
        """Тень доказанно другая сущность. Новый режим не имеет права её ни
        переименовать, ни показать как недоказанную — это была бы ложь."""
        self._shadow_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._score_action())
        notes = prepared.get("unverified_references") or []
        self.assertFalse([n for n in notes if "guard.gd" in str(n)], notes)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("var points := 0", self._read("src/unit.gd"))
        self.assertIn("return points", self._read("src/unit.gd"))
        self.assertIn("var score = 9", self._read("src/guard.gd"))

    def test_shadow_file_is_not_written_at_all(self):
        self._shadow_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._score_action())
        self.assertNotIn("res://src/guard.gd",
                         [item["path"] for item in prepared["files"]])

    def test_local_variable_named_like_class_is_never_renamed(self):
        """РЕГРЕСС, найденный сквозной проверкой на трёх уровнях наследования.

        Локальная переменная `var Player = 1` — доказанно другая сущность.
        Раньше она попадала в недоказанные и давала безопасный отказ, но с
        переименованием недоказанных она была бы ПЕРЕИМЕНОВАНА, а её объявление
        — нет. Получался сломанный код: `var Player = 1` и `return Avatar`.
        """
        self._write("src/guard.gd", SHADOW_OF_CLASS)
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        guard = self._read("src/guard.gd")
        self.assertIn("var Player = 1", guard)
        self.assertIn("return Player", guard)
        self.assertNotIn("Avatar", guard)

    # --- Аудит: жёсткие проверки не должны ослабляться флагом ---
    def test_flag_keeps_name_collision_guard(self):
        self._write("src/other.gd", "class_name Avatar\nextends Node\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))

    def test_flag_respects_write_policy(self):
        self._write("addons/pack/helper.gd", TYPED)
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertNotIn("res://addons/pack/helper.gd",
                         [item["path"] for item in prepared["files"]])

    def test_flag_does_not_touch_dynamic_reference(self):
        """ВАЖНО. `node.call("Player")` — это НЕ неполнота анализа, а обращение
        к движку по имени члена. Такой вызов нельзя ни доказать, ни переписать:
        после переименования он гарантированно падает в рантайме. Поэтому флаг
        недоказанных ссылок его НЕ касается.

        Раньше здесь стоял ClassDB.instantiate("Player"), но с Этапом 5 он
        признан доказуемым и переименовывается вместе с классом."""
        self._write("src/loader.gd", DYNAMIC)
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertEqual(getattr(ctx.exception, "code", ""), "unsafe")
        self.assertIn("class_name Player", self._read("src/player.gd"))

    def test_flag_keeps_probable_semantics(self):
        """probable не трогаем: он и раньше разрешал и недоказанные, и динамику."""
        self._mixed_project()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(mode="probable", allow_unverified=None))
        self.assertEqual(prepared.get("mode"), "probable")

    # __APPEND_2__
class FlagTypeStrictness(unittest.TestCase):
    """Отдельный класс: тип флага — это защита strict от тихого ослабления."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_flagtype_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER)
        self._write("src/arena.gd", UNPROVEN)
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(self.root)

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _action(self, value):
        return {"action": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": "Avatar",
                "allow_unverified": value}

    def test_string_false_is_rejected(self):
        """Модель отдаёт JSON, и "false" — это НЕ False в Python:
        bool("false") is True. Если не проверить тип, модель, сказав «строго»,
        получит терпимость молча, и пользователь об этом не узнает."""
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("false"))
        self.assertIn("allow_unverified", str(ctx.exception))

    def test_other_junk_never_enables_relaxation(self):
        for bogus in (1, 0, "true", "yes", 1.0, [], {}, "0"):
            with self.subTest(value=bogus):
                try:
                    prepared = symbol_refactor.prepare_rename(
                        self.root, self._action(bogus))
                except symbol_refactor.RenameError:
                    continue
                # Если НЕ отклонено — поведение обязано остаться строгим.
                self.assertEqual(
                    prepared.get("unverified_references") or [], [],
                    "allow_unverified=%r не должен включать переименование" % (bogus,))

    def test_absent_flag_keeps_strict(self):
        action = self._action(True)
        del action["allow_unverified"]
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, action)


class HighLevelPath(unittest.TestCase):
    """Путь от агента: project_command -> rename_symbol должен знать про флаг."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_flag_hl_")
        self.addCleanup(shutil.rmtree, self.root, True)
        path = os.path.join(self.root, "project.godot")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("config_version=5\n")

    def test_high_level_action_accepts_flag(self):
        import high_level_actions
        result = high_level_actions.compile_action(self.root, {
            "action": "project_command", "command": {
                "type": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": "Avatar",
                "allow_unverified": True}})
        self.assertIs(result.get("allow_unverified"), True)

    def test_unknown_field_is_still_rejected(self):
        """Белый список _exact_fields не должен растворяться вместе с флагом."""
        import high_level_actions
        with self.assertRaises(Exception):
            high_level_actions.compile_action(self.root, {
                "action": "project_command", "command": {
                    "type": "rename_symbol", "kind": "class_name",
                    "declaration": "res://src/player.gd:1",
                    "old_name": "Player", "new_name": "Avatar",
                    "allow_unverified": True, "что_то_еще": 1}})

    # __APPEND_3__
class PanelSettingDefault(unittest.TestCase):
    """Галочка в настройках панели: по умолчанию СТОИТ (переименовывать).

    Проверяем по исходнику панели: без редактора Godot нельзя поднять Control,
    а контракт (дефолт true + сохранение в user:// + передача в _policy_body)
    выражается именно в тексте панели.
    """

    PANEL = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                         "agent_panel.gd")

    def setUp(self):
        with open(self.PANEL, "r", encoding="utf-8") as handle:
            self.source = handle.read()

    def test_panel_has_unverified_toggle_defaulting_to_true(self):
        self.assertRegex(
            self.source,
            r"var\s+_rename_unverified_enabled\s*:\s*bool\s*=\s*true")

    def test_panel_persists_the_setting(self):
        # Настройка обязана переживать перезапуск редактора, иначе «снял
        # галочку» пришлось бы делать заново каждый раз.
        self.assertRegex(self.source, r"func\s+_save_rename_unverified_setting")
        self.assertRegex(self.source, r"func\s+_load_rename_unverified_setting")
        self.assertRegex(self.source, r"RENAME_UNVERIFIED_SETTING_FILE")

    def test_panel_load_defaults_to_true_when_no_file(self):
        """Отсутствие файла настроек = включено. Иначе первое же открытие
        проекта молча выставило бы strict вопреки «галочка стоит по стандарту»."""
        match = re.search(
            r"func\s+_load_rename_unverified_setting.*?\n\nfunc", self.source, re.S)
        self.assertIsNotNone(match, "не найден загрузчик настройки")
        body = match.group(0)
        self.assertRegex(body, r"file_exists\([^)]*\)\s*:\s*\n?\s*return\s+true")

    def test_panel_sends_the_flag_in_policy_body(self):
        """Флаг обязан уезжать тем же каналом, что allow_addons, иначе сервер
        не узнает о снятой галочке и поведёт себя по умолчанию."""
        match = re.search(r"func\s+_policy_body.*?\n\nfunc", self.source, re.S)
        self.assertIsNotNone(match, "не найдена _policy_body")
        self.assertIn("rename_unverified", match.group(0))


if __name__ == "__main__":
    unittest.main()