from importlib import import_module
from pathlib import Path
from unittest.mock import patch
import pytest
from python.kernel.errors import AppError
from tests.py.context.observations import references

def adapter(project,state):
    return import_module('python.substrate.assistant.judge_read').JudgeRead(project,state,Path(__file__).resolve().parents[3])

def test_composition_is_lazy_and_keeps_ask(tmp_path):
    from python.runtime.bootstrap import default_ports
    port=default_ports(tmp_path,'test',tmp_path.parent/'state')['librarian']
    assert callable(port.judge) and callable(port.answer)

@pytest.mark.parametrize('mode',['return','exception','interrupt'])
def test_shared_lock_profile_route_finally_restored(tmp_path,mode):
    project=tmp_path/'project';project.mkdir()
    with references(tmp_path/'refs') as subjects:
        port=adapter(project,tmp_path/'state')
        module=import_module('python.substrate.assistant.answer_judge')
        lock=port.answer.__globals__['_LOCK']
        assert import_module('python.substrate.assistant.judge_read')._LOCK is lock
        old=(subjects['data']._BASE_OVERRIDE,subjects['history']._STORAGE_OVERRIDE,subjects['api']._migrate_legacy_addon_cache)
        def native(*args,**kwargs):
            assert lock._is_owned()
            assert str(tmp_path/'state') in subjects['data']._BASE_OVERRIDE
            assert str(tmp_path/'state') in subjects['history']._STORAGE_OVERRIDE
            if mode=='interrupt':raise KeyboardInterrupt()
            if mode=='exception':raise ValueError('expected injected failure')
            return {'structural_score':(1,1,1,1,1,0,0)}
        with patch.object(module,'judge_answer',side_effect=native):
            if mode=='interrupt':
                with pytest.raises(KeyboardInterrupt):port.judge('===DONE===')
            elif mode=='exception':
                with pytest.raises(ValueError):port.judge('===DONE===')
            else:assert port.judge('===DONE===')['structural_score']==[1,1,1,1,1,0,0]
        assert (subjects['data']._BASE_OVERRIDE,subjects['history']._STORAGE_OVERRIDE,subjects['api']._migrate_legacy_addon_cache)==old

def test_state_inside_project_denied_before_io(tmp_path):
    project=tmp_path/'project';project.mkdir();port=adapter(project,project/'state')
    with pytest.raises(AppError) as caught:port.judge('===DONE===')
    assert caught.value.kind=='denied'
    assert list(project.rglob('*'))==[]

def test_missing_project_not_found(tmp_path):
    with pytest.raises(AppError) as caught:adapter(tmp_path/'missing',tmp_path/'state').judge('===DONE===')
    assert caught.value.kind=='not_found'
