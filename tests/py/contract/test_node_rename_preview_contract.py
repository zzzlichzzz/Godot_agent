import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.scene_model.node_rename import tools

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'fixtures/corpus/scene_model/node_rename').glob('[0-9]*.json'))]


def test_generated_card_equals_toolspec():
    from tools.gen_contract import rendered
    assert rendered()['node_rename_preview.json'].encode('utf-8') == (ROOT / 'contract/capabilities/node_rename_preview.json').read_bytes()


def test_strict_read_only_declaration_and_defaults():
    spec = tools.TOOLS[0]
    assert (spec.name, spec.effects, spec.idempotent, spec.cost) == ('node_rename_preview', 'read', True, 'cheap')
    assert not spec.requires_preview
    assert set(spec.errors) == {'invalid_input', 'not_found', 'denied'}
    assert spec.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}
    assert spec.args['required'] == ['path', 'node', 'new_name']
    assert spec.args['additionalProperties'] is False
    assert spec.result['additionalProperties'] is False and len(spec.result['required']) == 12
    assert 'base64' in spec.description.lower()


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_captured_inputs_and_results_fit_schema(record):
    spec = tools.TOOLS[0]
    assert validate(record['args'], spec.args) == []
    if record['expect']['ok']:
        assert validate(record['expect']['result'], spec.result) == []


@pytest.mark.parametrize('extra', [{'apply': True}, {'node': 12}, {'new_name': None}, {'update_scripts': 'yes'}])
def test_schema_refuses_unrequested_write_and_malformed_arguments(extra):
    assert validate({'path': 'res://main.tscn', 'node': '.', 'new_name': 'New', **extra}, tools.TOOLS[0].args)
