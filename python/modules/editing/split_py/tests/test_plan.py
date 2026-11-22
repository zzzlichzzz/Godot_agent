"""Independent native projection and native error/warning order."""
import json

import pytest

from python.modules.editing.split_py.tests.plan_cases import SUCCESSES, prepared


@pytest.mark.parametrize('case', SUCCESSES, ids=lambda c:c['id'])
def test_full_native_prepared(case):
    result = prepared(case)
    expected = {k:v for k,v in case['reference_result'].items() if k not in ('schema','addon_dir')}
    if 'ordinary_reference_refs' in case:
        expected['refs'] = case['ordinary_reference_refs']
    assert result == expected


@pytest.mark.parametrize('case', SUCCESSES, ids=lambda c:c['id'])
def test_public_projection(case):
    from python.modules.editing.split_py.domain.core import assemble_plan
    result = prepared(case)
    before = json.dumps(result, sort_keys=True)
    assert assemble_plan(result) == case['expect']['result']
    assert json.dumps(result, sort_keys=True) == before


def test_original_hooked_native_refs_null_is_preserved():
    case = next(c for c in SUCCESSES if c['id']=='072-plan-refs-null')
    result = prepared(case,hook=True)
    assert result == {k:v for k,v in case['reference_result'].items() if k not in ('schema','addon_dir')}
    assert result['refs'] is None
