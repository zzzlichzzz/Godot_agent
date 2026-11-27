"""Recorded mock boundary around the actual compat SSE loops (no network)."""
import base64
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import queue
from types import SimpleNamespace
from unittest.mock import patch

from tests.py.llm.api_stream import Response


@contextmanager
def recorded_transport(modules, case, keys):
    oc = modules['openai_compat']
    ac = modules['anthropic_compat']
    scripts = case.get('responses', [])
    requests, deltas, responses, readers = [], [], [], []
    original_spawn = oc._spawn_reader

    def opening(url, key, headers, proxy, payload, accept, timeout, method='POST'):
        assert url.startswith('http://127.0.0.1:1/'), 'non-loopback mock request'
        slot = keys.index(key) if key in keys else -1
        observed = {name: '<redacted>' if name.lower() == 'authorization' else value
                    for name, value in oc._headers(key, headers, accept).items()}
        requests.append({'url': url, 'payload': deepcopy(payload), 'headers': observed,
                         'proxy': proxy, 'accept': accept, 'timeout': timeout,
                         'method': method, 'key_slot': slot})
        assert scripts, 'unplanned transport call'
        script = scripts[min(len(requests) - 1, len(scripts) - 1)]
        if 'error' in script:
            args = script['error']
            cls = getattr(oc, args['type'])
            kwargs = {k: v for k, v in args.items() if k not in {'type', 'message'}}
            raise cls(args.get('message', 'synthetic error'), **kwargs)
        response = Response(base64.b64decode(script.get('wire_base64', ''), validate=True),
                            script.get('chunk', 17), script.get('read_failure'))
        responses.append(response)
        return response

    def spawning(response, q, stop):
        reader = original_spawn(response, q, stop)
        readers.append(reader)
        return reader

    def wrapping(original, protocol):
        def stream(*args, **kwargs):
            callback = kwargs.get('on_delta')

            def delta(text, thought):
                deltas.append({'protocol': protocol, 'text': text, 'reasoning': thought})
                if callback:
                    callback(text, thought)

            kwargs['on_delta'] = delta
            return original(*args, **kwargs)
        return stream

    with ExitStack() as stack:
        stack.enter_context(patch.object(oc, '_open', opening))
        stack.enter_context(patch.object(oc, '_spawn_reader', spawning))
        for transport, name in ((oc, 'openai'), (ac, 'anthropic')):
            stack.enter_context(patch.object(transport, 'stream_chat', wrapping(transport.stream_chat, name)))
        if case.get('silence'):
            class EmptyQueue:
                def get(self, **kwargs):
                    raise queue.Empty()

            fake_queue = SimpleNamespace(Queue=EmptyQueue, Empty=queue.Empty)
            for transport in (oc, ac):
                ticks = iter([1000.0, 1000.0, 1003.0])
                clock = SimpleNamespace(time=lambda values=ticks: next(values, 1003.0))
                stack.enter_context(patch.object(transport, 'queue', fake_queue))
                stack.enter_context(patch.object(transport, 'time', clock))
            stack.enter_context(patch.object(oc, '_spawn_reader', lambda *args: None))
        try:
            yield {'requests': requests, 'deltas': deltas}
        finally:
            for reader in readers:
                reader.join(timeout=2)
                assert not reader.is_alive(), 'owned routing reader did not stop'
            # _open errors legitimately create no response; silence has no reader.
            for response in responses:
                assert response.closed, 'compat did not close its response'
