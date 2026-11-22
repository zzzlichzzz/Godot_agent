"""tests/py/integration/test_context_contributions.py - вклады `context` через реестр.

Владелец инструмента не импортирует чужие модули: секции приходят из реестра
(`ctx.registry.contributions("context")`). Проверяется, что вклад виден, его отказ
попадает в `unavailable`, падение вклада не валит вызов, а чтение контекста ничего
не меняет в проекте (R-12, ADR-0004).
"""

from types import SimpleNamespace

from python.kernel.paths import PathPolicy
from python.modules.context.gather import app as gather_app
from python.modules.context.shared.context_section import (ContextSection,
                                                           unavailable)
from python.modules.project_text.search import tools as search_tools
from python.protocol.registry import Registry
from python.runtime.context import ModuleContext
from python.substrate.fs.memory_fs import MemoryFileSystem

FILES = {"project.godot": "config_version=5", "scripts/player.gd": "extends Node\n"}


def _spec(module_id, contributes_to=("context",)):
    return SimpleNamespace(id=module_id, contributes_to=contributes_to)


def _ctx(section=None, contributions=None):
    """Контекст владельца: реестр с вкладом (если он есть) и ФС в памяти."""
    registry = Registry()
    if section is not None:
        registry.add_module(_spec("context.editor_context"), (), {},
                            tuple(contributions or (section,)))
    fs = MemoryFileSystem(dict(FILES))
    ctx = ModuleContext(profile="test", ports={"fs": fs},
                        path_policy=PathPolicy("D:/p"), registry=registry)
    return ctx, fs


def test_contribution_fills_section():
    """Вклад из реестра попадает в `sections`, а не в `unavailable`."""
    section = ContextSection("editor", lambda target: {"scene": None,
                                                       "path": target["path"]})
    ctx, _ = _ctx(section)
    answer = gather_app.call("context", {"sections": ["editor"]}, ctx)
    assert answer["available"] == ["editor"]
    assert answer["sections"]["editor"] == {"scene": None, "path": None}
    assert answer["unavailable"] == []


def test_contribution_refusal_becomes_unavailable():
    """`unavailable("no_bridge")` вклада — строка долга, а не ошибка вызова."""
    section = ContextSection("editor", lambda target: unavailable("no_bridge"))
    ctx, _ = _ctx(section)
    answer = gather_app.call("context", {"sections": ["project", "editor"]}, ctx)
    assert answer["available"] == ["project"]
    assert answer["unavailable"] == [{"name": "editor", "reason": "no_bridge"}]


def test_contribution_failure_does_not_break_call():
    """Падение вклада не валит пакет: секция честно недоступна с причиной."""
    def boom(target):
        raise RuntimeError("редактор умер")

    ctx, _ = _ctx(ContextSection("editor", boom))
    answer = gather_app.call("context", {"sections": ["editor"]}, ctx)
    assert answer["available"] == []
    assert answer["unavailable"] == [{"name": "editor", "reason": "failed"}]


def test_editor_without_contribution_is_no_module():
    """В headless вклада нет вовсе: причина `no_module`, а не ошибка."""
    ctx, _ = _ctx(None)
    answer = gather_app.call("context", {"sections": ["editor"]}, ctx)
    assert answer["available"] == []
    assert answer["unavailable"] == [{"name": "editor", "reason": "no_module"}]


def test_context_does_not_change_files():
    """Чтение контекста не пишет: состав и содержимое проекта те же (R-12)."""
    ctx, fs = _ctx(ContextSection("editor", lambda target: {"ok": True}))
    gather_app.call("context", {"sections": ["project", "tools", "editor"]}, ctx)
    assert fs.list_files() == sorted(FILES)
    assert all(fs.read_text(name) == text for name, text in FILES.items())


def test_registry_ignores_contribution_without_target():
    """Вклад без `contributes_to` в реестр не попадает: её некуда отдать."""
    section = ContextSection("editor", lambda target: {"ok": True})
    registry = Registry()
    registry.add_module(_spec("context.editor_context", contributes_to=()),
                        (), {}, (section,))
    assert registry.contributions("context") == ()


def test_tools_section_reads_registry_entries():
    """Секция `tools` строится по реестру: имена по алфавиту, эффекты из спеки."""
    registry = Registry()
    registry.add_module(SimpleNamespace(id="project_text.search",
                                        contributes_to=()),
                        (search_tools.SEARCH,), {"search": lambda args: None})
    fs = MemoryFileSystem(dict(FILES))
    ctx = ModuleContext(profile="test", ports={"fs": fs},
                        path_policy=PathPolicy("D:/p"), registry=registry)
    answer = gather_app.call("context", {"sections": ["tools"]}, ctx)
    assert answer["sections"]["tools"] == {"count": 1, "names": ["search"],
                                           "effects": {"search": "read"}}
