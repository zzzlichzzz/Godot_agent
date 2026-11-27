"""Lazy corrected-native read adapter; all index/log state stays in the profile.

No native initializer, migration, function-card dependency or network activation.
The shared lock protects legacy data/history overrides and cache-migration suppression.
"""
import hashlib
from contextlib import nullcontext
import os
from pathlib import Path
from threading import RLock

from python.kernel.errors import AppError

_LOCK = RLock()


def _contains(root, path):
    try:
        return os.path.commonpath((root, path)) == root
    except ValueError:
        return False


class LibrarianRead:
    project_view = None

    def view(self, **options):
        return self.project_view(self._project,self.addon_dir,**options) if self.project_view else nullcontext(self._project)

    def __init__(self, project_root, state_dir, addon_dir):
        self._project = os.path.abspath(os.fspath(project_root))
        self._state = Path(state_dir).absolute()
        self.addon_dir = str(Path(addon_dir).absolute())
        key = hashlib.sha256(self._project.encode("utf-8")).hexdigest()
        self.storage_base = self._state / "context_ask" / key
        self.log_path = self.storage_base / "minilich_brain" / "librarian_log.jsonl"
        self.history_dir = self.storage_base / "agent_history"

    def _guard_storage(self):
        profile = os.path.normcase(os.path.realpath(self._state))
        project = os.path.normcase(os.path.realpath(self._project))
        paths = (self.storage_base, self.log_path.parent, self.log_path, self.history_dir,
                 self.history_dir / "snapshots", self.history_dir / "journal.json",
                 self.history_dir / "godot_api_cache.json")
        for path in paths:
            actual = os.path.normcase(os.path.realpath(path))
            if _contains(project, actual) or not _contains(profile, actual):
                raise AppError("denied", "хранилище ask должно оставаться вне проекта и внутри профиля")

    def answer(self, query: str, budget_chars: int = 8000, *, allow_addons: bool = False,
               allow_self_edit: bool = False, target: str | None = None) -> str:
        if not os.path.isdir(self._project):
            raise AppError("not_found", "корень проекта не найден")
        self._guard_storage()
        with _LOCK:
            from python.substrate.llm import runtime_bindings
            runtime_bindings.register()
            from . import librarian, ml_data
            from python.substrate.store import history_manager
            from python.substrate.engine import gd_api_cache
            if target is not None and not librarian.can_read_project_path(
                    target, self._project, addon_dir=self.addon_dir,
                    allow_addons=allow_addons, allow_self_edit=allow_self_edit):
                raise AppError("denied", "физический путь запроса закрыт политикой проекта")
            previous = ml_data._BASE_OVERRIDE
            previous_history = history_manager._STORAGE_OVERRIDE
            previous_migration = gd_api_cache._migrate_legacy_addon_cache
            try:
                gd_api_cache._migrate_legacy_addon_cache = lambda _addon_dir: None
                history_manager.set_storage_dir(str(self.storage_base))
                history_path = history_manager._STORAGE_OVERRIDE
                if not history_path or os.path.normcase(os.path.abspath(history_path)) != os.path.normcase(str(self.history_dir)):
                    raise AppError("denied", "хранилище истории профиля ask недоступно")
                routed = ml_data.set_storage_base(str(self.storage_base))
                if not routed or os.path.normcase(os.path.abspath(routed)) != os.path.normcase(str(self.log_path.parent)):
                    raise AppError("denied", "хранилище профиля ask недоступно")
                self._guard_storage()
                from python.substrate.fs.project_view import view_addon
                from .ml_project_index import EXTS
                with self.view(allow_addons=allow_addons,allow_self_edit=allow_self_edit,indexed=True,suffixes=EXTS | {'.godot'}) as root:
                    return librarian.answer(root, query, budget_chars=budget_chars,
                        addon_dir=view_addon(root,self._project,self.addon_dir), allow_addons=allow_addons,
                        allow_self_edit=allow_self_edit)
            finally:
                ml_data._BASE_OVERRIDE = previous
                history_manager._STORAGE_OVERRIDE = previous_history
                gd_api_cache._migrate_legacy_addon_cache = previous_migration
