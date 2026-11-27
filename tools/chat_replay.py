"""Run the frozen K1 corpus against the real dispatcher with synthetic SSE."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.corpus_replay import records


def _offline_open(oc, frames, tokens, attempts):
    def open_response(url, key, _headers, _proxy, _payload, accept, _timeout):
        assert url == 'https://example.invalid/v1/chat/completions'
        assert accept == 'text/event-stream' and key in tokens
        assert len(attempts) < len(frames), 'replay exhausted its frozen frames'
        frame = frames[len(attempts)]
        attempts.append(key)
        if frame.get('error') == 'rate_limit':
            raise oc.RateLimitError('synthetic daily quota', status=429, daily=True)
        if frame.get('error') == 'service_unavailable':
            raise oc.ServerError('synthetic service failure', status=503)
        return BytesIO(frame['sse'].encode('utf-8'))
    return open_response


def _config(state, tokens):
    directory = state / 'api_config'
    directory.mkdir(parents=True)
    (directory / 'api_keys.json').write_text(json.dumps({'version': 2, 'providers': {
        'custom': {'keys': [{'key': key, 'cooldown_until': 0, 'cooldown_reason': ''}
                            for key in tokens],
                   'base_url': 'https://example.invalid/v1', 'model': 'synthetic-offline'}},
        'defaults': {'provider': 'custom', 'model': 'synthetic-offline'}}), encoding='utf-8')


def replay(folder, compare):
    from python.runtime.bootstrap import build_agent
    from python.runtime.config import state_root
    from python.substrate.llm import runtime_bindings

    runtime_bindings.register()
    from python.substrate.llm.api import openai_compat as oc

    folder = Path(folder)
    script = json.loads((folder / 'sse' / 'wire.json').read_text(encoding='utf-8'))
    catalog = [record for _, record in records([folder / 'catalog.json'])]
    assert sorted(record['id'] for record in catalog) == sorted(script)
    tokens = ('synthetic-offline-key-1', 'synthetic-offline-key-2')
    failures = []

    def forbid(*_args, **_kwargs):
        raise AssertionError('real network is disabled for chat replay')

    with (TemporaryDirectory(prefix='godot-chat-replay-') as work,
          patch.dict(os.environ), patch.object(socket, 'getaddrinfo', forbid),
          patch.object(socket.socket, 'connect', forbid), patch.object(socket.socket, 'connect_ex', forbid)):
        os.environ.pop('GODOT_AGENT_CONFIG_DIR', None)
        os.environ.pop('GODOT_AGENT_CUSTOM_KEY', None)
        project = Path(work) / 'project'
        shutil.copytree(folder / 'project', project)
        for index, record in enumerate(catalog):
            name = record['id']
            attempts = []
            state = Path(work) / str(index)
            _config(Path(state_root('headless', state)), tokens)
            agent = build_agent(project, profile='headless', state_dir=state)
            with patch.object(oc, '_open', _offline_open(oc, script[name], tokens, attempts)):
                answer = agent.call(record['tool'], record['args'])
            problem = compare(answer, record['expect'], '')
            if not problem and len(attempts) != len(script[name]):
                problem = 'did not consume every frozen frame'
            if not problem and name == 'key_rotation' and len(set(attempts)) != 2:
                problem = 'candidate key did not rotate'
            if problem:
                failures.append(name + ': ' + problem)
    return len(catalog), len(catalog) - len(failures), failures
