"""modules/context/gather/tests/test_core.py - unit-тесты домена `context.gather`.

Домен ничего не читает: проверяются правила запроса (секции, порядок, дубли,
лимит), политика `path` и форма собранного ответа. Корпус
(`fixtures/corpus/context/gather`) гоняет те же правила на живом агенте.
Правила: R-07, R-09, R-11.
"""

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.context.gather.domain import core


def _refusal(args, contributions=(), policy=None):
    """`kind` и `details.reason` отказа домена — по одному месту на кейс."""
    with pytest.raises(AppError) as caught:
        core.build_request(args, policy, contributions)
    return caught.value.kind, caught.value.details.get("reason")


def test_default_request_is_all_known_sections():
    """Без `sections` запрашиваются все известные имена в объявленном порядке."""
    request = core.build_request({})
    assert request["sections"] == ["project", "tools", "editor", "runtime",
                                   "architecture"]
    assert request["path"] is None


def test_requested_order_is_kept():
    """Порядок `sections` в ответе — порядок запроса, а не алфавит."""
    request = core.build_request({"sections": ["tools", "project"]})
    assert request["sections"] == ["tools", "project"]


def test_contribution_name_becomes_known_section():
    """Секция из вклада — известное имя: без вклада `editor` был бы неизвестен."""
    section = type("Section", (), {"name": "editor"})()
    request = core.build_request({"sections": ["editor"]}, None, (section,))
    assert request["sections"] == ["editor"]


def test_duplicate_section_refused():
    """Повтор имени — отказ: одна и та же секция дважды в ответе бессмысленна."""
    assert _refusal({"sections": ["project", "project"]}) == \
        ("invalid_input", "duplicate_section")


def test_too_many_sections_refused():
    """Больше восьми секций — отказ по лимиту, а не тихое усечение."""
    assert _refusal({"sections": ["project"] * 9}) == \
        ("invalid_input", "too_large")


def test_unknown_section_refused():
    """Неизвестное имя отказывает всему вызову и называет известные секции."""
    with pytest.raises(AppError) as caught:
        core.build_request({"sections": ["project", "secrets"]})
    assert caught.value.kind == "invalid_input"
    assert caught.value.details["reason"] == "unknown_section"
    assert "project" in caught.value.hint


def test_empty_sections_refused():
    """Пустой список — отказ: «ничего не просил» не равно «просил всё»."""
    assert _refusal({"sections": []}) == ("invalid_input", "empty_sections")


def test_path_escape_refused():
    """`..` в цели — выход за проект, а не «просто путь»."""
    assert _refusal({"sections": ["project"], "path": "../outside.gd"}) == \
        ("denied", "path_escape")


def test_addon_path_denied():
    """Цель внутри аддонов закрыта политикой, пока аддоны не разрешены."""
    assert _refusal({"sections": ["project"], "path": "addons/plugin/x.gd"},
                    policy=PathPolicy("")) == ("denied", "denied")


def test_res_path_is_normalised():
    """`res://` снимается: секции работают с относительным путём проекта."""
    request = core.build_request({"sections": ["project"],
                                  "path": "res://scripts/player.gd"})
    assert request["path"] == "scripts/player.gd"


def test_project_section_shape():
    """Секция `project`: корень, файл проекта, движка нет, источник — ФС."""
    assert core.project_section("D:/p", "res://project.godot") == {
        "root": "D:/p", "project_file": "res://project.godot",
        "engine": None, "source": "fs"}


def test_tools_section_sorted_names_and_effects():
    """Секция `tools`: имена по алфавиту, эффекты — карта имя → effect."""
    assert core.tools_section([("write_preview", "write"), ("search", "read")]) == {
        "count": 2, "names": ["search", "write_preview"],
        "effects": {"search": "read", "write_preview": "write"}}


def test_assemble_sorts_lists_and_reports_cost():
    """Ответ: `available` по алфавиту, `unavailable` по имени, стоимость `light`."""
    result = core.assemble({"tools": {"count": 0}, "project": {"root": ""}},
                           [{"name": "runtime", "reason": "no_module"},
                            {"name": "editor", "reason": "no_bridge"}])
    assert result["available"] == ["project", "tools"]
    assert result["unavailable"] == [{"name": "editor", "reason": "no_bridge"},
                                     {"name": "runtime", "reason": "no_module"}]
    assert result["cost"] == "light"


def test_find_contribution_by_name():
    """Владелец ищет вклад по имени секции и не падает, если его нет."""
    editor = type("Section", (), {"name": "editor"})()
    runtime = type("Section", (), {"name": "runtime"})()
    assert core.find_contribution((editor, runtime), "runtime") is runtime
    assert core.find_contribution((editor,), "architecture") is None

