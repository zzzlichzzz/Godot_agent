"""Real dispatcher/native judge with offline model packets, not live success."""
import json
import pytest
from python.runtime.bootstrap import build_agent,default_ports
from tests.py.transfer_t1.test_write import client,physical

class OfflineGateway:
    def __init__(self,packets):self.packets=list(packets);self.sent=[]
    def send(self,text,*,system_text=None,max_chars=None):
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
    plan=answer['result']['plan']
    assert 'res://hero.gd' in gateway.sent[0][1] and 'only the user can approve' in gateway.sent[0][1]
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


@pytest.mark.parametrize('tool',['chat','assistant_turn'])
def test_both_loops_use_the_same_navigation_and_snapshot(client,tool):
    from tests.py.browser.runtime_cases import references

    actions = [dict(action='list_files',dir='res://',only_exts=['.gd']),
               dict(action='read_file',path='res://hero.gd',offset=0,max_chars=7),
               dict(action='read_function',path='res://hero.gd',name='hit'),
               dict(action='search_project',query='t1hero',case_insensitive=True,max_results=1,context_lines=0),
               dict(action='gather_context',sections=['tools','architecture']),
               dict(action='find_symbol_usages',kind='function',old_name='hit',declaration_path='res://hero.gd')]
    packets = []
    with references() as modules:
        for action in actions:
            value, error = modules['parser_base'].parse_action_json(json.dumps(action))
            assert error is None
            packets.append(packet(value))
    _,project,_=client
    (project/'AGENT_ARCHITECTURE.md').write_text('Hero logic lives in hero.gd.',encoding='utf-8')
    agent,gateway,project=with_packets(client,[*packets,packet()]);before=physical(project)
    result=agent.call(tool,dict(text='Разберись в проекте.'))
    assert result['ok'],result
    assert len(gateway.sent)==7 and physical(project)==before
    instructions=gateway.sent[0][1]
    assert all(prompt is instructions for _,prompt in gateway.sent)
    assert 'res://hero.gd' in instructions and 'list_files' in instructions
    assert 'Hero logic lives in hero.gd.' in instructions
    assert 'copy_file' not in instructions and 'inspect_runtime' not in instructions
    feedback=[json.loads(text.split('\n',2)[1])[0] for text,_ in gateway.sent[1:]]
    assert [item['path'] for item in feedback[0]['children']]==['res://hero.gd']
    assert len(feedback[1]['content'])==7 and feedback[1]['next_offset']==7
    assert [item['name'] for item in feedback[2]['functions']]==['hit']
    assert feedback[3]['matches'][0]['path']=='res://hero.gd'
    assert feedback[4]['sections']['architecture']['summary']=='Hero logic lives in hero.gd.'
    assert feedback[5]['declaration'].startswith('res://hero.gd:')


def test_read_function_without_names_is_a_list(client):
    agent,gateway,_=with_packets(client,[packet(dict(action='read_function',path='res://hero.gd')),packet()])
    assert agent.call('assistant_turn',dict(text='Какие есть функции?'))['ok']
    feedback=json.loads(gateway.sent[1][0].split('\n',2)[1])[0]
    assert 'hit' in feedback['names'] and 'functions' not in feedback
