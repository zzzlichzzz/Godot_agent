"""Native-observation contract for the offline routing reference slice."""
import hashlib
import json
import socket

import pytest

from tests.py.llm.routing_cases import (
    BACKEND_TARGET, ROUTING_CORPUS, ROOT, routing_observation, routing_references,
)

MANIFEST = json.loads((ROUTING_CORPUS / 'manifest.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('record', MANIFEST['cases'], ids=lambda r: r['id'])
def test_native_routing_observation(record, tmp_path):
    raw = (ROUTING_CORPUS / record['file']).read_bytes()
    assert len(raw) == record['bytes']
    assert hashlib.sha256(raw).hexdigest() == record['sha256']
    assert raw.count(b'\n') == record['LF']
    assert raw.count(b'\r\n') == record['CRLF']
    data = json.loads(raw)
    assert data['provenance']['source_sha256'] == MANIFEST['sources']['api_backend']['pin']['sha256']
    assert routing_observation(data['input'], tmp_path) == data['expect']


@pytest.mark.parametrize('name', MANIFEST['sources'])
def test_routing_source_bytes_and_mixed_eol(name):
    info = MANIFEST['sources'][name]
    raw = (ROOT / (info['target'].replace('.', '/') + '.py')).read_bytes()
    assert len(raw) == info['pin']['bytes']
    assert hashlib.sha256(raw).hexdigest() == info['pin']['sha256']
    assert raw.count(b'\n') == info['pin']['LF']
    assert raw.count(b'\r\n') == info['pin']['CRLF']


def observation(label, tmp_path):
    for record in MANIFEST['cases']:
        data = json.loads((ROUTING_CORPUS / record['file']).read_text(encoding='utf-8'))
        if data['input']['label'] == label:
            return routing_observation(data['input'], tmp_path)['result']
    raise AssertionError('unknown corpus label: ' + label)


def test_rotation_changes_key_not_chat_model(tmp_path):
    result = observation('key rotation boundary RateLimitError daily quota', tmp_path)
    assert [r['key_slot'] for r in result['requests']] == [0, 1]
    assert {r['payload']['model'] for r in result['requests']} == {'fixture/model'}
    assert result['usable_key_indices'] == [1]
    assert result['rate_status'] == [None, None]


def test_outage_does_not_exhaust_other_keys(tmp_path):
    result = observation('key rotation boundary ServerError down', tmp_path)
    assert len(result['requests']) == 1
    assert result['usable_key_indices'] == [0, 1]
    assert result['rate_status'] == [503, None]


def test_deterministic_timeout_no_history_or_fabricated_action(tmp_path):
    result = observation('deterministic silence timeout', tmp_path)
    assert result['rate_status'] == ['transport', None]
    assert result['reply']['action'] is None
    assert result['saved_messages'] == []


def test_continuation_commits_only_one_complete_exchange(tmp_path):
    result = observation('continuation inside JSON', tmp_path)
    assert len(result['requests']) == 2
    assert len(result['saved_messages']) == 2
    assert result['saved_messages'][1]['content'] == result['reply']['raw']
    assert result['reply']['action']['action'] == 'list_files'
    assert result['reply']['usage'] == {'prompt_tokens': 140, 'completion_tokens': 12}


def test_runtime_and_editor_are_ephemeral_for_history(tmp_path):
    result = observation('ephemeral editor/runtime not persisted', tmp_path)
    assert result['saved_messages'][0]['content'] == 'synthetic user request'
    assert '[Godot editor context' in result['requests'][0]['payload']['messages'][-1]['content']
    assert '[Godot runtime status' in result['requests'][0]['payload']['messages'][-1]['content']


def test_authorization_only_value_masking_preserves_headers(tmp_path):
    result = observation('key rotation boundary RateLimitError daily quota', tmp_path)
    for request in result['requests']:
        assert request['headers']['Authorization'] == '<redacted>'
        assert request['headers']['Accept'] == 'text/event-stream'
        assert request['headers']['Content-Type'] == 'application/json'
        assert request['headers']['User-Agent'] == 'GodotAgent/0.6'


def test_all_socket_and_dns_operations_denied(tmp_path):
    with routing_references(tmp_path):
        with pytest.raises(PermissionError, match='network denied'):
            socket.getaddrinfo('example.invalid', 443)
        with socket.socket() as sock:
            with pytest.raises(PermissionError, match='network denied'):
                sock.connect(('127.0.0.1', 1))


def test_repository_is_never_a_config_or_history_sandbox():
    with pytest.raises(ValueError, match='outside the repository'):
        routing_observation({'function': '_fmt_num', 'args': [1]}, ROOT)
