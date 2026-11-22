"""B-2 net_monitor: Phase A guard pins (D29) + verbatim and behavior pins.

Cases are taken from the recorded corpus (fixtures/corpus/browser/b2), which
in turn was extracted from native test observations, not from old tests.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CHECK_LIMITS = ROOT / 'tools' / 'check_limits.py'


def _load_check_limits():
    spec = importlib.util.spec_from_file_location('b2_check_limits', CHECK_LIMITS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_lines(tmp_path, rel, count):
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_text(
        ''.join('x = %d\n' % i for i in range(count)), encoding='utf-8')
    return target


# --- Phase A: D29 class deviation for verbatim browser files -----------------

def test_guard_allows_verbatim_browser_456_lines(tmp_path, monkeypatch):
    """Native net_monitor.py is 456 lines: under substrate/llm/browser the
    verbatim deviation (D29) must admit it; before the guard fix this pin
    is red, after it green."""
    module = _load_check_limits()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'PYTHON', tmp_path / 'python')
    _write_lines(tmp_path, 'python/substrate/llm/browser/net_monitor.py', 456)
    assert module.check_files() == []


def test_guard_verbatim_limit_is_600_not_unlimited(tmp_path, monkeypatch):
    """The deviation is a ceiling of 600, not a free pass."""
    module = _load_check_limits()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'PYTHON', tmp_path / 'python')
    _write_lines(tmp_path, 'python/substrate/llm/browser/net_monitor.py', 601)
    violations = module.check_files()
    assert len(violations) == 1
    assert 'лимит 600' in violations[0]


import base64
import hashlib
import json
import time


# --- Corpus battery (R-16: inputs and expectations from the corpus) ----------

CORPUS = ROOT / 'fixtures' / 'corpus' / 'browser' / 'b2'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
NATIVE_NET_MONITOR_SHA = MANIFEST['source_sha256']
CASES = {case['id']: case for case in MANIFEST['cases']}


class FakeCDP:
    """Inert CDP double: emits recorded Network.* events, no real socket."""

    def __init__(self):
        self.handlers = {}
        self.calls = []
        self.get_body_calls = 0
        self.buffered = b''
        self.body = ''
        self.stream_error = None

    def on_event(self, name, cb):
        self.handlers[name] = cb

    def emit(self, method, params):
        cb = self.handlers.get(method)
        assert cb is not None, 'no handler for %s' % method
        cb(params)

    def send_command(self, method, params=None):
        self.calls.append(method)
        if method == 'Network.streamResourceContent':
            if self.stream_error is not None:
                raise self.stream_error
            data = base64.b64encode(self.buffered).decode('ascii') if self.buffered else ''
            return {'bufferedData': data}
        if method == 'Network.getResponseBody':
            self.get_body_calls += 1
            return {'body': self.body}
        raise AssertionError('unexpected command: %s' % method)


def make_monitor(module, cdp):
    class LineMonitor(module.BaseNetMonitor):
        CHAT_URL_SUBSTR = '/api/v2/chat/completions'
        RESPONSE_MIME_SUBSTR = 'text/event-stream'
        LOG_TAG = 'b2_corpus'

        def _decode_frames_partial(self, raw):
            consumed = raw.rfind(b'\n') + 1
            return raw[:consumed].decode('utf-8').splitlines(), consumed

        def _decode_frames(self, raw):
            return raw.decode('utf-8').splitlines()

        def _decode_final_tail(self, raw):
            if self.accept_tail:
                return [raw.decode('utf-8')]
            return []

        def _apply_event(self, obj):
            if obj == 'RAISE':
                raise ValueError('event application failed')
            if obj == 'DONE':
                self._message_status = 'FINISHED'
                self._generating = False
                self._assistant_message_count += 1
            else:
                self.parts.append(obj)

        def _reset_answer_state_locked(self):
            self.parts = []

        def _answer_len_locked(self):
            return len(''.join(self.parts))

        def current_text(self):
            with self._lock:
                return ''.join(self.parts)

    mon = LineMonitor(cdp)
    mon.accept_tail = False
    return mon


def snapshot(mon, cdp):
    return {
        'text': mon.current_text(),
        'message_status': mon.message_status(),
        'assistant_message_count': mon.assistant_message_count(),
        'generating': mon.is_generating(),
        'chat_request_count': mon.chat_request_count(),
        'answer_request_count': mon.answer_request_count(),
        'pop_http_error': mon.pop_http_error(),
        'get_response_body_calls': cdp.get_body_calls,
    }


def _wait(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.002)
    raise AssertionError('timeout waiting for condition')


def apply_step(mon, cdp, step):
    if 'post' in step:
        rid, url, method = step['post']
        cdp.emit('Network.requestWillBeSent',
                 {'requestId': rid, 'request': {'url': url, 'method': method}})
    elif 'response' in step:
        rid, url, status, mime = step['response']
        cdp.emit('Network.responseReceived',
                 {'requestId': rid,
                  'response': {'url': url, 'status': status, 'mimeType': mime}})
    elif 'chunk' in step:
        rid, data = step['chunk']
        cdp.emit('Network.dataReceived', {'requestId': rid, 'data': data})
    elif 'buffered' in step:
        cdp.buffered = base64.b64decode(step['buffered'])
    elif 'body' in step:
        cdp.body = step['body']
    elif 'stream_error' in step:
        cdp.stream_error = RuntimeError(step['stream_error'])
    elif 'flag' in step:
        name, value = step['flag']
        setattr(mon, name, value)
    elif 'wait_stream' in step:
        rid = step['wait_stream']
        _wait(lambda: bool(mon._stream_mode.get(rid)))
    elif 'wait_done' in step:
        rid = step['wait_done']
        _wait(lambda: (mon._stream_done.get(rid) is None
                       or mon._stream_done[rid].is_set()))
    elif 'finish' in step:
        mon._finish_request(step['finish'])
    elif 'loading_failed' in step:
        rid, error, canceled = step['loading_failed']
        cdp.emit('Network.loadingFailed',
                 {'requestId': rid, 'errorText': error, 'canceled': canceled})
    elif 'pin' in step:
        pass  # applied by the test body after the step
    else:
        raise AssertionError('unknown step: %r' % (step,))


# --- Phase A pin (restored): deviation scoped to the verbatim directory ------

def test_guard_400_still_applies_outside_verbatim_dir(tmp_path, monkeypatch):
    """The deviation is scoped to the verbatim directory, not the repo."""
    module = _load_check_limits()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'PYTHON', tmp_path / 'python')
    _write_lines(tmp_path, 'python/other/regular.py', 456)
    violations = module.check_files()
    assert len(violations) == 1
    assert 'лимит 400' in violations[0]


# --- Verbatim byte-exactness pin (red on the stub, green after the copy) -----

def test_production_net_monitor_is_byte_exact_native():
    module_path = ROOT / 'python' / 'substrate' / 'llm' / 'browser' / 'net_monitor.py'
    data = module_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == NATIVE_NET_MONITOR_SHA


# --- Corpus battery (cases, not tests; frames are inert data) -----------------

@pytest.mark.parametrize('case_id', sorted(CASES))
def test_corpus_case(case_id):
    module = importlib.import_module('python.substrate.llm.browser.net_monitor')
    case = CASES[case_id]
    fixture_bytes = (CORPUS / case['fixture']).read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == case['sha256']
    cdp = FakeCDP()
    mon = make_monitor(module, cdp)
    for line in fixture_bytes.decode('utf-8').splitlines():
        if not line.strip():
            continue
        step = json.loads(line)
        apply_step(mon, cdp, step)
        if 'pin' in step:
            snap = snapshot(mon, cdp)
            for key, value in step['pin'].items():
                assert snap[key] == value, (case_id, 'pin', key, snap[key], value)
    snap = snapshot(mon, cdp)
    for key, value in case['expected'].items():
        assert snap[key] == value, (case_id, 'final', key, snap[key], value)




# --- Debt B-2 closed: independent one-shot case (same helpers, corpus scenario) ---


def test_pop_http_error_is_one_shot():
    module = importlib.import_module("python.substrate.llm.browser.net_monitor")
    cdp = FakeCDP()
    mon = make_monitor(module, cdp)
    apply_step(mon, cdp, {"post": ["r1", "https://chat.qwen.ai/api/v2/chat/completions", "POST"]})
    apply_step(mon, cdp, {"response": ["r1", "https://chat.qwen.ai/api/v2/chat/completions", 429, "text/html"]})
    apply_step(mon, cdp, {"wait_done": "r1"})
    assert snapshot(mon, cdp)["pop_http_error"] == 429
    assert snapshot(mon, cdp)["pop_http_error"] is None
