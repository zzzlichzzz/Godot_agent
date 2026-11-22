"""C.12 schema behavior; required/card drift is independently gen_contract's gate."""
import copy

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.verification.api_check.tools import API_CHECK, TOOLS


def sample():
    return {'path': 'res://missing.gd', 'problems': [], 'checked': False,
            'base_class': '', 'unavailable': [{'kind': 'source', 'reason': 'no_extends'}]}


def test_descriptor_identity():
    assert TOOLS == (API_CHECK,) and API_CHECK.name == 'api_check'
    assert API_CHECK.effects == 'read' and API_CHECK.idempotent is True
    assert API_CHECK.errors == ('invalid_input', 'denied') and API_CHECK.availability == '*'
    assert API_CHECK.cost == 'cheap' and API_CHECK.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}


@pytest.mark.parametrize('args', [{}, {'path': '', 'content': ''}, {'path': 1, 'content': ''},
                                   {'path': 'res://x.gd', 'content': False},
                                   {'path': 'res://x.gd', 'content': '', 'extra': 1}])
def test_invalid_args_schema(args):
    assert validate(args, API_CHECK.args)


def test_valid_args_schema():
    assert validate({'path': 'res://missing.gd', 'content': ''}, API_CHECK.args) == []


@pytest.mark.parametrize('field,bad', [('path', ''), ('problems', [1]), ('checked', 1),
                                      ('base_class', None), ('unavailable', [{'kind': '', 'reason': 'x'}])])
def test_result_wrong_types(field, bad):
    result = sample(); result[field] = bad
    assert validate(result, API_CHECK.result)


def test_nested_extra_fields_rejected():
    result = sample()
    assert validate(result, API_CHECK.result) == []
    bad = copy.deepcopy(result); bad['unavailable'][0]['extra'] = 1
    assert validate(bad, API_CHECK.result)
    result['extra'] = 1
    assert validate(result, API_CHECK.result)
