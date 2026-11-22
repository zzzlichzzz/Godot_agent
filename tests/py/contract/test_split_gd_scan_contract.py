"""ToolSpec behavior; generated-card drift belongs exclusively to gen_contract."""
import copy
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.editing.split_gd.tools import SCAN, TOOLS

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((ROOT / 'fixtures/corpus/editing/split_gd/002-mixed.json').read_bytes())['expect']['result']


def test_descriptor():
    assert tuple(t.name for t in TOOLS) == ('split_gd_scan', 'split_gd_plan') and SCAN.name == 'split_gd_scan'
    assert SCAN.effects == 'read' and SCAN.idempotent is True
    assert SCAN.errors == ('invalid_input', 'not_found', 'denied')
    assert SCAN.availability == '*' and SCAN.cost == 'cheap'
    assert SCAN.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}


@pytest.mark.parametrize('args', [{}, {'path': ''}, {'path': 1}, {'path': 'res://x.gd', 'x': 1}])
def test_args_rejected(args):
    assert validate(args, SCAN.args)


def test_valid_payload_schema():
    assert validate({'path': 'res://donor.gd'}, SCAN.args) == []
    assert validate(SAMPLE, SCAN.result) == []


@pytest.mark.parametrize('field,bad', [('lines', True), ('donor', ''), ('funcs', '1'),
    ('public_methods', [1]), ('truncated', 0), ('hard_files', [None]),
    ('soft_files', 'a.txt'), ('counts', {'mention': '0'}),
    ('occurrences', [{'file': '', 'line': '1', 'kind': 'other', 'text': 1}])])
def test_wrong_types(field, bad):
    result = copy.deepcopy(SAMPLE); result[field] = bad
    assert validate(result, SCAN.result)


def test_no_internal_schema_or_extra_fields():
    result = copy.deepcopy(SAMPLE); result['schema'] = 1
    assert validate(result, SCAN.result)
    result = copy.deepcopy(SAMPLE); result['counts']['extra'] = 0
    assert validate(result, SCAN.result)
    result = copy.deepcopy(SAMPLE); result['occurrences'][0]['extra'] = 1
    assert validate(result, SCAN.result)
