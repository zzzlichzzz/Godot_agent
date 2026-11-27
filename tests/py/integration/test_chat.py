"""K1 public protocol tests belong outside modules (R-11), not an import bypass."""
from importlib import import_module
from unittest.mock import patch
import pytest
from python.runtime.bootstrap import build_agent, default_ports
from python.modules.assistant.chat.tests.test_loop import Scripted, reply
from tests.py.chat_k1.isolation import isolated_chat_native_generation

def test_public_module_registered_and_closed_result(tmp_path):
    project=tmp_path/'project'; project.mkdir()
    port=Scripted([reply()])
    ports=default_ports(project,'headless',tmp_path/'state'); ports['chat_gateway']=port
    agent=build_agent(project,profile='headless',state_dir=tmp_path/'state',ports=ports)
    entry=agent._registry.get('chat')
    assert entry is not None and entry.module_id=='assistant.chat'
    assert entry.spec.effects=='read' and not entry.spec.idempotent and entry.spec.cost=='heavy'
    module=import_module('python.modules.assistant.chat.module').MODULE
    assert module.provides_tools==('chat',) and module.requires_ports==('chat_gateway',)
    assert set(module.entrypoints)=={'setup','call'}
    with patch('python.modules.assistant.chat.app.judge_reply',return_value={'score':74,'acceptable':True}):
        response=agent.call('chat',{'text':'hello'})
    assert response=={'ok':True,'result':dict(text='answer',turns_used=1,actions_executed=[],judge_summary={'score':74,'acceptable':True})}
    assert entry.spec.result['additionalProperties'] is False
    assert entry.spec.result['required']==['text','turns_used','actions_executed','judge_summary']

@pytest.mark.parametrize('args', [{}, {'text':''}, {'text':'ok','extra':1}, {'text':'ok','max_turns':0},
                                  {'text':'ok','max_turns':9}, {'text':'ok','max_turns':True},
                                  {'text':'ok','budget_chars':0}])
def test_public_invalid_args_rejected_before_provider(tmp_path,args):
    project=tmp_path/'project'; project.mkdir(); port=Scripted([])
    agent=build_agent(project,profile='headless',state_dir=tmp_path/'state',ports={'chat_gateway':port})
    value=agent.call('chat',args)
    assert value['ok'] is False and value['kind']=='invalid_input' and not port.prompts
