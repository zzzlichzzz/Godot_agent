# -*- coding: utf-8 -*-
"""Синтетические тесты п.3.2: enum и его members.

Парсер вообще не знал про enum: и сам тип, и его members не попадали в
объявления, поэтому переименовать их было нельзя. Плюс сообщение об ошибке
«По declaration найдено объявлений: 0» модель не может разобрать.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from godot_tools import gd_semantic_parser, symbol_refactor
from minilich import ml_project_index


UNIT = """class_name Unit
extends Node

enum State { IDLE, RUN, DONE }

func st() -> int:
\treturn State.IDLE
"""


class EnumRename(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_enum_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/unit.gd", UNIT)
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
        ml_project_index.build_index(self.root)

    def _member_action(self, new="IDLING", old="IDLE"):
        return {"action": "rename_symbol", "kind": "enum_member",
                "declaration": "res://src/unit.gd:4",
                "old_name": old, "new_name": new}

    def _type_action(self, new="Phase", old="State"):
        return {"action": "rename_symbol", "kind": "enum",
                "declaration": "res://src/unit.gd:4",
                "old_name": old, "new_name": new}

    # --- 3.2.1 парсер видит enum и его members ---
    def test_parser_sees_enum_and_members(self):
        parsed = gd_semantic_parser.parse(UNIT, "res://src/unit.gd")
        names = {item["name"]: item["kind"] for item in parsed["declarations"]}
        self.assertEqual(names.get("State"), "enum")
        for member in ("IDLE", "RUN", "DONE"):
            self.assertEqual(names.get(member), "enum_member", member)

    # --- 3.2.2 members enum переименовывается вместе со ссылками ---
    def test_enum_member_rename(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        unit = self._read("src/unit.gd")
        self.assertIn("enum State { IDLING, RUN, DONE }", unit)
        self.assertIn("return State.IDLING", unit)
        self.assertNotIn("IDLE", unit.replace("IDLING", ""))

    # --- 3.2.3 сам тип enum переименовывается ---
    def test_enum_type_rename(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._type_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        unit = self._read("src/unit.gd")
        self.assertIn("enum Phase { IDLE, RUN, DONE }", unit)
        self.assertIn("return Phase.IDLE", unit)

    # --- 3.2.4 анонимный enum: members без типа ---
    def test_anonymous_enum_members(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

enum { ALPHA, BETA }

func pick() -> int:
\treturn BETA
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, {
            "action": "rename_symbol", "kind": "enum_member",
            "declaration": "res://src/unit.gd:4",
            "old_name": "BETA", "new_name": "BETA_2"})
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("enum { ALPHA, BETA_2 }", self._read("src/unit.gd"))
        self.assertIn("return BETA_2", self._read("src/unit.gd"))

    # --- 3.2.5 члены enum со значениями ---
    def test_enum_member_with_values(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

enum State { IDLE = 0, RUN = 1, DONE = 2 }

func st() -> int:
\treturn State.RUN
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action("MOVING", "RUN"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        unit = self._read("src/unit.gd")
        self.assertIn("IDLE = 0, MOVING = 1, DONE = 2", unit)
        self.assertIn("return State.MOVING", unit)

    # --- 3.2.6 обращение из другого файла ---
    def test_member_reference_from_other_file(self):
        self._write("src/arena.gd", """extends Node

func start() -> int:
\treturn Unit.State.IDLE
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("Unit.State.IDLING", self._read("src/arena.gd"))
        self.assertIn("Unit.State.IDLING", self._read("src/arena.gd"))

    # --- 3.2.7 человекочитаемое сообщение об ошибке для enum ---
    def test_enum_error_message_is_actionable(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, {
                "action": "rename_symbol", "kind": "enum_member",
                "declaration": "res://src/unit.gd:99",
                "old_name": "NOPE", "new_name": "OTHER"})
        message = str(ctx.exception)
        # Модель должна понять, что именно не так, и что делать дальше.
        self.assertIn("enum_member", message)
        self.assertIn("99", message)
        self.assertIn("IDLE", message)

    # --- Аудит 3.2: тень одноимённой переменной внутри функции ---
    def test_shadowed_member_name_is_untouched(self):
        self._write("src/unit.gd", UNIT + """
func shadow() -> int:
\tvar IDLE = 5
\treturn IDLE
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        unit = self._read("src/unit.gd")
        self.assertIn("var IDLE = 5", unit)
        self.assertIn("return IDLE", unit)
        self.assertIn("State.IDLING", unit)

    # --- Аудит 3.2: коллизия члена с другим member блокирует ---
    def test_member_collision_is_refused(self):
        self._write("src/unit.gd",
                    "class_name Unit\nextends Node\n\nenum State { IDLE, IDLING }\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._member_action())

    # --- Аудит 3.2: members другого enum не трогаются ---
    def test_other_enum_members_untouched(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

enum State { IDLE, RUN }
enum Mode { IDLE, FAST }

func st() -> int:
\treturn State.IDLE
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        unit = self._read("src/unit.gd")
        self.assertIn("enum Mode { IDLE, FAST }", unit)
        self.assertIn("enum State { IDLING, RUN }", unit)
        self.assertIn("return State.IDLING", unit)

    # --- Аудит 3.2: откат возвращает исходные имена ---
    def test_rollback_restores_enum(self):
        import history_manager
        before = self._read("src/unit.gd")
        prepared = symbol_refactor.prepare_rename(
            self.root, self._member_action())
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("IDLING", self._read("src/unit.gd"))
        ok, _msg, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok)
        self.assertEqual(self._read("src/unit.gd"), before)


if __name__ == "__main__":
    unittest.main()


