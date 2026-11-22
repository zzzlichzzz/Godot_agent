"""C.9 schema, metadata and error envelope through the real dispatcher."""
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]


def test_descriptor_and_generated_card():
    from python.modules.verification.check.tools import VERIFY
    from python.modules.verification.check.module import MODULE
    assert MODULE.provides_tools == ('verify',) and MODULE.requires_ports == ('fs',)
    assert MODULE.requires == ()
    assert VERIFY.name == 'verify' and VERIFY.effects == 'read' and VERIFY.idempotent
    assert VERIFY.errors == ('invalid_input', 'not_found', 'denied')
    assert VERIFY.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}
    assert (ROOT / 'contract/capabilities/verify.json').is_file()


@pytest.mark.parametrize('args', [None, {}, {'path': ''}, {'path': 2}, {'path': 'res://x', 'kinds': []},
    {'path': 'res://x', 'kinds': 'gd'}, {'path': 'res://x', 'kinds': [4]},
    {'path': 'res://x', 'kinds': ['bogus']}, {'path': 'res://x', 'extra': True}])
def test_bad_arguments_fail_in_dispatch(args, tmp_path):
    agent = build_agent(project_root=tmp_path, state_dir=tmp_path / 'state')
    result = agent.call('verify', args)
    assert result['ok'] is False and result['kind'] == 'invalid_input'
    assert str(tmp_path) not in json.dumps(result)


def test_actual_result_conforms_to_schema(tmp_path):
    from python.modules.verification.check.tools import VERIFY
    project = ROOT / 'fixtures/corpus/verification/check/project/common'
    agent = build_agent(project_root=project, state_dir=tmp_path)
    for name in ('clean.gd', 'duplicate.json', 'steps.tscn', 'notes.md', 'resource.tres'):
        result = agent.call('verify', {'path': 'res://' + name})
        assert result['ok'] is True
        assert validate(result['result'], VERIFY.result) == []
