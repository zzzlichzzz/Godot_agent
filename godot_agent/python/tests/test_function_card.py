# -*- coding: utf-8 -*-
"""Тесты глубокой карточки функции (godot_tools/function_card.py).

План: docs/function_card_plan.md (S2–S4). Проверяются на синтетическом
мини-проекте ВСЕ секции карточки: тело, символы по группам (члены, консты,
сигналы, автолоады — и по res://, и по uid://), proven/dynamic-разруливание,
связи (call files с proven/probable, наследники по extends-иерархии,
переопределения с super), честные хвосты при обрезке и мост `--card`.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from minilich import ml_project_index  # noqa: E402
import function_card  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import agent_bridge  # noqa: E402


def _write(root, rel, text):
    p = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _run_bridge(argv):
    """Запуск CLI моста внутри процесса: (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = agent_bridge.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


BASE_GD = """extends Node
class_name BaseUnit

signal died

const MAX_HP := 10

var hp := MAX_HP
var _alive := true

func hurt(amount, from):
\tvar total = amount + 1
\thp -= total
\ttotal = min(total, MAX_HP)
\tScore.add(total)
\tCtx.ping()
\trandf()
\theal_hero(total)
\t_hook()
\tif hp <= 0:
\t\tdied.emit()

func _hook():
\tpass
"""

HERO_GD = """extends Node

func heal_hero(amount):
\tpass
"""

SCORE_GD = """extends Node

func add(points):
\tpass
"""

CTX_GD = """extends Node

func ping():
\tpass
"""

GRUNT_GD = """extends "res://scripts/base/base_unit.gd"

func hurt(amount, from):
\tsuper.hurt(amount, from)
\t_grunt_extra()

func _grunt_extra():
\tpass
"""

OGRE_GD = """extends BaseUnit

var ogre_flag := true
"""


def _make_project():
    root = tempfile.mkdtemp(prefix="func_card_")
    _write(root, "project.godot",
           "config_version=5\n\n[autoload]\n\n"
           'Score="*res://scripts/autoload/score.gd"\n'
           'Ctx="*uid://ctxuid123"\n')
    _write(root, "scripts/autoload/score.gd", SCORE_GD)
    _write(root, "scripts/autoload/ctx.gd", CTX_GD)
    _write(root, "scripts/autoload/ctx.gd.uid", "uid://ctxuid123\n")
    _write(root, "scripts/base/base_unit.gd", BASE_GD)
    _write(root, "scripts/base/base_hero.gd", HERO_GD)
    _write(root, "scripts/enemy/grunt.gd", GRUNT_GD)
    _write(root, "scripts/enemy/ogre.gd", OGRE_GD)
    _write(root, "scripts/caller_a.gd",
           "extends Node\n\nfunc on_hit(u):\n\tu.hurt(5, null)\n"
           "\tu.has_method(\"hurt\")\n")
    _write(root, "scripts/caller_b.gd",
           "extends Node\n\nfunc direct_hit():\n\thurt(2, null)\n")
    ml_project_index.build_index(root)
    return root

class FunctionCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = _make_project()
        res = function_card.build_function_card(
            cls.root, "res://scripts/base/base_unit.gd", "hurt")
        cls.lines = res["lines"]
        cls.text = "\n".join(cls.lines)

    def test_header_and_body(self):
        self.assertIn("FUNC CARD func:hurt — res://scripts/base/base_unit.gd:",
                      self.text)
        self.assertIn("class BaseUnit", self.text)
        self.assertIn("rev=sha1:", self.text)
        self.assertIn("[BODY]", self.text)
        self.assertIn("func hurt(amount, from):", self.text)

    def test_symbols_groups(self):
        self.assertIn("params: amount, from", self.text)
        self.assertIn("locals: total (L", self.text)
        self.assertIn("hp (L", self.text)
        # _alive объявлена, но в теле hurt не упоминается — карточка показывает
        # только члены, к которым функция обращается.
        self.assertNotIn("_alive", self.text)
        self.assertIn("MAX_HP (L", self.text)
        self.assertIn("died (L", self.text)

    def test_autoloads_res_and_uid(self):
        self.assertIn("Score → res://scripts/autoload/score.gd", self.text)
        self.assertIn("Ctx → res://scripts/autoload/ctx.gd", self.text)
        self.assertNotIn("uid не разрешён", self.text)

    def test_proven_vs_dynamic(self):
        # heal_hero объявлен один раз в проекте — proven с адресом.
        self.assertIn("heal_hero res://scripts/base/base_hero.gd:",
                      self.text)
        # randf — встроенная утилита GDScript.
        self.assertIn("randf", self.text.split("builtins:")[1].splitlines()[0])
        # died.emit() — вызов по значению: честный dynamic, не proven.
        self.assertIn(
            "emit",
            self.text.split("dynamic (не разрулено):")[1].splitlines()[0])

    def test_funcs_this_file(self):
        self.assertIn("funcs (этот файл): _hook:", self.text)

    def test_callers_proven_and_probable(self):
        self.assertIn("[CALLERS]", self.text)
        # super.hurt() — member-контекст (probable); bare hurt() — proven.
        self.assertIn("res://scripts/enemy/grunt.gd:4", self.text)
        self.assertIn("(probable)", self.text)
        self.assertIn("res://scripts/caller_b.gd:4 (proven)", self.text)
        self.assertIn("res://scripts/caller_a.gd:4", self.text)
        # Строковая ссылка has_method("hurt") — dynamic strings.
        self.assertIn('res://scripts/caller_a.gd:5 "hurt"', self.text)

    def test_subclasses_and_overrides(self):
        self.assertIn("[SUBCLASSES]", self.text)
        self.assertIn("res://scripts/enemy/grunt.gd", self.text)
        self.assertIn("res://scripts/enemy/ogre.gd", self.text)
        self.assertIn("[OVERRIDES]", self.text)
        self.assertIn("res://scripts/enemy/grunt.gd:3 (probable super)",
                      self.text)
        self.assertNotIn("ogre.gd:", self.text.split("[OVERRIDES]")[1])


class FunctionCardEdgeTest(unittest.TestCase):
    def test_func_not_found(self):
        root = _make_project()
        res = function_card.build_function_card(
            root, "res://scripts/base/base_unit.gd", "no_such_func")
        self.assertTrue(res.get("error"), res)
        self.assertIn("func-not-found", res["error"])

    def test_ambiguous_call_is_dynamic(self):
        root = tempfile.mkdtemp(prefix="func_card2_")
        _write(root, "project.godot", "config_version=5\n")
        _write(root, "a.gd",
               "extends Node\n\nfunc victim(x):\n\tshared()\n\n"
               "func shared():\n\tpass\n")
        _write(root, "b.gd",
               "extends Node\n\nfunc shared():\n\tpass\n")
        ml_project_index.build_index(root)
        res = function_card.build_function_card(root, "res://a.gd", "victim")
        text = "\n".join(res["lines"])
        # Два объявления shared() → proven невозможен, имя уходит в dynamic.
        self.assertIn(
            "shared",
            text.split("dynamic (не разрулено):")[1].splitlines()[0])
        self.assertNotIn("shared res://", text)

    def test_cap_tail_is_honest(self):
        root = tempfile.mkdtemp(prefix="func_card3_")
        _write(root, "project.godot", "config_version=5\n")
        body = "\n".join("\tuse_%d = %d" % (i, i) for i in range(30))
        _write(root, "big.gd",
               "extends Node\nvar use_0 := 0\n\nfunc f():\n%s\n" % body)
        ml_project_index.build_index(root)
        res = function_card.build_function_card(root, "res://big.gd", "f")
        text = "\n".join(res["lines"])
        self.assertIn("…(+", text)
        self.assertIn("more", text)


class FunctionCardBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = _make_project()

    def test_bridge_card_ok(self):
        rc, out, err = _run_bridge(
            ["--root", self.root, "--access", "project", "functions",
             "--card", "--names", "hurt", "res://scripts/base/base_unit.gd"])
        self.assertEqual(rc, agent_bridge.RC_OK, err)
        self.assertIn("FUNC CARD func:hurt", out)
        self.assertIn("[SUBCLASSES]", out)

    def test_bridge_card_requires_names(self):
        rc, out, err = _run_bridge(
            ["--root", self.root, "--access", "project", "functions",
             "--card", "res://scripts/base/base_unit.gd"])
        self.assertEqual(rc, agent_bridge.RC_USAGE, err)
        self.assertIn("--card requires --names", out + err)

    def test_bridge_card_missing_func(self):
        rc, out, err = _run_bridge(
            ["--root", self.root, "--access", "project", "functions",
             "--card", "--names", "no_such", "res://scripts/base/base_unit.gd"])
        self.assertEqual(rc, agent_bridge.RC_NOT_FOUND, err)
        self.assertIn("func-not-found", out)


class FunctionCardLibrarianTest(unittest.TestCase):
    """Проводка в Библиотекаря: `func:имя` — глубокая карточка, голое имя — L7."""
    @classmethod
    def setUpClass(cls):
        cls.root = _make_project()
        import librarian
        cls.lib = librarian

    def test_bare_name_stays_l7(self):
        ans = self.lib.answer(self.root, "hurt")
        self.assertIn("SYMBOL (", ans)
        self.assertNotIn("[BODY]", ans)
        self.assertNotIn("FUNC CARD", ans)

    def test_func_prefix_deep_card(self):
        ans = self.lib.answer(self.root, "func:hurt")
        self.assertIn("SYMBOL (", ans)
        self.assertIn("FUNC CARD func:hurt", ans)
        self.assertIn("[BODY]", ans)
        self.assertIn("[SUBCLASSES]", ans)
        # hurt объявлен и в base_unit, и в grunt (override) — честный WARNING;
        # карточка строится для иерархического корня (у base_unit наследники).
        self.assertIn("WARNING: имя объявлено в 2 файлах", ans)
        self.assertIn(
            "res://scripts/base/base_unit.gd",
            ans.split("FUNC CARD")[1].splitlines()[0])


if __name__ == "__main__":
    unittest.main()

