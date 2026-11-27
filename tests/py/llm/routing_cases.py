"""Routing observer: real reference dependencies, synthetic external storage."""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
from importlib import import_module, util
import io
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace
from unittest.mock import patch

from tests.py.llm.api_cases import ROOT, normalize, references
from tests.py.llm.routing_context_cases import context_references
from tests.py.llm.routing_transport import recorded_transport

ROUTING_CORPUS = ROOT / 'fixtures/corpus/llm/routing'
BACKEND_TARGET = 'python.substrate.llm.backends.api_backend'
SYNTHETIC_KEYS = ['fixture-routing-key-0001', 'fixture-routing-key-0002']


@contextmanager
def routing_references(sandbox, native=None):
    with patch.dict(sys.modules):
        sys.modules.pop(BACKEND_TARGET, None)
        sys.modules.pop('api_backend', None)
        with references(sandbox / 'binding'):
            sys.modules.pop(BACKEND_TARGET, None)
            sys.modules.pop('api_backend', None)
            with _routing_modules(sandbox, native) as modules:
                yield modules


@contextmanager
def _routing_modules(sandbox, native):
    # The sealed byte-exact parser dependency is bound explicitly, never old-host bootstrap.
    with references(sandbox / 'runtime', native) as modules, context_references(native) as contexts:
            with ExitStack() as stack:
                stack.enter_context(patch.dict(sys.modules, contexts))
                if native is None:
                    module = import_module(BACKEND_TARGET)
                else:
                    spec = util.spec_from_file_location('capture_api_backend', Path(native) / 'backends/api_backend.py')
                    module = util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                modules.update(contexts, api_backend=module)
                for value in modules.values():
                    if hasattr(value, 'time'):
                        stack.enter_context(patch.object(value, 'time', SimpleNamespace(time=lambda: 1000.0)))
                stack.enter_context(patch.object(modules['rate_limit'], 'random', random.Random(77)))
                stack.enter_context(patch.object(modules['chat_store'], 'uuid',
                    SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='0123456789abcdef' * 2))))
                stack.enter_context(patch.object(module, '_budget_notes', {}))
                stack.enter_context(patch.object(module, '_LAST_RATE_LIMIT', {'status': None, 'retry_after': None}))
                yield modules


def pure_observation(modules, case):
    ab, oc = modules['api_backend'], modules['openai_compat']
    kind = case.get('kind', 'call')
    if kind == 'error':
        info = case['error']
        kwargs = {k:v for k,v in info.items() if k not in {'type', 'message'}}
        error = getattr(oc, info['type'])(info.get('message', 'synthetic error'), **kwargs)
        if case.get('proxy'):
            modules['api_keys'].set_proxy(enabled=True, host='127.0.0.1', port=8080)
        return {'description': ab.describe_api_error(error, 'fixture-provider', 'fixture-model'),
                'rotate': ab.should_rotate_key(error)}
    if kind == 'budgets':
        def info(*args):
            if case.get('catalog_error'):
                raise ValueError('synthetic catalog failure')
            return case.get('catalog')
        with patch.object(modules['catalog'], 'model_info', info):
            return ab.budgets_for('custom', 'fixture-model', case.get('max_tokens'), case.get('budget_tokens', 16000))
    if kind == 'schedule':
        rate = modules['rate_limit']
        return [rate.sleep_seconds(n, case.get('retry_after'), kind=case['rate_kind']) for n in case['attempts']]
    if kind == 'rate_state':
        ab._note_rate_limit(case['status'], case.get('retry_after'))
        return [ab.pop_rate_limit_status(), ab.pop_rate_limit_status(), ab.pop_retry_after(), ab.pop_retry_after()]
    return getattr(ab, case['function'])(*deepcopy(case.get('args', [])), **deepcopy(case.get('kwargs', {})))


