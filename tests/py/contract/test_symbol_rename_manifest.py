"""tests/py/contract/test_symbol_rename_manifest.py - манифест-вклад editing.symbol_rename.

У модуля нет своего инструмента: он отдаёт вклад (ADR-0004). Проверяется, что
манифест объявляет только вклад, что реестр видит компилятор, что загрузчик
поднимает модуль без `provides_tools` и что собственного артефакта
(`contract/capabilities/symbol_rename.json`) не появляется.
"""

from pathlib import Path

import pytest

from python.kernel.errors import AppError
from python.modules.editing import symbol_rename
from python.modules.editing.symbol_rename import app as rename_app
from python.modules.editing.symbol_rename import module as rename_module
from python.modules.editing.symbol_rename import tools as rename_tools
from python.modules.editing.symbol_rename.domain.compiler import compile_plan
from python.protocol.registry import Registry
from python.runtime.module_loader import load_one

ROOT = Path(__file__).resolve().parents[3]


def test_manifest_declares_contribution_only():
    """Манифест: без `provides_tools`, с двумя целями вклада и сервисом."""
    spec = rename_module.MODULE
    assert spec.id == "editing.symbol_rename"
    assert tuple(spec.provides_tools) == ()
    assert tuple(spec.contributes_to) == ("editing.write_preview",
                                          "code_intel.usages")
    assert tuple(spec.internal_services) == ("symbol_rename_compiler",)
    assert tuple(spec.capabilities) == ("editing.symbol_rename",)
    assert "call" not in spec.entrypoints


def test_tools_module_publishes_no_tool_but_one_contribution():
    """`TOOLS = ()` и ровно один вклад; он указывает на компилятор домена."""
    assert rename_tools.TOOLS == ()
    assert rename_tools.CONTRIBUTIONS == (symbol_rename.COMPILER,)
    assert rename_tools.CONTRIBUTIONS[0].op == "symbol_rename"
    assert rename_tools.CONTRIBUTIONS[0].compile is compile_plan


def test_registry_sees_compiler_as_contribution():
    """Реестр раскладывает вклад по обеим целям и не публикует имени."""
    registry = Registry()
    registry.add_module(rename_module.MODULE, rename_tools.TOOLS, {},
                        rename_tools.CONTRIBUTIONS)
    assert registry.names() == []
    assert [item.op for item in registry.contributions("editing.write_preview")] == \
        ["symbol_rename"]
    assert [item.op for item in registry.contributions("code_intel.usages")] == \
        ["symbol_rename"]
    assert registry.contributions("context") == ()


def test_loader_accepts_contribution_without_tools():
    """«нет TOOLS» — только для модуля без вкладов: здесь их два (R-05)."""
    loaded = load_one(ROOT / "python" / "modules" / "editing"
                      / "symbol_rename" / "module.py")
    assert loaded.spec.id == "editing.symbol_rename"
    assert loaded.tools == ()
    assert [item.op for item in loaded.contributions] == ["symbol_rename"]


def test_no_own_capability_artifact():
    """Своего инструмента нет — нет и артефакта с его именем (ADR-0006)."""
    assert not (ROOT / "contract" / "capabilities" / "symbol_rename.json").exists()


def test_app_validates_request_before_plan():
    """Сценарий вклада проверяет запрос теми же правилами, что и воронка (R-04)."""
    with pytest.raises(AppError) as caught:
        rename_app.build_plan({"kind": "nope", "old_name": "a", "new_name": "b"},
                              {}, "strict", False)
    assert caught.value.kind == "invalid_input"
