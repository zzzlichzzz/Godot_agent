import pytest
from tests.py.engine_cache.observations import cases,observe

@pytest.mark.parametrize('row',cases('lint'),ids=lambda row:row['id'])
def test_lint_corpus(row,tmp_path):
    actual=observe(row['input'],tmp_path/row['id'])
    assert actual==row['expected']
    assert actual['before']==actual['after']
    assert isinstance(actual['result'],list) and len(actual['result'])<=8
