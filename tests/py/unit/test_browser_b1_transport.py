"""B-1 byte pins and transport cases, rebuilt from native observations, not old tests."""
import hashlib
import importlib
import json
from pathlib import Path
import threading

import pytest

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'fixtures/corpus/browser/b1'
WIRE = json.loads((BASE / 'wire.json').read_text(encoding='utf-8'))
HEADER = b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n'


def _transport():
    return importlib.import_module('python.substrate.llm.browser.cdp_ws')


def _random(n):
    return (bytes.fromhex(WIRE['random_key_hex']) * ((n + 3) // 4))[:n]


@pytest.mark.parametrize(('name', 'size', 'lines', 'sha', 'crlf', 'bare_lf'), [
    ('browser_manager.py', 12663, 193, '4afd245fbd4a4ab1cf95cb8be5435a6fc1ae30a788d891bcb2246f781e974d07', 189, 4),
    ('cdp_ws.py', 15867, 390, '3b5298dd76c061ce082828d9778b006b7fc68ed6dd1442e0bb4b95b5f95d339b', 0, 390),
])
def test_transport_is_byte_exact_native(name, size, lines, sha, crlf, bare_lf):
    data = (ROOT / 'python/substrate/llm/browser' / name).read_bytes()
    assert len(data) == size and len(data.splitlines()) == lines
    assert hashlib.sha256(data).hexdigest() == sha
    assert data.count(b'\r\n') == crlf and data.count(b'\n') - data.count(b'\r\n') == bare_lf


@pytest.mark.parametrize('chunk', [None, 1, 7], ids=['leftover', 'bytewise', 'split'])
@pytest.mark.parametrize('case', WIRE['receive'], ids=lambda case: case['id'])
def test_receive_native_frame_corpus(case, chunk, b1_socket, monkeypatch):
    module = _transport()
    raw = (BASE / case['input']['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case['input']['sha256']
    sock = b1_socket(HEADER + raw, chunk_size=chunk)
    monkeypatch.setattr(module.socket, 'create_connection', lambda *args, **kwargs: sock)
    monkeypatch.setattr(module.os, 'urandom', _random)
    ws = module.MiniWebSocket('ws://127.0.0.1:9222/own-fixture')
    result = ws.recv_message()
    if case['expected_none']:
        assert result is None
    else:
        assert len(result) == case['expected_bytes']
        assert hashlib.sha256(result).hexdigest() == case['expected_sha256']
    assert [data.hex() for data in sock.sent[1:]] == case['control_frames_hex']
    assert sock.timeouts == [None]
    ws.close()
    assert sock.closed is case['post_close_socket_closed']


@pytest.mark.parametrize('case', WIRE['send'], ids=lambda case: case['id'])
def test_send_is_masked_and_native_byte_exact(case, b1_socket, monkeypatch):
    module = _transport()
    text = (BASE / case['input']['file']).read_text(encoding='utf-8')
    sock = b1_socket(HEADER)
    monkeypatch.setattr(module.socket, 'create_connection', lambda *args, **kwargs: sock)
    monkeypatch.setattr(module.os, 'urandom', _random)
    ws = module.MiniWebSocket('ws://127.0.0.1:9222/own-fixture')
    ws.send_text(text)
    actual = sock.sent[1]
    assert actual[1] & 128
    assert len(actual) == case['expected_wire_bytes']
    assert hashlib.sha256(actual).hexdigest() == case['expected_wire_sha256']
    assert actual[:10].hex() == case['expected_prefix_hex']
    ws.close()
    assert sock.closed


@pytest.mark.parametrize('case', WIRE['connect'], ids=lambda case: case['id'])
def test_connect_transport_corpus(case):
    module = _transport()
    raw = (BASE / case['input']['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case['input']['sha256']
    assert [list(item) for item in module.decode_connect_frames(raw)] == case['expected']
    frames, consumed = module.decode_connect_frames_partial(raw)
    assert [list(item) for item in frames] == case['expected'] and consumed == case['consumed']


def test_cdp_ids_and_exact_flattened_session(b1_session):
    env = b1_session(result={'own': 'Свой 🐉'})
    assert env.session.send_command('Runtime.evaluate', {'expression': '1'}, session_id='B') == {'own': 'Свой 🐉'}
    assert env.session.send_command('Page.enable') == {'own': 'Свой 🐉'}
    assert [item['id'] for item in env.pipe.sent] == [1, 2]
    assert env.pipe.sent[0]['sessionId'] == 'B' and 'sessionId' not in env.pipe.sent[1]
    assert env.session._pending == {}


def test_cdp_error_and_timeout_remove_pending(b1_session):
    error = b1_session(error={'message': 'owned error'})
    with pytest.raises(error.module.WSError, match='owned error'):
        error.session.send_command('Page.enable')
    assert error.session._pending == {}
    timeout = b1_session(auto_reply=False)
    with pytest.raises(timeout.module.WSError, match='Timed out'):
        timeout.session.send_command('Page.enable', timeout=0.01)
    assert timeout.session._pending == {}


def test_cdp_events_skip_bad_json_and_preserve_session(b1_session):
    env = b1_session()
    seen, done = [], threading.Event()
    env.session.on_event('Own.event', lambda params: seen.append(('ordinary', params)))

    def received(params, session_id):
        seen.append(('flattened', params, session_id))
        done.set()

    env.session.on_session_event('Own.event', received)
    env.pipe.incoming.put(b'not-json')
    env.pipe.incoming.put(b'{"method":"Own.event","params":{"own":1},"sessionId":"B"}')
    assert done.wait(1)
    assert seen == [('ordinary', {'own': 1}), ('flattened', {'own': 1}, 'B')]


def test_dead_reader_refuses_new_commands(b1_session):
    env = b1_session()
    env.pipe.incoming.put(None)
    env.session._reader.join(timeout=1)
    assert not env.session.is_alive()
    with pytest.raises(env.module.WSError, match='closed'):
        env.session.send_command('Page.enable')


def test_reader_close_wakes_already_pending_command(b1_session):
    env = b1_session(auto_reply=False)
    errors, done = [], threading.Event()

    def pending():
        try:
            env.session.send_command('Page.enable', timeout=2)
        except env.module.WSError as exc:
            errors.append(str(exc))
            done.set()

    thread = threading.Thread(target=pending)
    thread.start()
    assert env.pipe.sent_event.wait(1)
    env.pipe.incoming.put(None)
    assert done.wait(1)
    thread.join(timeout=1)
    assert not thread.is_alive() and len(errors) == 1 and 'connection closed' in errors[0]
    assert env.session._pending == {}


def test_exact_target_discovery_never_selects_first_page(monkeypatch):
    module = _transport()
    targets = [{'type': 'page', 'id': 'A', 'webSocketDebuggerUrl': 'ws://own/A'},
               {'type': 'page', 'id': 'B', 'webSocketDebuggerUrl': 'ws://own/B'}]
    monkeypatch.setattr(module, 'list_targets', lambda *args, **kwargs: targets)
    assert module.find_page_ws_url_for_target('b') == 'ws://own/B'
    assert module.find_page_ws_url_for_target('missing') is None


def test_handshake_rejects_bad_status(b1_socket, monkeypatch):
    module = _transport()
    sock = b1_socket(b'HTTP/1.1 400 Bad Request\r\n\r\n')
    with pytest.raises(module.WSError, match='Unexpected'):
        module._ws_handshake(sock, '127.0.0.1:9222', '/fixture')
