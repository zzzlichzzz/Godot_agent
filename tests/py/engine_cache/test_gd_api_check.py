import json
import pytest
from tests.py.engine_cache.observations import OLD_API,cases,observe

@pytest.mark.parametrize('row',cases('api'),ids=lambda row:row['id'])
def test_api_check_corpus(row,tmp_path):
    actual=observe(row['input'],tmp_path/row['id'])
    assert actual==row['expected']
    if 'old_case' in row['input']:
        old=json.loads((OLD_API/row['input']['old_case']).read_text(encoding='utf-8'))
        if 'reference_result' in old:
            assert actual['result']==old['reference_result']
