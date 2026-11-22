"""Synthetic-only storage, redaction, environment isolation and fail-closed IO."""
from pathlib import Path
import os
import socket
from unittest.mock import patch
import pytest
from tests.py.llm.api_cases import references, observe

KEY1 = 'fixture-alpha-key-000000000001'
KEY2 = 'fixture-beta-key-000000000002'


def test_environment_is_isolated_and_restored(tmp_path):
    with patch.dict(os.environ, {'OTHER_API_KEY': KEY2}):
        before = dict(os.environ)
        with references(tmp_path) as modules:
            assert 'OTHER_API_KEY' not in os.environ
            assert modules['api_keys']._secrets() == []
            assert Path(modules['api_keys'].config_dir()) == tmp_path / 'config'
        assert dict(os.environ) == before


@pytest.mark.parametrize('host', ['example.invalid', '8.8.8.8', '0.0.0.0', '127.0.0.1.evil.invalid'])
def test_external_dns_and_socket_fail_closed(tmp_path, host):
    with references(tmp_path):
        with pytest.raises(PermissionError):
            socket.getaddrinfo(host, 443)
        with socket.socket() as sock:
            with pytest.raises(PermissionError):
                sock.connect((host, 443))
            with pytest.raises(PermissionError):
                sock.connect_ex((host, 443))


def test_key_stdout_and_public_state_are_masked(tmp_path, capsys):
    with references(tmp_path) as modules:
        keys = modules['api_keys']
        assert keys.set_key('fixture', KEY1)
        assert keys.add_key('fixture', KEY2)
        keys.note_key_exhausted('fixture', 0, reason='synthetic quota')
        public = keys.keys_state('fixture')
        assert KEY1 not in str(public) and KEY2 not in str(public)
        assert keys.resolve_key('fixture') == KEY2
        assert KEY1 not in keys.redact(KEY1 + ' ' + KEY2)
        assert KEY2 not in keys.redact(KEY1 + ' ' + KEY2)
    stdout = capsys.readouterr().out
    assert KEY1 not in stdout and KEY2 not in stdout


def test_env_key_priority_has_no_disk_rotation(tmp_path):
    with references(tmp_path) as modules:
        keys = modules['api_keys']
        keys.set_key('fixture', KEY1)
        os.environ['GODOT_AGENT_FIXTURE_KEY'] = KEY2
        assert keys.usable_keys('fixture') == [(-1, KEY2)]
        assert keys.note_key_exhausted('fixture', -1) is False
        assert keys.key_count('fixture') == 1
        assert keys.key_source('fixture') == 'env'


def test_history_decorator_preserves_identity_and_nested_lock(tmp_path):
    with references(tmp_path) as modules:
        history = modules['api_history']
        original = history.append_exchange.__wrapped__
        assert history.append_exchange.__name__ == original.__name__
        assert history.append_exchange(str(tmp_path), 'fixture', 'hello', 'answer')
        assert len(history.load_messages(str(tmp_path), 'fixture')) == 2
        assert history._lock(str(tmp_path), 'fixture') is history._lock(str(tmp_path), 'fixture')


def test_corrupt_history_never_replaced_by_empty(tmp_path):
    with references(tmp_path) as modules:
        history = modules['api_history']
        target = Path(history.history_path(str(tmp_path), 'fixture'))
        target.parent.mkdir()
        target.write_bytes(b'{corrupt')
        before = target.read_bytes()
        with pytest.raises(history.ApiHistoryError):
            history.append_exchange(str(tmp_path), 'fixture', 'new', 'new')
        assert target.read_bytes() == before


def test_markdown_reference_bold_is_behavior_not_hash(tmp_path):
    with references(tmp_path) as modules:
        assert modules['md_to_bbcode'].to_bbcode('**ёж**') == '[b]ёж[/b]'


@pytest.mark.parametrize('module', ['openai_compat', 'anthropic_compat'])
def test_recorded_authorization_is_redacted_not_removed(tmp_path, module):
    import base64
    case = {'kind': 'stream', 'module': module, 'chunk': 7,
            'wire_base64': base64.b64encode(b'data: [DONE]\r\n\r\n').decode()}
    result = observe(case, tmp_path)
    assert len(result['requests']) == 1
    headers = result['requests'][0]['headers']
    authorization = [v for k, v in headers.items() if k.lower() == 'authorization']
    assert authorization == ['<redacted>']
    assert result['readers_stopped'] is True
