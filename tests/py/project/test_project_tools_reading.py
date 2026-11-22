"""Read/scanner/scene/architecture observations preserve native result and refusal."""
import pytest

from tests.py.project.observations import cases, load, observe

ROWS = cases('reading')


@pytest.mark.parametrize('row', ROWS, ids=[row['id'] for row in ROWS])
def test_project_reading_corpus(row, tmp_path):
    case = load(row)
    actual = observe(case['input'], tmp_path / 'sandbox')
    assert actual == case['expected']
    assert actual['before'] == actual['after'], 'read observation changed fixture'
