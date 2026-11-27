"""BUG-008 / section 1.5: Chrome/Edge auto-detection at server startup and fail-closed errors."""
from importlib import import_module
from types import SimpleNamespace
import os
from pathlib import Path
import pytest

from python.kernel.errors import AppError
from python.channels.http import app as http_app
from python.channels.http import exe_bootstrap


CHROME_MISSING_MSG = 'Chrome не найден, укажите путь в настройках'


def _clear_chrome_env(monkeypatch):
    monkeypatch.delenv('GODOT_AGENT_CHROME_PATH', raising=False)


def _deployed(tmp_path):
    project = tmp_path / 'project'
    addon = project / 'addons/godot_agent'
    exe = addon / 'python/dist/godot_agent_server.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'SYNTHETIC-NOT-AN-EXE')
    (project / 'project.godot').write_text('[application]\nconfig/name="c8browser"\n', 'utf-8')
    (addon / 'plugin.cfg').write_text('[plugin]\n', 'utf-8')
    state = tmp_path / 'roaming' / 'Godot/app_userdata/c8browser'
    return project, state, exe


def test_detect_chrome_checks_standard_paths_and_edge_in_order(tmp_path):
    chrome_paths = import_module('python.runtime.chrome_paths')
    local_app = tmp_path / 'local'
    pf_chrome = tmp_path / 'pf/Google/Chrome/Application/chrome.exe'
    pf86_chrome = tmp_path / 'pf86/Google/Chrome/Application/chrome.exe'
    local_chrome = local_app / 'Google/Chrome/Application/chrome.exe'
    edge = tmp_path / 'pf/Microsoft/Edge/Application/msedge.exe'
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b'edge')

    order = (pf_chrome, pf86_chrome, local_chrome, edge)
    assert chrome_paths.detect_chrome_path(
        environ={'LOCALAPPDATA': str(local_app)},
        standard_paths=(pf_chrome, pf86_chrome, local_chrome),
        edge_paths=(edge,),
        registry_lookup=lambda: None,
    ) == str(edge)

    local_chrome.parent.mkdir(parents=True)
    local_chrome.write_bytes(b'local')
    assert chrome_paths.detect_chrome_path(
        environ={'LOCALAPPDATA': str(local_app)},
        standard_paths=(pf_chrome, pf86_chrome, local_chrome),
        edge_paths=(edge,),
        registry_lookup=lambda: None,
    ) == str(local_chrome)

    reg_chrome = tmp_path / 'custom/chrome.exe'
    reg_chrome.parent.mkdir(parents=True)
    reg_chrome.write_bytes(b'reg')
    assert chrome_paths.detect_chrome_path(
        environ={'LOCALAPPDATA': str(tmp_path / 'absent')},
        standard_paths=(pf_chrome, pf86_chrome, tmp_path / 'absent/Google/Chrome/Application/chrome.exe'),
        edge_paths=(edge,),
        registry_lookup=lambda: f'"{reg_chrome}"',
    ) == str(reg_chrome)
    assert order


def test_detect_chrome_reads_hklm_app_paths_when_standard_absent(tmp_path, monkeypatch):
    chrome_paths = import_module('python.runtime.chrome_paths')
    reg_chrome = tmp_path / 'vendor/Chrome/chrome.exe'
    reg_chrome.parent.mkdir(parents=True)
    reg_chrome.write_bytes(b'chrome-binary')

    seen = []

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _FakeWinreg:
        HKEY_LOCAL_MACHINE = 0x80000002
        KEY_READ = 0x20019

        def OpenKey(self, root, subkey, *args):
            seen.append((root, subkey))
            return _Key()

        def QueryValueEx(self, key, name):
            assert name in ('', None)
            return f'"{reg_chrome}"', 1

    monkeypatch.setattr(chrome_paths, '_winreg_module', lambda: _FakeWinreg())
    found = chrome_paths.read_registry_chrome_path()
    assert found == str(reg_chrome)
    assert seen and seen[0][1] == r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'


