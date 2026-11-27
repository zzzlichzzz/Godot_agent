"""Pinned API observations; isolated aliases/environment, never native test code."""
from contextlib import contextmanager, ExitStack, redirect_stdout
from importlib import import_module, util
import base64
import io
import json
import os
from pathlib import Path
import random
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/llm/api'
SOURCES = (
    ('api_keys', 'api/api_keys.py', 'api_keys'),
    ('openai_compat', 'api/openai_compat.py', 'openai_compat'),
    ('providers', 'api/providers.py', 'providers'),
    ('model_cache', 'api/model_cache.py', 'model_cache'),
    ('catalog', 'api/catalog.py', 'providers_catalog'),
    ('anthropic_compat', 'api/anthropic_compat.py', 'anthropic_compat'),
    ('agent_prompts', 'server/agent_prompts.py', 'agent_prompts'),
    ('rate_limit', 'server/rate_limit.py', 'rate_limit'),
    ('md_to_bbcode', 'server/md_to_bbcode.py', 'md_to_bbcode'),
    ('chat_store', 'server/chat_store.py', 'chat_store'),
    ('api_history', 'server/api_history.py', 'api_history'),
)


def normalize(value, sandbox):
    if isinstance(value, bytes):
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, BaseException):
        out = {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
        for name in ('status', 'retry_after', 'daily'):
            if hasattr(value, name):
                out[name] = getattr(value, name)
        return out
    if isinstance(value, str):
        return value.replace(str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>')
    if isinstance(value, dict):
        return {str(k): normalize(v, sandbox) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(item, sandbox) for item in value]
    return value


@contextmanager
def references(sandbox, native=None):
    """No user environment or external DNS/socket target can reach a reference."""
    sandbox = Path(sandbox).resolve()
    if ROOT == sandbox or ROOT in sandbox.parents:
        raise ValueError('API sandbox must be outside the repository')
    sandbox.mkdir(parents=True, exist_ok=True)
    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def permitted(host):
        return host in ('127.0.0.1', 'localhost', '::1')

    def resolve(host, *args, **kwargs):
        if not permitted(host):
            raise PermissionError('external DNS denied by API test guard')
        return original_resolve(host, *args, **kwargs)

    def connect(sock, address):
        if not isinstance(address, tuple) or not permitted(address[0]):
            raise PermissionError('external socket denied by API test guard')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if not isinstance(address, tuple) or not permitted(address[0]):
            raise PermissionError('external socket denied by API test guard')
        return original_connect_ex(sock, address)

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {'GODOT_AGENT_CONFIG_DIR': str(sandbox / 'config')}, clear=True))
        stack.enter_context(patch.dict(sys.modules))
        stack.enter_context(patch.object(socket, 'getaddrinfo', resolve))
        stack.enter_context(patch.object(socket.socket, 'connect', connect))
        stack.enter_context(patch.object(socket.socket, 'connect_ex', connect_ex))
        for name, _, target in SOURCES:
            sys.modules.pop(name, None)
            sys.modules.pop('python.substrate.llm.api.' + target, None)
        sys.modules.pop('python.substrate.llm.runtime_bindings', None)
        if native is not None:
            for name, source, _ in SOURCES:
                spec = util.spec_from_file_location(name, Path(native) / source)
                module = util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        else:
            import_module('python.substrate.llm.runtime_bindings').register()
        yield {name: sys.modules[name] for name, _, _ in SOURCES}


def observe(case, sandbox, native=None):
    from tests.py.llm.api_state import state_observation
    from tests.py.llm.api_stream import stream_observation
    sandbox = Path(sandbox)
    transcript = io.StringIO()
    with references(sandbox, native) as modules, redirect_stdout(transcript):
        clock = [float(case.get('now', 1000.0))]
        for module in modules.values():
            if hasattr(module, 'time'):
                module.time = SimpleNamespace(time=lambda: clock[0])
        modules['rate_limit'].random = random.Random(case.get('seed', 77))
        modules['chat_store'].uuid = SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='0123456789abcdef0123456789abcdef'))
        try:
            kind = case['kind']
            if kind == 'call':
                module = modules[case['module']]
                args = list(case.get('args', []))
                if case.get('bytes_argument'):
                    assert case['module'] == 'openai_compat' and case['function'] == 'split_sse_lines'
                    args[0] = base64.b64decode(args[0]['base64'], validate=True)
                result = getattr(module, case['function'])(*args, **case.get('kwargs', {}))
            elif kind == 'stream':
                result = stream_observation(modules, case)
            elif kind == 'state':
                result = state_observation(modules, case, sandbox, clock)
            elif kind == 'prompts':
                m = modules['agent_prompts']
                result = {name: getattr(m, name) for name in ('API_HISTORY_BUDGET', 'API_MAX_TOKENS', 'API_CONTEXT_WINDOW', 'PROMPT_HASH')}
            else:
                raise ValueError('unknown pinned API runner')
        except Exception as error:
            result = error
    return normalize(result, sandbox)
