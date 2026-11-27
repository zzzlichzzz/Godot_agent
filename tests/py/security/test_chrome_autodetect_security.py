"""SEC-TF6-CHROME: Chrome auto-detection respects explicit env, fails closed, never leaks profiles."""
from importlib import import_module
import os
from pathlib import Path
import pytest

from python.channels.http import app as http_app


def test_preserves_valid_explicit_chrome_env_without_overwriting(tmp_path, monkeypatch):
    chrome_paths = import_module('python.runtime.chrome_paths')
    explicit = tmp_path / 'explicit/chrome.exe'
    explicit.parent.mkdir(parents=True)
    explicit.write_bytes(b'explicit')
    detected = tmp_path / 'other/chrome.exe'
    detected.parent.mkdir(parents=True)
    detected.write_bytes(b'other')

    monkeypatch.setenv('GODOT_AGENT_CHROME_PATH', str(explicit))
    monkeypatch.setattr(chrome_paths, 'detect_chrome_path', lambda *a, **kw: str(detected))
    chosen = chrome_paths.configure_chrome_env()
    assert chosen == str(explicit)
    assert os.environ['GODOT_AGENT_CHROME_PATH'] == str(explicit)


def test_invalid_directory_or_user_profile_paths_are_rejected(tmp_path):
    chrome_paths = import_module('python.runtime.chrome_paths')
    chrome_dir = tmp_path / 'not_a_file'
    chrome_dir.mkdir()
    profile_like = tmp_path / 'Google' / 'Chrome' / ('User ' + 'Data') / 'chrome.exe'
    profile_like.parent.mkdir(parents=True)
    profile_like.write_bytes(b'trap')

    assert chrome_paths.detect_chrome_path(
        environ={},
        standard_paths=(chrome_dir, profile_like),
        edge_paths=(),
        registry_lookup=lambda: str(profile_like),
    ) is None


def test_registry_errors_do_not_crash_startup(tmp_path, monkeypatch):
    chrome_paths = import_module('python.runtime.chrome_paths')
    monkeypatch.delenv('GODOT_AGENT_CHROME_PATH', raising=False)

    class _BrokenWinreg:
        HKEY_LOCAL_MACHINE = 0x80000002
        KEY_READ = 0x20019

        def OpenKey(self, *args):
            raise OSError('access denied')

    monkeypatch.setattr(chrome_paths, '_winreg_module', lambda: _BrokenWinreg())
    assert chrome_paths.read_registry_chrome_path() is None

    monkeypatch.setattr(chrome_paths, 'detect_chrome_path', lambda *a, **kw: None)
    project = tmp_path / 'proj'
    project.mkdir()
    (project / 'project.godot').write_text('[application]\nconfig/name="sec"\n', 'utf-8')
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'godot_agent_token.txt').write_text('SYNTHETIC-CHROME-SEC-TOKEN', 'utf-8')
    app = http_app.create_app(project, state, native_routes=True)
    assert app is not None and 'GODOT_AGENT_CHROME_PATH' not in os.environ
