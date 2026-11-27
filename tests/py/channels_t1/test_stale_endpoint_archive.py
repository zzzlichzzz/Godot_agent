"""ADR-0092: safe archiving of dead-PID loopback http_endpoint.json without touching live/malformed claims."""
import json
import os
import subprocess
import sys
from unittest.mock import Mock
import pytest


@pytest.fixture
def patched_listener(monkeypatch, tmp_path):
    from python.channels.http import listener
    import werkzeug.serving

    project = tmp_path / 'project'
    project.mkdir()
    state = tmp_path / 'profile'
    state.mkdir()

    class Server:
        server_port = 54321
        closed = False
        ran = False

        def serve_forever(self):
            self.ran = True

        def server_close(self):
            self.closed = True

    server = Server()
    monkeypatch.setattr(werkzeug.serving, 'make_server', lambda host, port, app, threaded: server)
    return listener, server, project, state


def test_dead_pid_complete_loopback_endpoint_is_archived_preserving_exact_bytes(patched_listener):
    listener, server, project, state = patched_listener
    endpoint = state / 'http_endpoint.json'
    stale_record = {'host': '127.0.0.1', 'port': 5000, 'pid': 99999999, 'session_id': 'dead-session-id'}
    raw = (json.dumps(stale_record, sort_keys=True) + '\n').encode('utf-8')
    endpoint.write_bytes(raw)

    listener.serve(object(), project, state, port=5000)
    assert server.ran and server.closed
    assert not endpoint.exists()
    archived = list(state.glob('http_endpoint.stale-99999999-*.json'))
    assert len(archived) == 1
    assert archived[0].read_bytes() == raw


@pytest.mark.parametrize('pid_fn', ['live-self', 'access-denied'])
def test_live_or_inaccessible_pid_refuses_without_archiving(patched_listener, monkeypatch, pid_fn):
    listener, server, project, state = patched_listener
    endpoint = state / 'http_endpoint.json'
    pid = os.getpid() if pid_fn == 'live-self' else 88888888
    raw = (json.dumps({'host': '127.0.0.1', 'port': 5000, 'pid': pid, 'session_id': 'live-id'}) + '\n').encode('utf-8')
    endpoint.write_bytes(raw)
    if pid_fn == 'access-denied':
        monkeypatch.setattr(listener, '_pid_alive', lambda p: True)

    with pytest.raises(FileExistsError):
        listener.serve(object(), project, state, port=5000)
    assert not server.ran and server.closed
    assert endpoint.read_bytes() == raw
    assert list(state.glob('http_endpoint.stale-*')) == []


def test_hardlinked_dead_endpoint_is_never_archived(patched_listener):
    listener, server, project, state = patched_listener
    endpoint = state / 'http_endpoint.json'
    sentinel = state / 'sentinel.txt'
    raw = (json.dumps({'host': '127.0.0.1', 'port': 5000, 'pid': 99999999, 'session_id': 'link-id'}) + '\n').encode('utf-8')
    sentinel.write_bytes(raw)
    os.link(sentinel, endpoint)

    with pytest.raises(FileExistsError):
        listener.serve(object(), project, state, port=5000)
    assert not server.ran and server.closed
    assert endpoint.read_bytes() == raw and sentinel.read_bytes() == raw
    assert list(state.glob('http_endpoint.stale-*')) == []


@pytest.mark.parametrize('payload', [
    {'host': '0.0.0.0', 'port': 5000, 'pid': 99999999, 'session_id': 'bad-host'},
    {'host': '127.0.0.1', 'port': 80, 'pid': 99999999, 'session_id': 'bad-port'},
    {'host': '127.0.0.1', 'port': 5000, 'pid': True, 'session_id': 'bool-pid'},
    {'host': '127.0.0.1', 'port': 5000, 'pid': 99999999, 'session_id': ''},
    {'host': '127.0.0.1', 'port': 5000, 'pid': 99999999, 'session_id': 'x', 'extra': 1},
])
def test_noncanonical_endpoint_shape_refuses_without_archiving(patched_listener, payload):
    listener, server, project, state = patched_listener
    endpoint = state / 'http_endpoint.json'
    raw = (json.dumps(payload) + '\n').encode('utf-8')
    endpoint.write_bytes(raw)

    with pytest.raises(FileExistsError):
        listener.serve(object(), project, state, port=5000)
    assert not server.ran and server.closed
    assert endpoint.read_bytes() == raw
    assert list(state.glob('http_endpoint.stale-*')) == []


def test_win32_access_denied_treats_pid_as_live_fail_closed(monkeypatch):
    import ctypes
    from python.channels.http import listener
    if os.name != 'nt':
        pytest.skip('Windows-only OpenProcess last-error test')

    kernel = Mock()
    kernel.OpenProcess.return_value = 0
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: kernel)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5)
    assert listener._pid_alive(424242) is True

    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 87)
    assert listener._pid_alive(424242) is False
    assert listener._pid_alive(0x1_0000_0000 + 424242) is True


@pytest.mark.skipif(os.name != 'nt', reason='Windows-only wait statuses')
@pytest.mark.parametrize('status', [0x102, 0xFFFFFFFF])
def test_win32_wait_without_exit_proof_is_fail_closed(monkeypatch, status):
    import ctypes
    from python.channels.http import listener

    kernel = Mock()
    handle = 0x1_0000_0001
    kernel.OpenProcess.return_value = handle
    kernel.WaitForSingleObject.return_value = status
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: kernel)

    assert listener._pid_alive(424242) is True
    kernel.OpenProcess.assert_called_once_with(0x00100000, False, 424242)
    kernel.WaitForSingleObject.assert_called_once_with(handle, 0)
    kernel.CloseHandle.assert_called_once_with(handle)


@pytest.mark.skipif(os.name != 'nt', reason='Windows process handle lifetime')
@pytest.mark.parametrize('exit_code', [0, 259])
def test_exited_pid_with_retained_handle_does_not_block_startup(patched_listener, exit_code):
    listener, server, project, state = patched_listener
    endpoint = state / 'http_endpoint.json'
    # Popen retains its process handle until collection, including after wait().
    with subprocess.Popen([sys.executable, '-B', '-c', 'import sys; sys.exit(int(sys.argv[1]))',
                           str(exit_code)]) as child:
        assert child.wait(timeout=10) == exit_code
        raw = json.dumps(dict(host='127.0.0.1', port=5000, pid=child.pid, session_id='exited')).encode()
        endpoint.write_bytes(raw)

        listener.serve(object(), project, state, port=5000)

        archived, = state.glob(f'http_endpoint.stale-{child.pid}-*.json')
        assert archived.read_bytes() == raw
        assert server.ran and server.closed and not endpoint.exists()
