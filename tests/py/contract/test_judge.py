from importlib import import_module
from python.kernel.schema import validate
import json
import pytest
from tests.py.judge_j1.observations import CORPUS,cases

def test_judge_contract_is_read_closed_bounded():
    spec=import_module('python.modules.assistant.judge.tools').JUDGE
    assert spec.effects=='read' and spec.idempotent and not spec.requires_preview
    assert spec.args['additionalProperties'] is False and spec.result['additionalProperties'] is False
    assert spec.errors==('invalid_input','not_found','denied')
    assert validate({'full_text':'===DONE==='},spec.args)==[]
    assert validate({'full_text':7},spec.args) and validate({'full_text':'x','extra':1},spec.args)
    assert validate({'unexpected':True},spec.result)

@pytest.mark.parametrize('case',cases(),ids=lambda x:x['id'])
def test_judge_result_covers_native_closed_envelope(case):
    spec=import_module('python.modules.assistant.judge.tools').JUDGE
    result=json.loads((CORPUS/'native'/(case['id']+'.json')).read_text('utf-8'))['answer']['result']
    assert validate(result,spec.result)==[]
