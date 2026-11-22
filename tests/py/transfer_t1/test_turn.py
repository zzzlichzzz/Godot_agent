"""Real dispatcher/native judge with offline model packets, not live success."""
import json
import pytest
from python.runtime.bootstrap import build_agent,default_ports
from tests.py.transfer_t1.test_write import client,physical

class OfflineGateway:
    def __init__(self,packets):self.packets=list(packets);self.sent=[]
    def system_prompt(self,*,tree=''):return 'offline-system:'+tree
    def send(self,text,*,system_text=None):
        self.sent.append((text,system_text))
        assert self.packets,'Unexpected model call'
        return self.packets.pop(0)

def packet(action=None,text='Готово.',done=True):
    raw=text+('\n```agent_action\n'+json.dumps(action,ensure_ascii=False)+'\n```' if action else '')+('\n===DONE===' if done else '')
    return dict(text=text,raw=raw,done=done,action=action)

def with_packets(client,packets):
    _,project,state=client;ports=default_ports(project,'cli',state_dir=state)
    gateway=OfflineGateway(packets);ports['chat_gateway']=gateway
    return build_agent(project,profile='cli',state_dir=state,ports=ports),gateway,project

def test_model_write_is_preview_only_and_explicit_confirmation(client):
    action=dict(action='create_file',path='res://new.gd',content='extends Node\n')
    agent,gateway,project=with_packets(client,[packet(action,text='Создам файл.')]);before=physical(project)
    answer=agent.call('assistant_turn',dict(text='Создай файл.'))
    assert answer['ok'],answer
    assert answer['result']['state']=='pending_confirmation' and physical(project)==before
    plan=answer['result']['plan'];assert gateway.sent[0][1].startswith('offline-system:')
    result=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert result['ok'] and (project/'new.gd').read_bytes()==b'extends Node\n'

def test_read_then_final_without_write(client):
    agent,gateway,project=with_packets(client,[packet(dict(action='read_file',path='res://hero.gd')),packet()]);before=physical(project)
    answer=agent.call('assistant_turn',dict(text='Прочитай файл.'))
    assert answer['ok'],answer
    assert answer['result']['state']=='final' and len(gateway.sent)==2 and physical(project)==before
    assert 'T1Hero' in gateway.sent[1][0]

@pytest.mark.parametrize('action',[dict(action='command',command='unsafe'),dict(action='write_apply',plan_id='forged')])
def test_unknown_or_executor_action_never_grants_write(client,action):
    agent,_,project=with_packets(client,[packet(action)]);before=physical(project)
    answer=agent.call('assistant_turn',dict(text='Нет разрешения.'))
    assert not answer['ok'] and answer['kind']=='denied' and physical(project)==before

def test_incomplete_reply_repaired_until_limit_without_write(client):
    agent,gateway,project=with_packets(client,[packet(text='Без конца.',done=False)]*2);before=physical(project)
    answer=agent.call('assistant_turn',dict(text='Ответь.',max_turns=2))
    assert not answer['ok'] and answer['kind']=='unavailable' and len(gateway.sent)==2 and physical(project)==before
