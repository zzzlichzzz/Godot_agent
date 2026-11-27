import copy
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.scene_model.node_reparent import tools

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in
         sorted((ROOT / 'fixtures/corpus/scene_model/node_reparent').glob('[0-9]*.json'))]


def test_generated_card_matches_toolspec_bytes():
    from tools.gen_contract import rendered
    path = 'node_reparent_preview.json'
    assert rendered()[path].encode('utf-8') == (ROOT / 'contract/capabilities' / path).read_bytes()


def test_strict_read_only_surface_and_defaults():
    spec = tools.TOOLS[0]
    assert (spec.name, spec.effects, spec.idempotent, spec.cost) == ('node_reparent_preview', 'read', True, 'cheap')
    assert spec.errors == ('invalid_input', 'not_found', 'denied') and not spec.requires_preview
    assert spec.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}
    assert spec.args['required'] == ['path', 'node', 'new_parent']
    assert set(spec.args['properties']) == {'path', 'node', 'new_parent', 'update_scripts'}
    assert spec.args['additionalProperties'] is False and spec.result['additionalProperties'] is False
    assert len(spec.result['required']) == 10 and 'base64' in spec.description.lower()
    assert 'defaults to true' in spec.description


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_actual_old_inputs_and_complete_results_fit_schema(record):
    spec = tools.TOOLS[0]
    assert validate(record['args'], spec.args) == []
    if record['expect']['ok']:
        assert validate(record['expect']['result'], spec.result) == []


@pytest.mark.parametrize('extra', [{'apply': True}, {'node': 1}, {'new_parent': None}, {'update_scripts': 'yes'}])
def test_invalid_arguments_and_write_flags_fail_closed(extra):
    assert validate({'path': 'res://main.tscn', 'node': 'Old', 'new_parent': 'New', **extra}, tools.TOOLS[0].args)


@pytest.mark.parametrize('field', ['absolute', 'scene_res', 'scripts_only', 'previous_name', 'text'])
def test_host_and_other_refactor_fields_are_not_in_result(field):
    result = copy.deepcopy(CASES[0]['expect']['result'])
    result[field] = 'forbidden'
    assert validate(result, tools.RESULT)


def test_structured_diff_is_not_unified_text_and_occurrences_nonnegative():
    result = copy.deepcopy(CASES[0]['expect']['result'])
    result['files'][0]['diff'] = 'unified text'
    assert validate(result, tools.RESULT)
    result = copy.deepcopy(CASES[0]['expect']['result'])
    result['files'][0]['occurrences'] = -1
    assert validate(result, tools.RESULT)
