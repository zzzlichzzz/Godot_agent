from importlib import import_module
from types import SimpleNamespace
import pytest
from python.kernel.errors import AppError

def request(args):
    return import_module('python.modules.assistant.judge.domain.request').request(args,SimpleNamespace(allow_addons=False,allow_self_edit=False))

@pytest.mark.parametrize('args',[{},None,{'full_text':False},{'full_text':'\x00'},{'full_text':''},{'full_text':'x','extra':1},{'full_text':'x'*200001}])
def test_bad_request(args):
    with pytest.raises(AppError) as caught:request(args)
    assert caught.value.kind=='invalid_input'

def test_text_is_preserved_and_flags_are_policy_owned():
    assert request({'full_text':' x\r\n===DONE==='})==(' x\r\n===DONE===',False,False)
