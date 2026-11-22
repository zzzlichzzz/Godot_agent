"""kernel/module_spec.py - манифест модуля (R-05): кто он, что даёт, что требует.

Общий код знает о модуле только это. Импорт модуля не должен иметь побочных
эффектов: манифест — данные, а не запуск.
"""

import re
from dataclasses import dataclass, field

ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
ENVIRONMENTS = ("editor", "headless", "cli", "*")
#: Чем доказывается поведение: `corpus` - снапшоты эталона, `live` - механика
#: исполняется в GDScript редактора и проверяется живым тестом (R-07, R-18).
CORPUS_POLICIES = ("corpus", "live")


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    description: str = ""
    version: str = "0.1.0"
    kernel_api: str = "^1"
    godot: str = "^4.6"
    environment: str = "*"
    corpus: str = "corpus"
    provides_tools: tuple = ()
    contributes_to: tuple = ()
    internal_services: tuple = ()
    requires_ports: tuple = ()
    requires: tuple = ()
    recommends: tuple = ()
    capabilities: tuple = ()
    settings_schema: dict = field(default_factory=dict)
    entrypoints: dict = field(default_factory=dict)

    def __post_init__(self):
        if not ID_RE.match(self.id):
            raise ValueError("module id должен быть '<область>.<фича>': %r" % (self.id,))
        if self.environment not in ENVIRONMENTS:
            raise ValueError("environment должен быть из %s: %r"
                             % (ENVIRONMENTS, self.environment))
        if self.corpus not in CORPUS_POLICIES:
            raise ValueError("corpus должен быть из %s: %r"
                             % (CORPUS_POLICIES, self.corpus))
        if not (self.provides_tools or self.contributes_to or self.internal_services
                or self.entrypoints or self.capabilities):
            raise ValueError("модуль %r не объявляет ни provides_tools, "
                             "ни contributes_to" % (self.id,))
        if len(set(self.provides_tools)) != len(self.provides_tools):
            raise ValueError("повтор tool_name в %r" % (self.id,))

    @property
    def area(self):
        return self.id.split(".", 1)[0]

    @property
    def feature(self):
        return self.id.split(".", 1)[1]
