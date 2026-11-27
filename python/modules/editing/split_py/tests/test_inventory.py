"""Native inventory summary, source segments, decorators and mutable state."""
import pytest

from python.modules.editing.split_py.tests.plan_cases import SUCCESSES, inputs


@pytest.mark.parametrize('case', SUCCESSES, ids=lambda c:c['id'])
def test_native_inventory_summary(case):
    from python.modules.editing.split_py.domain import inventory
    _, _, raw, _ = inputs(case)
    info = inventory.file_inventory(inventory.decode(raw))
    summary = {'symbols':[{k:item[k] for k in ('name','kind','lines','is_public','state')}
                         for item in info['symbols']], 'imports':len(info['imports']),
               'other':len(info['other']), 'docstring':bool(info['docstring'])}
    assert summary == case['reference_result']['inventory']
    assert all(type(s['state']) is bool for s in summary['symbols'])


def test_decorators_sticky_comments_and_coding_header():
    from python.modules.editing.split_py.domain.inventory import file_inventory, _segment_text
    text = '# -*- coding: utf-8 -*-\n# sticky\n@decorate\ndef fn():\n    pass\n'
    info = file_inventory(text)
    assert info['symbols'][0]['line_start'] == 2
    assert info['symbols'][0]['lines'] == 4
    assert _segment_text(text.splitlines(), 2, 5) == '# sticky\n@decorate\ndef fn():\n    pass'
