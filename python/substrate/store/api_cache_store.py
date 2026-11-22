"""Read-only API snapshot adapter; never refresh, migrate, mkdir or write.

External state wins; old project/bundled snapshots are compatibility input.
As in the reference, truthy classes are cached and falsy class records retained.
"""
import hashlib
import json
from pathlib import Path

from python.kernel.limits import READ_TEXT_MAX_BYTES


class ApiCacheStore:
    def __init__(self, project_root, state_dir=None, addon_dir=None):
        self._project = Path(project_root).absolute()
        self._state = Path(state_dir) if state_dir is not None else None
        self._addon = Path(addon_dir) if addon_dir is not None else None
        self._classes = {}

    @property
    def cache_path(self):
        if self._state is None:
            return self._project / '.agent_history' / 'godot_api_cache.json'
        key = hashlib.sha256(str(self._project).encode('utf-8')).hexdigest()
        return self._state / 'api_cache' / (key + '.json')

    @staticmethod
    def _read(path):
        try:
            if path.stat().st_size > READ_TEXT_MAX_BYTES:
                return {}
            with path.open('rb') as handle:
                raw = handle.read(READ_TEXT_MAX_BYTES + 1)
            if len(raw) > READ_TEXT_MAX_BYTES:
                return {}
            record = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, ValueError):
            return {}
        classes = record.get('classes', {}) if isinstance(record, dict) else {}
        return classes if isinstance(classes, dict) else {}

    def classes(self):
        if self._classes:
            return self._classes
        classes = self._read(self.cache_path)
        legacy = self._project / '.agent_history' / 'godot_api_cache.json'
        if not classes and legacy != self.cache_path:
            classes = self._read(legacy)
        if not classes and self._addon is not None:
            bundled = self._addon / 'agent_api_cache' / 'default_api_cache.json'
            if not bundled.is_file():
                bundled = self._addon / 'default_api_cache.json'
            classes = self._read(bundled)
        self._classes = classes
        return classes

    @staticmethod
    def _read_snapshot(path):
        """Fresh classes and version from one bounded JSON read (ADR-0009)."""
        try:
            if path.stat().st_size > READ_TEXT_MAX_BYTES:
                return {}, ''
            with path.open('rb') as handle:
                raw = handle.read(READ_TEXT_MAX_BYTES + 1)
            if len(raw) > READ_TEXT_MAX_BYTES:
                return {}, ''
            record = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, ValueError):
            return {}, ''
        classes = record.get('classes', {}) if isinstance(record, dict) else {}
        if not isinstance(classes, dict) or not classes:
            return {}, ''
        version = record.get('godot_version', '')
        return classes, version if isinstance(version, str) else ''

    def snapshot(self):
        """Same fallback order as classes(), without touching its memoized state."""
        classes, version = self._read_snapshot(self.cache_path)
        legacy = self._project / '.agent_history' / 'godot_api_cache.json'
        if not classes and legacy != self.cache_path:
            classes, version = self._read_snapshot(legacy)
        if not classes and self._addon is not None:
            bundled = self._addon / 'agent_api_cache' / 'default_api_cache.json'
            if not bundled.is_file():
                bundled = self._addon / 'default_api_cache.json'
            classes, version = self._read_snapshot(bundled)
        return classes, version

    def version(self):
        """Read-only convenience; api uses snapshot() to keep fields coherent."""
        return self.snapshot()[1]
