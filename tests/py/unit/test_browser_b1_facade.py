"""D24/D25 glue: owned plain process, attach only, own file targets and cleanup."""
from pathlib import Path

import pytest


def _new(env, **kwargs):
    return env.module.ReadOnlyBrowser('fake-chrome.exe', 'fake-driver.exe', **kwargs)


def test_pinned_launch_profile_flags_and_no_focus(b1_browser_env):
    env = b1_browser_env()
    browser = _new(env)
    expected = ['fake-chrome.exe', '--remote-debugging-port=9222',
                '--user-data-dir=' + str(env.local / 'Godot_AI_Profile'),
                '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
                '--disable-background-timer-throttling', '--disable-features=CalculateNativeWinOcclusion', 'about:blank']
    assert env.launch_args == expected
    assert set(env.launch_kwargs) == {'startupinfo', 'close_fds'}
    assert env.launch_kwargs['close_fds'] is True
    startup = env.launch_kwargs['startupinfo']
    assert startup.dwFlags & env.module.subprocess.STARTF_USESHOWWINDOW
    assert startup.wShowWindow == 7
    assert browser._process is env.process
    browser.close()


def test_selenium_only_attaches_with_non_inherited_handles(b1_browser_env):
    env = b1_browser_env()
    browser = _new(env)
    assert env.options.experimental_options == {'debuggerAddress': '127.0.0.1:9222'}
    assert env.options.binary_location == 'fake-chrome.exe'
    assert env.options.arguments == []
    assert env.services[0].kwargs == {'executable_path': 'fake-driver.exe', 'popen_kw': {'close_fds': True}}
    assert env.http_closed and ('proxy', {}) in env.calls
    browser.close()


def test_busy_port_refuses_before_launch_or_owner_query(b1_browser_env):
    env = b1_browser_env(busy=True)
    with pytest.raises(RuntimeError, match='9222'):
        _new(env)
    assert env.launch_args is None and env.cdp is None and env.services == []
    assert not any(call[0] == 'http.open' for call in env.calls)


def test_exclusive_probe_not_tcp_refusal_proves_port_available(b1_browser_env, monkeypatch):
    env = b1_browser_env()

    def no_tcp_refusal(*args, **kwargs):
        raise TimeoutError('Windows silently drops a closed-port connection')

    monkeypatch.setattr(env.module.socket, 'create_connection', no_tcp_refusal)
    with _new(env):
        assert ('probe.option', (env.module.socket.SOL_SOCKET, env.module.socket.SO_EXCLUSIVEADDRUSE, 1)) in env.calls
        assert ('probe.bind', ('127.0.0.1', 9222)) in env.calls
        assert env.calls.index(('probe.close',)) < env.calls.index(('Popen',))


def test_indeterminate_bind_failure_refuses_before_launch(b1_browser_env, monkeypatch):
    env = b1_browser_env()

    def denied(*args, **kwargs):
        raise PermissionError('exclusive bind not available')

    monkeypatch.setattr(env.module.socket, 'socket', denied)
    with pytest.raises(RuntimeError, match='9222'):
        _new(env)
    assert env.launch_args is None and env.cdp is None and env.services == []


def test_readiness_failure_never_attaches_and_terminates_only_own_process(b1_browser_env):
    env = b1_browser_env(ready=False)
    with pytest.raises(RuntimeError):
        _new(env)
    assert env.driver is None and env.services == []
    assert ('process.terminate', 321) in env.calls


def test_owner_mismatch_does_not_close_foreign_browser(b1_browser_env):
    env = b1_browser_env(owner=False)
    with pytest.raises(RuntimeError, match='owner'):
        _new(env)
    assert env.services == [] and env.driver is None and env.cdp.closed
    assert not any(call[0] == 'Browser.close' for call in env.cdp.calls)
    assert ('process.terminate', 321) in env.calls


def test_failed_selenium_attach_stops_own_service_and_browser(b1_browser_env):
    env = b1_browser_env(attach_error=True)
    with pytest.raises(RuntimeError, match='attach'):
        _new(env)
    assert env.services[0].stopped and env.cdp.closed
    assert any(call[0] == 'Browser.close' for call in env.cdp.calls)
    assert env.process.returncode == 0


