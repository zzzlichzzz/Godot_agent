"""modules/code_intel/functions/tests/test_core.py - unit-тесты домена (R-11).

Домен получает текст и возвращает данные: ни диска, ни `MemoryFS`, ни Godot.
Кейсы повторяют корпус `fixtures/corpus/code_intel/functions/` (R-07): порядок
объявления, `static func`, дубль имени, прилегающие комментарии и аннотации,
пустые строки в теле, вложенный класс, закомментированная функция, CRLF.
"""

from python.modules.code_intel.functions.domain import core

LAB = "\n".join([
    "extends RefCounted",           # 1
    "",                             # 2
    "var counter := 0",             # 3
    "",                             # 4
    "func _process(delta: float) -> void:",   # 5
    "\tcounter += 1",               # 6
    "",                             # 7
    "static func make() -> RefCounted:",      # 8
    "\treturn RefCounted.new()",    # 9
    "",                             # 10
    "# Прилегающий комментарий.",   # 11
    "@tool",                        # 12
    '@rpc("any_peer")',             # 13
    "func rpc_ping() -> void:",     # 14
    "\tpass",                       # 15
    "",                             # 16
    "func spaced_lines() -> int:",  # 17
    "\tvar first := 1",             # 18
    "",                             # 19
    "\tvar second := 2",            # 20
    "\treturn first + second",      # 21
    "",                             # 22
    "",                             # 23
    "class Inner:",                 # 24
    "\tfunc inner_helper() -> String:",       # 25
    '\t\treturn "inner"',           # 26
    "",                             # 27
    "# func fake() -> void:",       # 28
    "# \tpass",                     # 29
    "func duplicated() -> String:",  # 30
    '\treturn "first"',             # 31
    "",                             # 32
    "func duplicated() -> String:",  # 33
    '\treturn "second"',            # 34
])

PLAYER = "\n".join([
    "extends CharacterBody2D",      # 1
    "",                             # 2
    "var health := 100",            # 3
    "",                             # 4
    "",                             # 5
    "func _ready() -> void:",       # 6
    "\tpass",                       # 7
    "",                             # 8
    "",                             # 9
    "func take_damage(amount: int) -> void:",  # 10
    "\thealth = max(0, health - amount)",      # 11
    "\tif health == 0:",            # 12
    "\t\tdie()",                    # 13
    "",                             # 14
    "",                             # 15
    "func die() -> void:",          # 16
    "\tqueue_free()",               # 17
])


def test_list_order_follows_declaration():
    assert core.list_names(PLAYER) == ["_ready", "take_damage", "die"]


def test_static_and_helpers_are_listed():
    assert core.list_names(LAB) == ["_process", "make", "rpc_ping", "spaced_lines",
                                    "inner_helper", "duplicated", "duplicated"]


def test_call_of_func_ready_is_not_a_declaration():
    text = "func_ready()\nfunc _ready():\n\tpass\n"
    assert core.list_names(text) == ["_ready"]


def test_extract_one_snippet_is_verbatim():
    found, missing = core.extract(PLAYER, ["take_damage"])
    assert missing == []
    assert found == [{
        "name": "take_damage",
        "snippet": ("func take_damage(amount: int) -> void:\n"
                    "\thealth = max(0, health - amount)\n"
                    "\tif health == 0:\n"
                    "\t\tdie()"),
        "start_line": 10,
        "end_line": 13,
    }]


def test_request_order_and_missing_are_kept():
    found, missing = core.extract(PLAYER, ["die", "no_such", "take_damage"])
    assert [item["name"] for item in found] == ["die", "take_damage"]
    assert missing == ["no_such"]


def test_duplicate_name_takes_first_declaration():
    found, missing = core.extract(LAB, ["duplicated"])
    assert missing == []
    assert len(found) == 1
    assert found[0]["start_line"] == 28
    assert found[0]["end_line"] == 31
    assert found[0]["snippet"].endswith('func duplicated() -> String:\n\treturn "first"')


def test_attached_comments_and_annotations_enter_snippet():
    found, _ = core.extract(LAB, ["rpc_ping"])
    assert found[0]["start_line"] == 11
    assert found[0]["end_line"] == 15
    lines = found[0]["snippet"].splitlines()
    assert lines[:2] == ["# Прилегающий комментарий.", "@tool"]
    assert lines[2] == '@rpc("any_peer")'


def test_blank_lines_inside_body_stay_and_trailing_are_trimmed():
    found, _ = core.extract(LAB, ["spaced_lines"])
    assert found[0]["start_line"] == 17
    assert found[0]["end_line"] == 21
    assert "\n\n" in found[0]["snippet"]
    assert not found[0]["snippet"].endswith("\n")


def test_nested_class_function_is_found():
    found, _ = core.extract(LAB, ["inner_helper"])
    assert found[0]["start_line"] == 25
    assert found[0]["snippet"] == '\tfunc inner_helper() -> String:\n\t\treturn "inner"'


def test_commented_function_is_not_found():
    found, missing = core.extract(LAB, ["fake"])
    assert found == []
    assert missing == ["fake"]


def test_crlf_text_keeps_lines_and_snippets():
    text = LAB.replace("\n", "\r\n")
    assert core.list_names(text) == core.list_names(LAB)
    found, _ = core.extract(text, ["spaced_lines"])
    assert found[0]["start_line"] == 17
    assert "\r" not in found[0]["snippet"]


def test_empty_text_is_empty_answer():
    assert core.list_names("") == []
    assert core.extract("", ["f"]) == ([], ["f"])


def test_func_inside_func_listed_but_not_extractable():
    """`func` в теле другой функции: в списке виден, тело не извлекается.

    Так ведёт себя эталон: `_spans` перепрыгивает тело целиком, поэтому
    вложенное объявление не попадает в карту границ, а `list_names` идёт
    по всем строкам и имя видит.
    """
    text = "\n".join([
        "func nested_outer() -> int:",      # 1
        "\tvar total := 0",                 # 2
        "\tfunc nested_inner() -> int:",    # 3
        "\t\treturn 1",                     # 4
        "\ttotal += 1",                     # 5
        "\treturn total",                   # 6
    ])
    assert core.list_names(text) == ["nested_outer", "nested_inner"]
    found, missing = core.extract(text, ["nested_outer"])
    assert missing == []
    assert [item["name"] for item in found] == ["nested_outer"]
    assert found[0]["start_line"] == 1
    assert found[0]["end_line"] == 6
    assert "nested_inner" in found[0]["snippet"]
    found, missing = core.extract(text, ["nested_outer", "nested_inner"])
    assert [item["name"] for item in found] == ["nested_outer"]
    assert missing == ["nested_inner"]
