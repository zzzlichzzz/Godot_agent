"""kernel/paths.py - PathPolicy: единственная точка решения о путях (R-13, SEC-12).

Политика отвечает на один вопрос: «можно ли читать этот путь проекта?» — и
делает это по строке относительного пути, без обращения к диску. Реальный
`realpath` и проверка выхода за корень живут в адаптере (`substrate/fs`):
здесь — правила, там — физика.

Шумовые каталоги (`.godot`, `__pycache__`, `node_modules`) — НЕ политика
доступа, а качество выдачи: это решает домен поиска.
"""

import os

HISTORY_DIR = ".agent_history"
ADDONS_DIR = "addons"


def normalize_rel(path):
    """Путь внутри проекта в вид `a/b.gd`; None, если путь вне проекта.

    Отклоняется: пустой путь, абсолютный (`/x`, `C:/x`), с `..`, с NUL.
    """
    value = str(path or "").replace("\\", "/").strip()
    if not value or "\x00" in value:
        return None
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        return None
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


class PathPolicy:
    """Что можно читать при текущей capability-политике профиля."""

    def __init__(self, project_root="", allow_addons=False, allow_self_edit=False,
                 agent_dir=None):
        self.project_root = str(project_root or "")
        self.allow_addons = bool(allow_addons)
        self.allow_self_edit = bool(allow_self_edit)
        self.agent_dir = str(agent_dir or "")
        self._agent_rel = self._relative_agent_dir()

    def _relative_agent_dir(self):
        if not (self.agent_dir and self.project_root):
            return None
        try:
            rel = os.path.relpath(os.path.abspath(self.agent_dir),
                                  os.path.abspath(self.project_root))
        except ValueError:
            return None
        return None if rel.startswith(os.pardir) else normalize_rel(rel)

    @property
    def agent_py_allowed(self):
        """`.py` — право видеть исходник агента, а не «просто расширение»."""
        return bool(self.allow_self_edit and self._agent_rel)

    def is_agent(self, rel):
        return bool(self._agent_rel and (rel == self._agent_rel
                                        or rel.startswith(self._agent_rel + "/")))

    @staticmethod
    def is_addon(rel):
        return rel == ADDONS_DIR or rel.startswith(ADDONS_DIR + "/")

    @staticmethod
    def is_history(rel):
        return rel == HISTORY_DIR or rel.startswith(HISTORY_DIR + "/")

    def deny_reason(self, rel):
        """Пустая строка — читать можно; иначе короткая причина для `denied`."""
        path = normalize_rel(rel)
        if path is None:
            return "путь вне проекта"
        if self.is_history(path):
            return "история агента закрыта"
        if self.is_agent(path):
            return "" if self.allow_self_edit else "исходники агента закрыты (developer mode выключен)"
        if self.is_addon(path):
            if self._agent_rel is None:
                return "корень агента неизвестен: аддоны закрыты (fail closed)"
            return "" if self.allow_addons else "аддоны закрыты"
        return ""

    def can_read(self, rel):
        return not self.deny_reason(rel)

    def protected_override_candidate(self, rel):
        """Deny-only integrity check, never permission to return or modify a script."""
        return (normalize_rel(rel) == rel and rel.endswith('.gd') and not self.can_read(rel)
                and (self.is_agent(rel) or self.is_addon(rel)) and not self.is_history(rel))
