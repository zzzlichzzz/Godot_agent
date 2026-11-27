"""The literal Qwen answer, project transaction and receipt in the original browser conversation."""
import json

import pytest

from .test_qwen_choice import PAGE, bind_local_qwen
from .test_studio_conversation import local_studio
from tests.py.panel_tf.rename_example import ACTION, PROPOSAL, write_sources
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


SUMMARY='Изменены два файла. Тип объекта статически не доказан.'
SINGLE=PAGE[:PAGE.index(' if(location')] + '''
 const first=sends===1;
 window.requests=(window.requests||[]).concat([{path:location.pathname,text:user.innerText}]);
 history.pushState({},'', '/c/rename-test');
 network=first?PROPOSAL:SUMMARY;
 shell.innerHTML='<div class="response-message-content"><div class="qwen-markdown"></div></div>'+footer;
 shell.querySelector('.qwen-markdown').innerText=network;
};</script>'''.replace('PROPOSAL',json.dumps(PROPOSAL)).replace('SUMMARY',json.dumps(SUMMARY+'\n===DONE==='))
CARDS=PAGE.replace("card('B','Second answer.\\n===DONE===')",'card(\'B\','+json.dumps(PROPOSAL)+')').replace("network='Continuing '+votes.at(-1)+'.\\n===DONE===';",
    'window.requests=[{path:location.pathname,text:user.innerText}];network='+json.dumps(SUMMARY+'\n===DONE===')+';')


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio,confirm,expected_path',[
    ({'https://chat.qwen.ai/*':SINGLE},'/chat/confirm_action','/c/rename-test'),
    ({'https://chat.qwen.ai/*':CARDS},'/chat/confirm','/c/selected'),
],indirect=['local_studio'],ids=['single-json','two-cards'])
def test_reported_rename_commits_once_and_returns_receipt(local_studio,confirm,expected_path,client,cold_tf6,monkeypatch):
    http,headers,state,_,(_,_,app)=cold_tf6;driver=local_studio
    bind_local_qwen(app,driver,monkeypatch)
    before=write_sources(client[1])
    def post(path,**kw):return http.post(path,headers=headers,json=dict(panel_body(app,state,**kw),allow_addons=False,allow_self_edit=False))
    cid=post('/chats/new',site_id='qwen').json['current_id']
    result=post('/chat',chat_id=cid,prompt='Проверь rename_symbol')
    assert result.status_code==200 and result.json['pending_confirmation'],result.json
    assert result.json['turns_used']==1 and result.json['response']=='Предлагаю переименование.'
    plan=result.json['preview']; warnings=plan['warnings'];identity={k:plan[k] for k in ('digest','plan_id')}
    assert any('Включена недоказанная ссылка' in w and 'coin.gd:4' in w for w in warnings),warnings
    assert all(p.read_bytes()==data for p,data in before.items())
    assert driver.execute_script('return sends')==1
    receipt=post(confirm,approved=True,chat_id=cid,**identity)
    assert receipt.status_code==200 and receipt.json['state']=='COMMITTED',receipt.json
    assert sorted(receipt.json['changed_paths'])==['res://src/scripts/coin.gd','res://src/scripts/player.gd']
    assert 'переименуется сама' not in receipt.json['message'] and warnings[0] in receipt.json['message']
    assert all(p.read_bytes()==data.replace(b'add_coin',b'gain_coin') for p,data in before.items())
    ticket=receipt.json['rename_report_request']; report='/chat/rename/report'
    assert post(report,**dict(ticket,chat_id='foreign')).status_code==409
    assert post(report,**dict(ticket,entry_id='foreign')).status_code==409
    summary=post(report,**ticket);assert summary.status_code==200 and summary.json.get('answer')==SUMMARY,summary.json
    request=driver.execute_script('return requests.at(-1)');assert request['path']==expected_path
    assert json.loads(request['text'].splitlines()[-1])==dict(old_name=ACTION['old_name'],new_name=ACTION['new_name'],state='COMMITTED',changed_files=2,warnings=len(warnings))
    assert 'res://' not in request['text'] and 'has_method' not in request['text']
    assert post(report,**ticket).status_code==409 and driver.execute_script('return sends')==2
    assert post('/chat/rollback').json['state']=='ROLLED_BACK'
    assert all(p.read_bytes()==data for p,data in before.items())
