"""kernel/tool_spec.py - дескриптор возможности (R-05, ADR-0006).

Источник правды — `ToolSpec` в `modules/<область>/<фича>/tools.py`;
`contract/capabilities/*.json` — генерируемый артефакт (его пишет
`tools/gen_contract.py`). Расхождение артефакта и дескриптора — ошибка сборки.
"""

import re
from dataclasses import dataclass, field

from .errors import KINDS

EFFECTS = ("read", "write", "exec")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
CONTRACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ToolSpec:
    """Что клиент может вызвать: имя, схемы, эффекты, идемпотентность, ошибки."""

    name: str
    description: str
    args: dict
    result: dict
    effects: str = "read"
    idempotent: bool = True
    errors: tuple = ()
    availability: str = "*"
    cost: str = "cheap"
    requires_preview: bool = False
    limits: dict = field(default_factory=dict)

    def __post_init__(self):
        if not NAME_RE.match(self.name):
            raise ValueError("tool_name должен быть плоским: %r" % (self.name,))
        if self.effects not in EFFECTS:
            raise ValueError("effects должен быть одним из %s: %r" % (EFFECTS, self.effects))
        if not str(self.description or "").strip():
            raise ValueError("пустое описание инструмента %r" % (self.name,))
        for kind in self.errors:
            if kind not in KINDS:
                raise ValueError("неизвестный kind %r у %r" % (kind, self.name))
        if self.requires_preview and self.effects == "read":
            raise ValueError("read-инструменту не нужен preview (R-12): %r" % (self.name,))
        if not isinstance(self.args, dict) or not isinstance(self.result, dict):
            raise ValueError("args/result должны быть JSON-схемами: %r" % (self.name,))

    def contract(self, module_id, capability_id):
        """Сгенерированный артефакт для клиентов и CI (ADR-0006)."""
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "module_id": module_id,
            "capability_id": capability_id,
            "tool_name": self.name,
            "description": self.description,
            "input_schema": self.args,
            "result_schema": self.result,
            "effects": [self.effects],
            "idempotent": bool(self.idempotent),
            "requires_preview": bool(self.requires_preview),
            "errors": list(self.errors),
            "availability": self.availability,
            "cost": self.cost,
            "limits": dict(self.limits),
        }

    def mcp(self):
        """Форма `tools/list` канала MCP."""
        return {"name": self.name, "description": self.description,
                "inputSchema": self.args}

