"""Offline reference harness only; not an application/runtime import adapter."""
import base64
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / 'python/substrate/llm/browser'
ALLOWED = {'sites.py', 'live_input.py', 'net_monitor.py', 'ai_studio_net.py',
           'qwen_net.py', 'backends/browser_backend.py'}


def load(root, filename):
    assert filename in ALLOWED, 'source path is chosen by harness, not corpus data'
    path = root / filename
    assert path.is_file(), 'reference file not delivered: ' + filename
    spec = importlib.util.spec_from_file_location('b3_reference_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def references(root=TARGET):
    # Explicitly test-only legacy import dependency; reverted on every exit.
    base = load(root, 'net_monitor.py')
    server = ModuleType('server_state')
    server.wait_driver = lambda: 'inert-owned-driver'
    absent = {name: None for name in ['ai_parser', 'deepseek_parser', 'qwen_parser',
                                      'kimi_parser', 'arena_parser']}
    with patch.dict(sys.modules, {'net_monitor': base, 'server_state': server, **absent}):
        yield lambda filename: load(root, filename)


class CDP:
    """Memory-only registered callbacks; no sockets, Chrome, JS or key input."""
    def __init__(self, body=b'', buffered=b'', fallback=False):
        self.handlers, self.calls = {}, []
        self.body, self.buffered, self.fallback = body, buffered, fallback

    def on_event(self, name, handler):
        self.handlers[name] = handler

    def send_command(self, method, params=None):
        self.calls.append(method)
        if method == 'Network.streamResourceContent':
            if self.fallback:
                raise RuntimeError('inert stream unavailable')
            return {'bufferedData': base64.b64encode(self.buffered).decode('ascii')}
        if method == 'Network.getResponseBody':
            return {'body': base64.b64encode(self.body).decode('ascii'), 'base64Encoded': True}
        raise AssertionError('unexpected CDP primitive: ' + method)


def state(mon):
    return {'answer': mon.current_text(), 'thought': mon.thought_text(),
            'finished': mon.is_finished(), 'generating': mon.is_generating(),
            'assistant_count': mon.assistant_message_count(),
            'status': mon.message_status()}


def _monitor(module, kind, cdp):
    return (module.AiStudioChatMonitor if kind == 'ai' else module.QwenChatMonitor)(cdp)


def decode(case, importer):
    kind = case['monitor']
    module = importer('ai_studio_net.py' if kind == 'ai' else 'qwen_net.py')
    if case.get('codec_missing'):
        module._brotli = None
    mon = _monitor(module, kind, CDP())
    raw = base64.b64decode(case['body_b64'], validate=True)
    trace, buffer = [], b''
    step = case['step']
    for offset in range(0, len(raw), step):
        buffer += raw[offset:offset + step]
        events, used = mon._decode_frames_partial(buffer)
        assert 0 <= used <= len(buffer)
        buffer = buffer[used:]
        for event in events:
            mon._apply_event(event)
        if case.get('trace') and events:
            trace.append(state(mon))
    return {'state': state(mon), 'tail_b64': base64.b64encode(buffer).decode('ascii'),
            'trace': trace}


def wire(case, importer):
    kind = case['monitor']
    module = importer('ai_studio_net.py' if kind == 'ai' else 'qwen_net.py')
    raw = base64.b64decode(case['body_b64'], validate=True)
    cdp = CDP(body=raw, buffered=raw if case.get('buffered') else b'',
              fallback=case.get('fallback', False))
    mon = _monitor(module, kind, cdp)
    url = ('https://example.invalid/MakerSuiteService/GenerateContent' if kind == 'ai'
           else 'https://example.invalid/api/v2/chat/completions')
    mime = 'application/json+protobuf' if kind == 'ai' else 'text/event-stream'
    cdp.handlers['Network.requestWillBeSent']({'requestId': 'owned',
        'request': {'url': url, 'method': 'POST'}})
    cdp.handlers['Network.responseReceived']({'requestId': 'owned',
        'response': {'url': url, 'mimeType': mime, 'status': 200}})
    started = mon._stream_done['owned']
    assert started.wait(2), 'bounded inert stream setup'
    if not case.get('buffered') and not case.get('fallback'):
        for start in range(0, len(raw), case['step']):
            cdp.handlers['Network.dataReceived']({'requestId': 'owned',
                'data': base64.b64encode(raw[start:start + case['step']]).decode('ascii')})
    cdp.handlers['Network.loadingFinished']({'requestId': 'owned'})
    deadline = time.monotonic() + 2
    while mon.is_generating() and time.monotonic() < deadline:
        time.sleep(.001)
    assert not mon.is_generating(), 'bounded inert request completion'
    return {'state': state(mon), 'calls': cdp.calls,
            'request_count': mon.chat_request_count(), 'answer_count': mon.answer_request_count()}


def sites(case, importer):
    module = importer('sites.py')
    if case.get('kind') == 'sites-error':
        try:
            module.get_parser_module('unknown')
        except ModuleNotFoundError as error:
            return {'missing_parser': error.name}
        raise AssertionError('absent parser unexpectedly available')
    return {'flags': {site: module.needs_visibility_spoof(site_id=site)
                      for site in case['ids']},
            'detect': [module.detect_site(url) for url in case['urls']],
            'same': [module.same_site(left, right) for left, right in case['pairs']],
            'list': module.list_sites()}


def mirror(case, importer):
    module = importer('live_input.py')
    settings, calls = {}, []

    def get(name, value):
        if settings.get(name + '_error'):
            raise RuntimeError('inert ' + name)
        return value

    def apply(driver, text, prefer_url=None):
        calls.append({'driver': driver, 'text': text, 'prefer_url': prefer_url})
        if settings.get('apply_error'):
            raise RuntimeError('inert parser error')
        return settings.get('applied', True)

    parser = SimpleNamespace(mirror_input=apply)
    mon = module.LiveInputMirror(
        get_driver=lambda: get('driver', None if settings.get('no_driver') else 'owned'),
        get_parser=lambda: get('parser', None if settings.get('no_parser') else parser),
        busy_fn=lambda: get('busy', settings.get('busy', False)),
        prefer_url_fn=lambda: get('prefer', 'https://example.invalid/owned'))
    results = []
    for item in case['steps']:
        settings.clear()
        settings.update(item.get('settings', {}))
        results.append(mon.apply(seq=item.get('seq'), text=item.get('text')))
    return {'results': results, 'calls': calls}


def backend(case, importer):
    module = importer('backends/browser_backend.py')
    calls, result = [], {}

    def send(driver, prompt, **kwargs):
        calls.append({'driver': driver, 'prompt': prompt, **kwargs})
        return case.get('response')

    def pop():
        if case.get('pop_error'):
            raise RuntimeError('inert pop error')
        return 429

    parser = SimpleNamespace(__name__='inert_parser', send_message_and_get_response=send,
                             pop_rate_limit_network_status=pop)
    service = module.BrowserBackend(None if case.get('no_parser') else parser)
    try:
        result['send'] = service.send(case['prompt'], prefer_url='https://example.invalid/owned')
    except AttributeError:
        result['send_error'] = 'AttributeError'
    result.update(describe=service.describe(), calls=calls,
                  rate_limit=service.pop_rate_limit_status(), retry_after=service.pop_retry_after())
    return result


def pop(case, importer):
    module = importer('net_monitor.py')

    class Monitor(module.BaseNetMonitor):
        CHAT_URL_SUBSTR = '/api/v2/chat/completions'
        RESPONSE_MIME_SUBSTR = 'text/event-stream'
        def _reset_answer_state_locked(self):
            pass

    cdp, values = CDP(), []
    mon = Monitor(cdp)
    for item in case['steps']:
        if item == 'pop':
            values.append(mon.pop_http_error())
        else:
            cdp.handlers['Network.responseReceived']({'requestId': 'untracked',
                'response': {'url': item['url'], 'status': item['status'], 'mimeType': 'text/html'}})
    return {'values': values, 'cdp_calls': cdp.calls}


RUNNERS = {'decode': decode, 'wire': wire, 'sites': sites, 'sites-error': sites,
           'mirror': mirror, 'backend': backend, 'pop': pop}


def observe(case, root=TARGET):
    # A fixed trusted runner is selected; strings from fixtures never become code.
    with references(root) as importer:
        return RUNNERS[case['kind']](case, importer)