def test_without_chrome_env_and_missing_chrome_fails_closed_on_startup_and_chat(tmp_path, monkeypatch):
    _clear_chrome_env(monkeypatch)
    chrome_paths = import_module('python.runtime.chrome_paths')
    monkeypatch.setattr(chrome_paths, 'detect_chrome_path', lambda *a, **kw: None)

    project, state, _ = _deployed(tmp_path)
    state.mkdir(parents=True)
    (state / 'godot_agent_token.txt').write_text('SYNTHETIC-CHROME-ABSENT-TOKEN', 'utf-8')

    app = http_app.create_app(project, state, native_routes=True)
    assert 'GODOT_AGENT_CHROME_PATH' not in os.environ

    gateway = app.extensions['godot_session'].gateway
    with pytest.raises(AppError) as err:
        gateway._ensure_browser()
    assert err.value.kind == 'unavailable'
    assert CHROME_MISSING_MSG in err.value.message

    with pytest.raises(RuntimeError, match=CHROME_MISSING_MSG):
        gateway.wait_driver(timeout=0.05)

    client = app.test_client()
    response = client.post('/chats/new', json={'kind': 'site', 'site_id': 'qwen'},
                           headers={'X-Agent-Token': 'SYNTHETIC-CHROME-ABSENT-TOKEN'})
    assert response.status_code == 503
    assert CHROME_MISSING_MSG in (response.get_json() or {}).get('error', '')


def test_autodetect_sets_env_on_exe_bootstrap_and_app_serve_and_browser_ready(tmp_path, monkeypatch):
    _clear_chrome_env(monkeypatch)
    chrome_paths = import_module('python.runtime.chrome_paths')
    fake_chrome = tmp_path / 'detected/chrome.exe'
    fake_chrome.parent.mkdir(parents=True)
    fake_chrome.write_bytes(b'fake-chrome-bin')
    monkeypatch.setattr(chrome_paths, 'detect_chrome_path', lambda *a, **kw: str(fake_chrome))

    project, state, exe = _deployed(tmp_path)
    monkeypatch.setattr(exe_bootstrap, 'ensure_token', lambda p, s: state.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(exe_bootstrap, 'configuration', lambda argv, ex, env: (project, state, 5000))

    seen_envs = []
    with monkeypatch.context() as scoped:
        scoped.setattr(http_app, 'serve', lambda p, s, port=0: seen_envs.append(os.environ.get('GODOT_AGENT_CHROME_PATH')))
        assert exe_bootstrap.main([]) == 0
    assert seen_envs == [str(fake_chrome)]

    _clear_chrome_env(monkeypatch)
    state.mkdir(parents=True, exist_ok=True)
    (state / 'godot_agent_token.txt').write_text('SYNTHETIC-CHROME-READY-TOKEN', 'utf-8')
    from python.channels.http import listener
    from python.substrate.llm import runtime_owner
    monkeypatch.setitem(runtime_owner._holder, 'owner', None)
    monkeypatch.setitem(runtime_owner._holder, 'driver_error', None)

    fake_driver = object()
    launched = []

    from python.substrate.llm.browser import facade
    real_cls = facade.ReadOnlyBrowser

    class _FakeBrowser(real_cls):
        def __init__(self, chrome_path, driver_path=None):
            launched.append((chrome_path, driver_path))
            self._owned = True
            self._process = SimpleNamespace(poll=lambda: None)
            self._driver = fake_driver

        def close(self):
            return None

    monkeypatch.setattr(facade, 'ReadOnlyBrowser', _FakeBrowser)

    def _inspect_listener(app, proj, st, port=0):
        assert os.environ.get('GODOT_AGENT_CHROME_PATH') == str(fake_chrome)
        gw = app.extensions['godot_session'].gateway
        driver = gw.wait_driver(timeout=0.05)
        assert driver is fake_driver
        runtime_owner.release_owner(gw._owned_browser)

    monkeypatch.setattr(listener, 'serve', _inspect_listener)
    importlib_serve = http_app.serve
    importlib_serve(project, state, port=0)
    assert launched == [(str(fake_chrome), None)]


@pytest.mark.parametrize(('failure', 'message'), [
    ('9222 availability unknown; refusing launch', '9222'),
    ('own Chrome debugger did not become ready', 'окну браузера'),
    ('debugger owner does not match own process', 'окну браузера'),
    ('session not created: private path', 'ChromeDriver'),
])
def test_existing_binary_launch_failure_is_not_reported_as_missing(tmp_path, monkeypatch, failure, message):
    project, state, _ = _deployed(tmp_path)
    state.mkdir(parents=True)
    (state / 'godot_agent_token.txt').write_text('SYNTHETIC-DIAGNOSTIC-TOKEN', 'utf-8')
    gw = http_app.create_app(project, state, native_routes=True).extensions['godot_session'].gateway
    def fail(timeout): raise RuntimeError(failure)
    monkeypatch.setattr(gw, '_ensure_browser', fail)
    with pytest.raises(RuntimeError, match=message) as err: gw.wait_driver()
    assert CHROME_MISSING_MSG not in str(err.value) and 'private path' not in str(err.value)