def test_open_read_close_binds_exact_target_not_first(b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        first, second = browser.open('file:///owned/A.html'), browser.open('file:///owned/B.html')
        assert browser.read(second) == {'title': 'session-' + second, 'text': 'session-' + second}
        evaluated = [call for call in env.cdp.calls if call[0] == 'Runtime.evaluate']
        assert evaluated[-1][2] == 'session-' + second
        created = [call for call in env.cdp.calls if call[0] == 'Target.createTarget']
        assert all(call[1] == {'url': 'about:blank', 'newWindow': False, 'background': True} for call in created)
        browser.close_tab(second)
        browser.close_tab(first)
        assert browser._tabs == {}
    assert env.driver.quit_called and env.services[0].stopped and env.cdp.closed


@pytest.mark.parametrize('method', ['Target.attachToTarget', 'Page.enable', 'Page.navigate'])
def test_open_failure_closes_only_just_created_target(method, b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        env.fail_method = method
        with pytest.raises(RuntimeError, match='injected'):
            browser.open('file:///owned/A.html')
        assert browser._tabs == {}
        closed = [call for call in env.cdp.calls if call[0] == 'Target.closeTarget']
        assert closed == [('Target.closeTarget', {'targetId': 'own-1'}, None)]


def test_foreign_target_cannot_be_read_or_closed(b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        before = len(env.cdp.calls)
        with pytest.raises(ValueError):
            browser.read('foreign')
        with pytest.raises(ValueError):
            browser.close_tab('foreign')
        assert len(env.cdp.calls) == before


def test_navigation_error_response_closes_owned_target(b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        env.navigate_error = 'net::ERR_FILE_NOT_FOUND'
        with pytest.raises(RuntimeError, match='ERR_FILE_NOT_FOUND'):
            browser.open('file:///owned/missing.html')
        assert browser._tabs == {}
        assert ('Target.closeTarget', {'targetId': 'own-1'}, None) in env.cdp.calls


@pytest.mark.parametrize('uri', ['https://example.invalid/', 'file://remote/share/x.html', 'about:blank', 'javascript:1'])
def test_facade_rejects_non_local_file_urls(uri, b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        before = len(env.cdp.calls)
        with pytest.raises(ValueError):
            browser.open(uri)
        assert len(env.cdp.calls) == before


def test_refused_target_close_does_not_forget_owned_target(b1_browser_env):
    env = b1_browser_env()
    with _new(env) as browser:
        target = browser.open('file:///owned/A.html')
        env.close_success = False
        with pytest.raises(RuntimeError):
            browser.close_tab(target)
        assert target in browser._tabs


def test_quit_failure_still_stops_service_and_own_browser(b1_browser_env):
    env = b1_browser_env(quit_error=True)
    browser = _new(env)
    browser.close()
    assert env.services[0].stopped and env.cdp.closed and env.process.returncode == 0
    browser.close()


def test_disposable_live_profile_adds_only_authorized_first_run_flag(b1_browser_env):
    env = b1_browser_env()
    profile = env.local / ('Godot_AI_Profile_B1_' + 'a' * 32)
    profile.mkdir()
    with _new(env, live_profile=profile):
        assert '--user-data-dir=' + str(profile) in env.launch_args
        assert env.launch_args[-2:] == ['--no-first-run', 'about:blank']
    assert profile.exists()


def test_production_profile_contents_are_not_read(b1_browser_env, monkeypatch):
    env = b1_browser_env()
    profile = env.local / 'Godot_AI_Profile'
    profile.mkdir()
    sentinel = profile / 'untouched.txt'
    sentinel.write_bytes(b'owned-test-sentinel')
    original = Path.iterdir

    def guarded(path):
        assert path != profile, 'production profile must not be enumerated'
        return original(path)

    monkeypatch.setattr(Path, 'iterdir', guarded)
    with _new(env):
        pass
    assert sentinel.read_bytes() == b'owned-test-sentinel'
