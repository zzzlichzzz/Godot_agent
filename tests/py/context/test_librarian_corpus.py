"""Measured corrected-native observations, including original EOL/storage bytes."""
import json
import pytest
from tests.py.context.observations import CORPUS,observe

CATALOG=json.loads((CORPUS/'catalog.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('case',CATALOG,ids=lambda case:case['id'])
def test_corrected_native_corpus(case,tmp_path,capsys):
    expected=json.loads((CORPUS/'observations'/f"{case['id']}.json").read_text(encoding='utf-8'))
    assert observe(case,tmp_path/str(case['id']))==expected
    if case['operation']=='log':
        captured=capsys.readouterr()
        assert captured.out==captured.err==''

@pytest.fixture(scope='module')
def guard_result(tmp_path_factory):
    from tests.py.context.guard_operations import replay
    return replay(tmp_path_factory.mktemp('librarian-guard'))

@pytest.mark.parametrize('index',range(72),ids=lambda index:f'guard-{index+1:02d}')
def test_guard72(index,guard_result):
    expected=json.loads((CORPUS/'guard72.json').read_text(encoding='utf-8'))['checks']
    actual=guard_result['checks'][index]
    assert actual['pass'],actual
    assert actual==expected[index]
