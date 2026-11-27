"""A reference parity; native code is never imported by this test suite."""
import hashlib
import json
from pathlib import Path

import pytest

from tests.py.llm.routing_context_cases import (
    CONTEXT_CORPUS, CONTEXT_SOURCES, ROOT, context_observation, context_references,
)

MANIFEST = json.loads((CONTEXT_CORPUS / 'manifest.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('record', MANIFEST['cases'], ids=lambda r: r['id'])
def test_native_context_observation(record, tmp_path):
    raw = (CONTEXT_CORPUS / record['file']).read_bytes()
    assert len(raw) == record['bytes']
    assert hashlib.sha256(raw).hexdigest() == record['sha256']
    data = json.loads(raw)
    assert data['provenance']['source_sha256'] == MANIFEST['sources'][data['input']['module']]['sha256']
    assert context_observation(data['input'], tmp_path) == data['expect']


@pytest.mark.parametrize('name', CONTEXT_SOURCES)
def test_context_source_bytes_eol(name):
    info = MANIFEST['sources'][name]
    raw = (ROOT / (info['target'].replace('.', '/') + '.py')).read_bytes()
    assert len(raw) == info['bytes']
    assert hashlib.sha256(raw).hexdigest() == info['sha256']
    assert raw.count(b'\n') == info['LF']
    assert raw.count(b'\r\n') == info['CRLF']


def test_one_turn_context_removed_not_saved():
    with context_references() as modules:
        editor = modules['editor_context']
        runtime = modules['runtime_debug']
        status = {'sessions': [{'session_id': 3, 'active': True, 'bridge_ready': True}]}
        snapshot = {'schema_version': 1, 'script': {'path': 'res://player.gd',
                    'selection': {'text': 'func jump():\n    pass'}}}
        prompt, _ = editor.attach_to_prompt('this code', snapshot)
        decorated = runtime.attach_status(prompt, status)
        assert editor.user_prompt_without_context(runtime.strip_status(decorated)) == 'this code'


def test_runtime_token_never_sent_to_game():
    with context_references() as modules:
        runtime = modules['runtime_debug']
        request = runtime.create_request({'action': 'inspect_runtime', 'sections': ['tree']},
                  {'sessions': [{'session_id': 3, 'active': True, 'bridge_ready': True}]}, 'chat', 7)
        assert 'result_token' in runtime.public_request(request)
        assert 'result_token' not in runtime.runtime_request(request)
        assert 'deadline' not in runtime.public_request(request)


def test_context_reference_has_no_io_imports():
    import ast
    for name, (_, target) in CONTEXT_SOURCES.items():
        tree = ast.parse((ROOT / (target.replace('.', '/') + '.py')).read_text(encoding='utf-8'))
        imports = {n.module if isinstance(n, ast.ImportFrom) else alias.name
                   for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                   for alias in (n.names if isinstance(n, ast.Import) else [None])}
        assert imports == ({'json', 'secrets', 'time'} if name == 'runtime_debug' else set())
