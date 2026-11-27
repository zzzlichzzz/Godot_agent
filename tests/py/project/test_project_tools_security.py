"""Native containment/access observations; junctions real, UNC OS seam explicit."""
import pytest

from tests.py.project.observations import cases, load, observe

ROWS = cases('security')


@pytest.mark.parametrize('row', ROWS, ids=[row['id'] for row in ROWS])
def test_project_security_corpus(row, tmp_path):
    case = load(row)
    actual = observe(case['input'], tmp_path / 'sandbox')
    assert actual == case['expected']
    assert actual['before'] == actual['after'], 'path observation wrote fixture bytes'
    if case['input']['kind'] == 'path':
        result = actual['result']
        if not result['classification']['in_project'] or result['classification']['is_history']:
            assert (result['read'], result['write'], result['reference']) == (False, False, False)
        if result['classification']['is_project_settings']:
            assert result['write'] is False
    else:
        # This environment has no symlink privilege; not a successful symlink proof.
        assert actual['result']['winerror'] == 1314
