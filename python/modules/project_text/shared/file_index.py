"""Physical identities for read/tree only; accepted search and fs are unchanged."""
import os

from python.kernel.errors import AppError
from .policy import can_read_project_path


class ProjectTextFileSystem:
    def __init__(self, fs):
        self.fs = fs
        self.root = os.path.realpath(fs.project_root)

    def _relative(self, path):
        real = os.path.realpath(path)
        if os.path.normcase(os.path.commonpath((self.root, real))) != os.path.normcase(self.root):
            raise ValueError("outside")
        rel = os.path.relpath(real, self.root).replace("\\", "/")
        return "" if rel == "." else rel

    def _agent(self, policy):
        path = policy.agent_dir
        if not path or not os.path.isabs(path) or any(part in (".", "..") for part in path.replace("\\", "/").split("/")):
            return None
        try:
            rel = self._relative(path)
        except (ValueError, OSError):
            return None
        parts = rel.split("/")
        return rel if len(parts) >= 2 and parts[0].casefold() == "addons" and os.path.isdir(path) else None

    def resolve(self, path, policy, tree=False):
        if not isinstance(path, str) or not path.startswith("res://") or "\x00" in path:
            raise AppError("invalid_input", "Путь должен быть res:// без NUL")
        suffix = path[6:].replace("\\", "/")
        if suffix.startswith("/") or (len(suffix) > 1 and suffix[1] == ":"):
            raise AppError("invalid_input", "Абсолютный путь запрещён")
        try:
            rel = self._relative(os.path.join(self.root, suffix))
        except (ValueError, OSError):
            message = ("Путь вне проекта отклонен: " if tree else "Путь отклонён политикой доступа (read): ")
            raise AppError("denied", message + path) from None
        if tree and (rel.casefold() == ".agent_history" or rel.casefold().startswith(".agent_history/")):
            raise AppError("denied", "Доступ к служебной папке истории запрещён.")
        if not can_read_project_path(rel, policy, self._agent(policy)):
            raise AppError("denied", "Путь отклонён политикой доступа (read): " + path)
        return rel

    def read_text(self, rel):
        return self.fs.read_text(rel)

    def is_file(self, rel):
        return self.fs.is_file(rel) if rel else False

    def is_dir(self, rel):
        return os.path.isdir(os.path.join(self.root, rel))

    def entries(self, base, policy, visible):
        agent = self._agent(policy)
        def accept(row):
            allowed = can_read_project_path(row["path"], policy, agent)
            if row["type"] == "dir" and agent and policy.allow_self_edit:
                allowed = allowed or agent.casefold().startswith(row["path"].casefold() + "/")
            return allowed and visible(row, base)
        return self.fs.list_entries(base, accept=accept)
