"""D20/R-05: an actual internal service needs neither a fake tool nor consumer.

These are new infrastructure boundary cases, not imported native test code.
Three independent positives expose existing blockers; the empty negative stays.
"""
from types import SimpleNamespace

import pytest

from python.kernel.module_spec import ModuleSpec
from python.protocol.registry import Registry
from python.runtime.bootstrap import _register
from tools.selfcheck import module_readiness


def build_tree(args, ctx):
    return {"path": "res://", "type": "dir", "children": [], "count": 0}


def service_metadata():
    return SimpleNamespace(
        id="project_text.tree", environment="*", provides_tools=(),
        contributes_to=(), internal_services=("project_text.tree",),
        requires_ports=("project_text_fs",), entrypoints={"build": build_tree},
    )


def test_internal_only_manifest_is_valid_without_invented_contribution():
    metadata = service_metadata()
    spec = ModuleSpec(**vars(metadata))
    assert spec.provides_tools == spec.contributes_to == ()
    assert spec.internal_services == ("project_text.tree",)
    assert set(spec.entrypoints) == {"build"}


def test_internal_only_registration_keeps_public_registry_empty():
    registry = Registry()
    item = SimpleNamespace(spec=service_metadata(), tools=(), contributions=())
    ctx = _register(registry, item, "test", {"project_text_fs": object()}, None, {})
    assert ctx is not None, registry.disabled()
    assert registry.entries() == []
    assert registry.disabled() == {}


def test_internal_service_readiness_requires_no_fake_public_surface():
    status, detail = module_readiness(service_metadata(), has_tests=True, has_corpus=True)
    assert status == "ok", detail


def test_a_truly_empty_manifest_still_fails_closed():
    with pytest.raises(ValueError, match="не объявляет"):
        ModuleSpec(id="project_text.tree")


def test_d21_internal_only_service_with_tests_and_corpus_is_ready():
    metadata = service_metadata()
    metadata.id = "private.worker"
    status, detail = module_readiness(metadata, has_tests=True, has_corpus=True)
    assert status == "ok", detail


def test_d21_empty_manifest_retains_the_exact_existing_error():
    with pytest.raises(ValueError) as caught:
        ModuleSpec(id="private.worker")
    assert str(caught.value) == (
        "модуль 'private.worker' не объявляет ни provides_tools, ни contributes_to")


@pytest.mark.parametrize("identity", [
    {"internal_services": ("private.worker",)},
    {"entrypoints": {"build": build_tree}},
    {"capabilities": ("private.worker",)},
])
def test_d21_manifest_has_an_identity_without_public_tools(identity):
    spec = ModuleSpec(id="private.worker", **identity)
    assert spec.provides_tools == spec.contributes_to == ()


def test_d21_internal_service_without_tests_does_not_turn_green():
    status, _ = module_readiness(service_metadata(), has_tests=False, has_corpus=False)
    assert status == "not_implemented"


def test_d21_internal_service_without_corpus_does_not_turn_green():
    status, _ = module_readiness(service_metadata(), has_tests=True, has_corpus=False)
    assert status == "not_implemented"


def test_tree_passes_actual_module_discovery():
    from python.runtime.module_loader import discover
    loaded, failed = discover()
    errors = [row for row in failed if row["module"] == "project_text.tree"]
    assert not errors, errors
    assert any(item.spec.id == "project_text.tree" and tuple(tool.name for tool in item.tools) == ('tree',)
               for item in loaded)


def test_tree_is_not_disabled_by_actual_agent_bootstrap(tmp_path):
    from python.runtime.bootstrap import build_agent
    agent = build_agent(tmp_path, "test", state_dir=str(tmp_path / "state"))
    assert "project_text.tree" not in agent.disabled(), agent.disabled().get("project_text.tree")
    assert "tree" in {tool["name"] for tool in agent.tools()}


def test_d22_loader_empty_identity_keeps_exact_error(monkeypatch):
    from python.runtime import module_loader
    package = "python.modules.private.worker.module"
    empty = SimpleNamespace(provides_tools=(), internal_services=(), entrypoints={}, contributes_to=())
    modules = {package: SimpleNamespace(MODULE=empty),
               package.rsplit(".", 1)[0] + ".tools": SimpleNamespace(TOOLS=())}
    monkeypatch.setattr(module_loader.importlib, "import_module", modules.__getitem__)
    path = module_loader.ROOT / "python/modules/private/worker/module.py"
    with pytest.raises(RuntimeError) as caught:
        module_loader.load_one(path)
    assert str(caught.value) == package + ": нет TOOLS (ADR-0006)"
