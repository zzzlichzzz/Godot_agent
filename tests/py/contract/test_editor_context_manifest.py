"""Контракт вклада `context.editor_context` (R-05, ADR-0004, R-15).

Своего `ToolSpec` у вклада нет: секция `editor` отдаётся реестру вкладов, а
артефакта `contract/capabilities` модуль не создаёт. Инвентарь инструментов
headless не растёт - иначе срез протёк через `provides_tools`.
"""

import json
from pathlib import Path

from python.modules.context.editor_context.app import SECTION
from python.modules.context.editor_context.module import MODULE
from python.modules.context.editor_context import tools as contribution_tools

ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES = ROOT / "contract" / "capabilities"


def test_manifest_declares_contribution():
    """Манифест: профиль editor, вклад в context, порт editor, без инструментов."""
    assert MODULE.id == "context.editor_context"
    assert MODULE.environment == "editor"
    assert tuple(MODULE.provides_tools) == ()
    assert tuple(MODULE.contributes_to) == ("context",)
    assert tuple(MODULE.requires_ports) == ("editor",)
    assert tuple(MODULE.internal_services) == ("editor_bridge",)


def test_no_tool_spec_of_its_own():
    """`TOOLS = ()` и ровно одна секция в `CONTRIBUTIONS`."""
    assert contribution_tools.TOOLS == ()
    assert contribution_tools.CONTRIBUTIONS == (SECTION,)
    assert SECTION.name == "editor"


def test_no_capabilities_artifact():
    """Артефакт возможностей у вклада не появляется."""
    assert not (CAPABILITIES / "editor_context.json").exists()
    for path in CAPABILITIES.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "context.editor_context" not in json.dumps(payload), path.name


def test_editor_is_not_a_tool():
    """Имя `editor` не становится инструментом: секция, не примитив."""
    assert "editor" not in contribution_tools.TOOLS
    assert SECTION.name not in [tool for tool in contribution_tools.TOOLS]
