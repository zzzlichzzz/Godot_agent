import pytest

from ..domain.collect import ENGINE_VIRTUALS, collect_locals
from ..domain.tokens import tokenize
from .plan_corpus import NATIVE, source


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_frozen_native_locals_including_lambda_params(case):
    lines = source(case).split('\n')
    for func in case['reference_inventory']['funcs']:
        body = '\n'.join(lines[func['body_start'] - 1:func['end']])
        assert sorted(collect_locals(tokenize(body))) == case['reference_locals'][func['name']]


def test_locals_are_native_superset_not_scope_analysis():
    body = 'var state = 1\nconst LIMIT = 2\nfor x in values:\n\tpass\nvar f = func named(panel: int, other = 2): return panel\n'
    assert collect_locals(tokenize(body)) == {'state', 'LIMIT', 'x', 'f', 'named', 'panel', 'other'}
    assert '_ready' in ENGINE_VIRTUALS and '_process' in ENGINE_VIRTUALS
