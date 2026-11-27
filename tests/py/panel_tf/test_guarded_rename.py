"""Reported probable rename: analysis, immutable previews, actual receipt and rollback."""
import pytest

from tests.py.panel_tf.test_qwen_turn import setup
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, ok, physical


OLD,NEW='collect_coin','add_coin'
PLAYER,COIN='res://player.gd','res://coin.gd'
ARGS=dict(kind='function',old_name=OLD,new_name=NEW,declaration=PLAYER+':2:6',mode='probable',allow_unverified=True)
SOURCE=('extends Area2D\nfunc hit(body):\n\tif body.has_method("collect_coin"):\n'
        '\t\tvar active = true\n\t\tbody.collect_coin()\n\tprint("collect_coin")\n'
        '\treturn body.has_method("collect_coin")\n')


@pytest.mark.parametrize('confirm',['/chat/confirm_action','/chat/confirm'])
def test_reported_rename_and_actual_files(client,cold_tf6,monkeypatch,confirm):
    agent,project,_=client
    (project/'player.gd').write_bytes(b'extends Node\nfunc collect_coin():\n\tpass\n')
    (project/'coin.gd').write_bytes(SOURCE.replace('\n','\r\n').encode())
    before=physical(project); after=SOURCE.replace('has_method("collect_coin"):', 'has_method("add_coin"):').replace('body.collect_coin()', 'body.add_coin()')
    usage=ok(agent,'usages',{k:ARGS[k] for k in ('kind','old_name','declaration')})
    analysis=ok(agent,'analyze_rename',ARGS)
    assert usage['usages']==analysis['usages'] and analysis['affected_paths']==[COIN,PLAYER]
    assert [(u['line'],u['confidence']) for u in usage['usages'] if u['path']==COIN]==[(3,'dynamic'),(5,'probable'),(7,'dynamic')]
    assert 'вместе' in usage['usages'][0]['note']
    preview=ok(agent,'write_preview',ARGS)
    assert preview['affected_paths']==[COIN,PLAYER] and preview['stats']['edits']==3
    # Removing the guard alone is not an approval to break the call underneath it.
    for tool in ('assistant_plan','write_preview'):
        partial=dict(ARGS,exclude=[COIN+':3']);args={'action':dict(partial,action='rename_symbol')} if tool=='assistant_plan' else partial
        refusal=agent.call(tool,args); assert not refusal['ok'] and refusal['details']['reason']=='partial_guard',refusal
    app,cid,post=setup(client,cold_tf6,monkeypatch)
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    monkeypatch.setattr(BrowserBackend,'send',lambda *a,**k:dict(action=dict(ARGS,action='rename_symbol'),text='Переименую.'))
    r=post('/chat',chat_id=cid,prompt='переименуй метод');assert r.status_code==200,r.json
    card=r.json['pending_action_description'];plan=r.json['preview']
    assert r.json['pending_action']['action']=='rename_symbol' and OLD+' → '+NEW in card
    assert COIN+':7' in card and 'Не переименовано: '+COIN+':3 ' not in card
    diff=next(d for d in plan['diffs'] if d['path']==COIN)
    visible=next(d for d in r.json['pending_action_diffs'] if d['path']==COIN)
    assert any(line[0]=='+' and 'has_method("add_coin")' in line[3] for line in visible['lines'])
    assert diff['after'].splitlines()==after.splitlines() and physical(project)==before
    identity={k:plan[k] for k in ('plan_id','digest')}
    assert post(confirm,chat_id='foreign',approved=True,**identity).status_code==409
    assert physical(project)==before
    r=post(confirm,chat_id=cid,approved=True,**identity);assert r.status_code==200,r.json
    assert sorted(r.json['changed_paths'])==[COIN,PLAYER] and OLD+' → '+NEW in r.json['message'] and COIN+':7' in r.json['message']
    assert (project/'coin.gd').read_text('utf-8')==after and (project/'player.gd').read_bytes()==before['player.gd'].replace(OLD.encode(),NEW.encode())
    assert post('/chat/rollback').status_code==200 and physical(project)==before
