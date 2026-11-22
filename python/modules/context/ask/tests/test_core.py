"""New public ask contract: pure validation and structural adapter boundary."""
from importlib import import_module
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy


def core():
    return import_module("python.modules.context.ask.domain.core")


def test_default_native_budget_and_original_query_are_forwarded():
    policy = PathPolicy("fixture")
    request = core().build_request({"query": " take_damage "}, policy)
    assert request == {"query": " take_damage ", "budget_chars": 8000,
                       "allow_addons": False, "allow_self_edit": False, "target": None}


@pytest.mark.parametrize("budget", [-1, 0, 299, 300, 301, 400, 500, 1000, 8000, 100000])
def test_integer_budgets_remain_native_inputs_not_an_invented_upper_clamp(budget):
    request = core().build_request({"query": "take_damage", "budget_chars": budget}, PathPolicy("fixture"))
    assert request["budget_chars"] == budget


@pytest.mark.parametrize("args", [None, [], {}, {"query": ""}, {"query": "   "},
    {"query": None}, {"query": 17}, {"query": []}, {"query": "a\x00b"},
    {"query": "ok", "budget_chars": None}, {"query": "ok", "budget_chars": True},
    {"query": "ok", "budget_chars": "500"}, {"query": "ok", "budget_chars": 1.5},
    {"query": "ok", "operation": "log"}])
def test_invalid_input_is_typed_before_the_port(args):
    with pytest.raises(AppError) as failure:
        core().build_request(args, PathPolicy("fixture"))
    assert failure.value.kind == "invalid_input"


@pytest.mark.parametrize("query", ["../outside.gd", "..\\outside.gd", "/outside.gd",
    "C:/outside.gd", "res://../outside.gd", ".agent_history/private.gd", "addons/vendor/private.gd"])
def test_explicit_forbidden_paths_are_typed_denied(query):
    with pytest.raises(AppError) as failure:
        core().build_request({"query": query}, PathPolicy("fixture"))
    assert failure.value.kind == "denied"
    assert "fixture" not in failure.value.message


def test_explicit_allowed_path_is_physical_guard_input_not_a_new_public_field():
    request = core().build_request({"query": "res://scripts/player.gd"}, PathPolicy("fixture"))
    assert request["target"] == "scripts/player.gd"


def test_capabilities_come_from_policy_not_query_or_arguments():
    request = core().build_request({"query": "take_damage"},
        PathPolicy("fixture", allow_addons=True, allow_self_edit=True))
    assert request["allow_addons"] is request["allow_self_edit"] is True


def test_app_orchestrates_the_local_port_without_changing_native_text():
    calls = []

    class Port:
        def answer(self, **request):
            calls.append(request)
            return "[MAP]\nres://scripts/player.gd\n[FRAGMENTS]\nfunc take_damage():"

    port = Port()
    ctx = SimpleNamespace(path_policy=PathPolicy("fixture"), port=lambda name: port if name == "librarian" else None)
    app = import_module("python.modules.context.ask.app")
    answer = app.call("ask", {"query": "take_damage", "budget_chars": 500}, ctx)
    assert answer == "[MAP]\nres://scripts/player.gd\n[FRAGMENTS]\nfunc take_damage():"
    assert calls == [{"query": "take_damage", "budget_chars": 500,
        "allow_addons": False, "allow_self_edit": False, "target": None}]


def test_app_rejects_foreign_tool():
    app = import_module("python.modules.context.ask.app")
    with pytest.raises(AppError) as failure:
        app.call("not_ask", {}, None)
    assert failure.value.kind == "unknown_tool"


def test_adapter_implements_the_module_owned_runtime_checkable_protocol(tmp_path):
    from tests.py.context.ask_composition import adapter_for
    port = import_module("python.modules.context.ask.ports").Librarian
    adapter = adapter_for
    assert isinstance(adapter(tmp_path / "project", tmp_path / "state", tmp_path / "addon"), port)


def test_spec_has_native_limits_and_no_diagnostic_public_operations():
    spec = import_module("python.modules.context.ask.tools").ASK
    module = import_module("python.modules.context.ask.module").MODULE
    assert spec.name == "ask" and spec.effects == "read" and spec.idempotent
    assert spec.errors == ("invalid_input", "not_found", "denied")
    assert spec.availability == "*" and spec.result == {"type": "string"}
    assert set(spec.args["properties"]) == {"query", "budget_chars"}
    assert spec.limits == {"budget_chars_default": 8000, "budget_chars_min": 400,
        "map_files": 8, "structure_files": 3, "signatures_per_file": 24,
        "scene_chars": 900, "fragments": 6, "fragment_tokens": 4,
        "fragments_per_file": 2, "fragment_pool": 12, "callers": 6,
        "caller_functions": 2, "autoloads": 12, "signals": 2, "signal_links": 6,
        "card_declarations": 4, "card_parameters": 10, "card_locals": 8,
        "card_uses": 8, "card_references": 8}
    assert module.id == "context.ask" and module.provides_tools == ("ask",)
    assert module.requires_ports == ("librarian",) and module.corpus == "corpus"
