"""Real Windows parent casing/rollback state on owned synthetic fixture copies."""
import pytest

from tests.py.project.observations import cases, load, observe

ROWS = cases('casing')


@pytest.mark.parametrize('row', ROWS, ids=[row['id'] for row in ROWS])
def test_project_casing_corpus(row, tmp_path):
    case = load(row)
    actual = observe(case['input'], tmp_path / 'sandbox')
    assert actual == case['expected']
    if case['input']['mode'] in ('rollback', 'bad_depth', 'apply_failure'):
        assert actual['before'] == actual['after'], 'rollback did not restore exact casing/bytes'
    if case['input']['mode'] == 'rollback_failure':
        assert actual['result']['rollback_succeeded'] is False
        assert actual['result']['failed_renames']
        assert actual['after'] == actual['result']['middle'], 'failed recovery lost retained data'
