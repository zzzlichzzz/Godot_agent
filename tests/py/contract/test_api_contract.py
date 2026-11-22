"""C.11 schema boundaries; artifact drift belongs to gen_contract, not unit."""
import copy

import pytest

from python.kernel.schema import validate
from python.modules.engine_kb.class_api.tools import API, TOOLS


def sample():
    return {'class_name': 'C', 'found': False, 'cache_version': '', 'inherits': [],
            'methods': [], 'properties': [], 'signals': [], 'unavailable': []}


def test_descriptor_identity_and_read_effect():
    assert TOOLS == (API,) and API.name == 'api'
    assert API.effects == 'read' and API.idempotent is True
    assert API.errors == ('invalid_input',) and API.availability == '*'
    assert API.cost == 'cheap' and API.limits == {}


@pytest.mark.parametrize('args', [{}, {'class_name': ''}, {'class_name': 1},
                                  {'class_name': None}, {'class_name': 'x' * 121},
                                  {'class_name': 'C', 'path': 'res://x'}])
def test_invalid_schema_args(args):
    assert validate(args, API.args)


@pytest.mark.parametrize('name', ['C', 'x' * 120, ' λ '])
def test_valid_schema_args(name):
    assert validate({'class_name': name}, API.args) == []


@pytest.mark.parametrize('field,bad', [('found', 1), ('inherits', ['C', 1]),
                                     ('cache_version', None), ('properties', [1]),
                                     ('unavailable', [{'kind': '', 'reason': 'x'}])])
def test_result_rejects_wrong_types(field, bad):
    result = sample(); result[field] = bad
    assert validate(result, API.result)


def test_nested_arity_and_extra_fields():
    result = sample()
    result['methods'] = [{'name': 'foo', 'min_args': -1, 'max_args': -1, 'signature': ''}]
    assert validate(result, API.result) == []
    bad = copy.deepcopy(result); bad['methods'][0]['min_args'] = True
    assert validate(bad, API.result)
    bad = copy.deepcopy(result); bad['methods'][0]['extra'] = 1
    assert validate(bad, API.result)
    result['extra'] = 1
    assert validate(result, API.result)
