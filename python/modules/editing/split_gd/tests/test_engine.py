import pytest

from ..domain.engine import api
from .plan_corpus import NATIVE, classes


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_native_methods_properties_and_fallback(case):
    methods, properties = api(classes(case), case['reference_inventory']['extends'] or 'Control')
    assert sorted(methods) == case['reference_engine']['methods']
    assert sorted(properties) == case['reference_engine']['properties']


def test_inheritance_depth_guard_is_thirty():
    cache = {'C%d' % i: {'methods': {'m%d' % i: {}}, 'inherits': 'C%d' % (i + 1)} for i in range(40)}
    assert api(cache, 'C0') == ({'m%d' % i for i in range(30)}, set())
