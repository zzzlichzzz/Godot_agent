import copy
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.editing.split_gd.tools import PLAN, SCAN, TOOLS

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(p.read_bytes()) for p in sorted((ROOT / 'fixtures/corpus/editing/split_gd').glob('1[0-9][0-9]-*.json'))]
SUCCESS = [case for case in CASES if case['expect']['ok']]


def test_descriptor_and_additive_ownership():
    assert TOOLS == (SCAN, PLAN) and PLAN.name == 'split_gd_plan'
    assert PLAN.effects == 'read' and PLAN.idempotent is True
    assert PLAN.errors == ('invalid_input', 'not_found', 'denied')
    assert PLAN.availability == '*' and PLAN.cost == 'cheap'
    assert PLAN.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}


@pytest.mark.parametrize('case', SUCCESS, ids=lambda c: c['id'])
def test_native_payload_matches_schema(case):
    assert validate(case['args'], PLAN.args) == []
    assert validate(case['expect']['result'], PLAN.result) == []


@pytest.mark.parametrize('args', [{}, {'path': ''}, {'path': None}, {'path': 'res://x.gd', 'extra': 1},
    {'path': 'res://x.gd', 'groups': {}}, {'path': 'res://x.gd', 'groups': [None]},
    {'path': 'res://x.gd', 'groups': [{'module': '', 'funcs': ['x']}]},
    {'path': 'res://x.gd', 'groups': [{'module': 'part', 'funcs': 'alpha'}]},
    {'path': 'res://x.gd', 'target_lines': True}, {'path': 'res://x.gd', 'target_lines': '100'},
    {'path': 'res://x.gd', 'target_lines': None}])
def test_input_schema_refusals(args):
    assert validate(args, PLAN.args)


@pytest.mark.parametrize('args', [{'path': 'res://x.gd', 'target_lines': 99},
    {'path': 'res://x.gd', 'target_lines': 5001}, {'path': 'res://x.gd', 'target_lines': -1},
    {'path': 'res://x.gd', 'groups': [{'module': 'part', 'funcs': []}]}])
def test_domain_refusals_are_not_hidden_by_schema(args):
    assert validate(args, PLAN.args) == []


def test_factual_newline_enum():
    assert PLAN.result['properties']['newline']['enum'] == ['\n', '\r\n', '\r']


@pytest.mark.parametrize('field,bad', [('wrappers', 1), ('stats', {'moved': '2'}),
    ('modules', [{'path': 'part.gd', 'lines': 1, 'funcs': []}]), ('groups', {}),
    ('warnings', [1]), ('donor_sha256', 'short'), ('target_lines', True)])
def test_native_metadata_types_not_invented_aliases(field, bad):
    payload = copy.deepcopy(SUCCESS[0]['expect']['result'])
    payload[field] = bad
    assert validate(payload, PLAN.result)


@pytest.mark.parametrize('field', ['addon_dir', 'project_root', 'donor_abs', 'donor_content', 'lines_after'])
def test_private_fields_and_aliases_rejected(field):
    payload = copy.deepcopy(SUCCESS[0]['expect']['result'])
    payload[field] = 'private'
    assert validate(payload, PLAN.result)
