"""Public projection independently from captured native replies (R-16)."""
import json
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[5] / 'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json')) if (c := json.loads(p.read_bytes()))['tool']=='split_scan']
SUCCESSES = [c for c in CASES if c['expect']['ok']]


@pytest.mark.parametrize('case', SUCCESSES, ids=lambda c: c['id'])
def test_assemble_native(case):
    from python.modules.editing.split_py.domain.core import assemble
    raw = case['reference_result']
    before = json.dumps(raw, sort_keys=True)
    assert assemble(raw['rel'], raw['stem'], raw) == case['expect']['result']
    assert json.dumps(raw, sort_keys=True) == before


def test_sorted_both_lists_and_retained_only():
    from python.modules.editing.split_py.domain.core import assemble
    refs = {'counts': {'import': 1, 'source_read': 0, 'patch': 100, 'mention': 1, 'doc': 1},
            'occurrences': [{'rel': rel, 'line': i+1, 'kind': kind, 'text': 'x'}
                            for i, (rel, kind) in enumerate([('z.py','import'),('z.py','mention'),('a.md','doc')])],
            'truncated': True}
    result = assemble('pkg/donor.py', 'donor', refs)
    assert result['hard_files'] == ['z.py'] and result['soft_files'] == ['a.md', 'z.py']
    assert result['truncated'] and result['counts']['patch'] == 100
