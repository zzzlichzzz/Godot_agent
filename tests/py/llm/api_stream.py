"""Recorded bytes through actual native SSE loops and owned reader threads."""
import base64
import json
from unittest.mock import patch


class Response:
    def __init__(self, raw, chunk, failure=None):
        self.raw, self.chunk, self.failure = raw, chunk, failure
        self.pos, self.closed = 0, False

    def read1(self, size):
        if self.pos >= len(self.raw):
            if self.failure:
                raise OSError(self.failure)
            return b''
        end = min(len(self.raw), self.pos + self.chunk, self.pos + size)
        out, self.pos = self.raw[self.pos:end], end
        return out

    def read(self, size=-1):
        if size >= 0:
            return self.read1(size)
        self.pos = len(self.raw)
        return self.raw

    def close(self):
        self.closed = True


def stream_observation(modules, case):
    oc = modules['openai_compat']
    transport = modules[case['module']]
    raw = base64.b64decode(case['wire_base64'], validate=True)
    response = Response(raw, case['chunk'], case.get('read_failure'))
    requests, deltas, readers = [], [], []
    original_spawn = oc._spawn_reader

    def open_response(url, key, headers, proxy, payload, accept, timeout, method='POST'):
        assert url.startswith('http://127.0.0.1:')
        recorded_headers = {name: '<redacted>' if name.lower() == 'authorization' else value
                            for name, value in oc._headers(key, headers, accept).items()}
        requests.append({'url': url, 'payload': payload, 'accept': accept,
                         'headers': recorded_headers})
        return response

    def spawn(resp, queue, stop):
        reader = original_spawn(resp, queue, stop)
        readers.append(reader)
        return reader

    result, error = None, None
    with patch.object(oc, '_open', open_response), patch.object(oc, '_spawn_reader', spawn):
        try:
            call = transport.stream_chat if case.get('stream', True) else transport.complete_chat
            options = {'on_delta': lambda text, thought: deltas.append([text, thought])} if case.get('stream', True) else {}
            if case.get('cancel'):
                options['cancel_cb'] = lambda: True
            result = call('http://127.0.0.1:1/v1', 'fixture-transport-key-0001', 'fixture-model',
                          [{'role': 'system', 'content': 'fixture rules'}, {'role': 'user', 'content': 'ёж Ω'}],
                          max_tokens=16, **options)
        except Exception as exc:
            error = {'error': type(exc).__name__, 'message': str(exc)}
        finally:
            for reader in readers:
                reader.join(timeout=2)
                assert not reader.is_alive(), 'owned API reader did not stop'
    return {'result': result, 'error': error, 'deltas': deltas, 'requests': requests,
            'closed': response.closed, 'readers_stopped': all(not t.is_alive() for t in readers)}