def send_observation(modules, case, sandbox):
    ab, keys, history = modules['api_backend'], modules['api_keys'], modules['api_history']
    record = dict(id='fixturechat0001', kind='api', provider='custom', model='fixture/model')
    record.update(case.get('record', {}))
    pid = record['provider']
    base = sandbox / 'history'
    base.mkdir()
    if not case.get('missing_url'):
        keys.set_base_url(pid, 'http://127.0.0.1:1/v1')
    if case.get('keys'):
        keys.set_key(pid, SYNTHETIC_KEYS[0])
        for key in SYNTHETIC_KEYS[1:case['keys']]:
            keys.add_key(pid, key)
    if case.get('spent'):
        for index, key in keys.usable_keys(pid):
            keys.note_key_exhausted(pid, index, reason='synthetic spent', retry_after=120)
    if case.get('proxy'):
        keys.set_proxy(enabled=True, host='127.0.0.1', port=8080)
    keys.set_model(pid, 'not-the-chat-model')
    for pair in case.get('history', []):
        history.append_exchange(str(base), record['id'], pair[0], pair[1])
    prompt = case.get('prompt', 'synthetic user request')
    if case.get('context'):
        prompt = modules['editor_context'].attach_to_prompt(prompt, case['context'])[0]
        prompt = modules['runtime_debug'].attach_status(prompt, {'sessions': [
            {'session_id': 3, 'active': True, 'bridge_ready': True}]})
    messages_built, progress, build = [], [], history.build_request_messages
    cancelled = [0]

    def build_messages(*args, **kwargs):
        messages = build(*args, **kwargs)
        messages_built.append({'budget': kwargs['budget_tokens'], 'messages': deepcopy(messages)})
        return messages

    def system():
        if case.get('system_error'):
            raise ValueError('synthetic system failure')
        return case.get('system', 'synthetic system instructions')

    def cancel():
        cancelled[0] += 1
        return bool(case.get('cancel_after') is not None and cancelled[0] > case['cancel_after'])

    backend = ab.ApiBackend(record, str(base), system_text_provider=system,
        max_tokens=case.get('max_tokens', 1000), temperature=case.get('temperature', 0.25),
        budget_tokens=case.get('budget_tokens', 16000), silence_timeout=case.get('silence_timeout', 2))
    with ExitStack() as stack:
        stack.enter_context(patch.object(history, 'build_request_messages', build_messages))
        if 'catalog' in case:
            stack.enter_context(patch.object(modules['catalog'], 'model_info', return_value=case['catalog']))
        if case.get('anthropic'):
            # Only the provider registry boundary is mocked; both SSE compat modules are real.
            stack.enter_context(patch.object(modules['providers'], 'transport_for', return_value='anthropic'))
        if case.get('history_error'):
            def broken(*args, **kwargs):
                raise history.ApiHistoryError('synthetic history refusal')
            stack.enter_context(patch.object(history, 'build_request_messages', broken))
        if case.get('save_failure'):
            stack.enter_context(patch.object(history, 'append_exchange', return_value=False))
        if case.get('stats_failure'):
            stack.enter_context(patch.object(history, 'stats', side_effect=history.ApiHistoryError('synthetic stats refusal')))
        with recorded_transport(modules, case, SYNTHETIC_KEYS) as trace:
            try:
                result = backend.send(prompt, progress_cb=lambda info: progress.append(deepcopy(info)),
                                      cancel_cb=cancel, prefer_url='unused-browser-url')
            except Exception as error:
                result = error
    messages = history.load_messages(str(base), record['id'])
    files = {}
    for path in sorted(sandbox.rglob('*.json')):
        files[path.relative_to(sandbox).as_posix()] = json.loads(path.read_text(encoding='utf-8'))
    return {'reply': result, **trace, 'progress': progress, 'messages_built': messages_built,
            'saved_messages': messages, 'files': files,
            'rate_status': [backend.pop_rate_limit_status(), backend.pop_rate_limit_status()],
            'retry_after': [backend.pop_retry_after(), backend.pop_retry_after()],
            'usable_key_indices': [index for index, key in keys.usable_keys(pid)],
            'description': backend.describe()}


def routing_observation(case, sandbox, native=None):
    sandbox = Path(sandbox)
    before, stdout = deepcopy(case), io.StringIO()
    with redirect_stdout(stdout), routing_references(sandbox, native) as modules:
        try:
            value = (send_observation(modules, case, sandbox) if case.get('kind') == 'send'
                     else pure_observation(modules, case))
        except Exception as error:
            value = error
    assert case == before, 'routing observer changed its synthetic input'
    return normalize({'result': value, 'stdout': stdout.getvalue()}, sandbox)
