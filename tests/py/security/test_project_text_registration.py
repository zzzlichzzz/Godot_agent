"""SEC-24/D21: internal registration is not a public capability grant."""
from types import SimpleNamespace

from python.protocol.registry import Registry
from python.runtime.bootstrap import _register


def metadata(**changes):
    fields = dict(id="private.worker", environment="*", provides_tools=(),
                  contributes_to=(), internal_services=("private.worker",),
                  requires_ports=("private_fs",), entrypoints={"build": lambda args, ctx: {}})
    fields.update(changes)
    return SimpleNamespace(**fields)


def register(registry, spec, ports, profile="test"):
    return _register(registry, SimpleNamespace(spec=spec, tools=(), contributions=()),
                     profile, ports, None, {})


def test_internal_registration_adds_no_public_tool_or_contribution():
    registry = Registry()
    assert register(registry, metadata(), {"private_fs": object()}) is not None
    assert registry.entries() == []
    assert registry.contributions("context") == ()
    assert registry.disabled() == {}


def test_missing_port_failure_is_isolated_from_internal_neighbor():
    registry = Registry()
    assert register(registry, metadata(id="private.missing"), {}) is None
    assert register(registry, metadata(), {"private_fs": object()}) is not None
    assert registry.disabled() == {"private.missing": "нет портов: private_fs"}
    assert registry.entries() == []


def test_wrong_editor_profile_still_rejects_internal_service():
    registry = Registry()
    assert register(registry, metadata(environment="editor"), {"private_fs": object()}) is None
    assert registry.disabled() == {"private.worker": "нужен профиль editor (живой редактор)"}


def test_public_tool_without_call_keeps_the_existing_refusal():
    registry = Registry()
    spec = metadata(provides_tools=("private_tool",))
    assert register(registry, spec, {"private_fs": object()}) is None
    assert registry.disabled() == {"private.worker": "нет entrypoints['call']"}


def test_no_tools_no_services_no_entrypoints_still_fails_registration():
    registry = Registry()
    spec = metadata(internal_services=(), entrypoints={})
    assert register(registry, spec, {"private_fs": object()}) is None
    assert registry.disabled() == {"private.worker": "нет entrypoints['call']"}
