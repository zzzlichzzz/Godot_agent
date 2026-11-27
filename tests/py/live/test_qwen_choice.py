"""Qwen parallel answers, real DOM and project judge through the panel HTTP route."""
import pytest

from .test_studio_conversation import local_studio
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.transfer_t1.test_write import client


PAGE='''<textarea class="message-input-textarea"></textarea><script>
window.votes=JSON.parse(sessionStorage.votes||'[]');window.sends=0;window.network='';
document.querySelector('textarea').onkeydown=e=>{if(e.key!=='Enter')return;
 e.preventDefault();let user=document.createElement('div');user.className='qwen-chat-message-user';
 user.innerText=e.target.value;document.body.append(user);e.target.value='';sends++;
 let shell=document.createElement('div');shell.className='qwen-chat-message-assistant';document.body.append(shell);
 const footer='<div class="response-message-footer"><div class="qwen-chat-package-comp-new-action-control-icons"></div></div>';
 if(location.pathname==='/c/selected' && votes.length){
   network='Continuing '+votes.at(-1)+'.\\n===DONE===';
   shell.innerHTML='<div class="response-message-content"><div class="qwen-markdown"></div></div>'+footer;
   shell.querySelector('.qwen-markdown').innerText=network;return;}
 network='Wrong network branch.\\n===DONE===';
 let list=document.createElement('div');list.className='smrm-list';shell.append(list);
 function card(key,text){let el=document.createElement('div');el.className='smrm-card';
 el.innerHTML='<div class="smrm-card__content"><div class="response-message-content"><div class="qwen-markdown"></div></div></div><div class="smrm-card__footer"><button class="smrm-card__prefer-btn">Prefer</button></div>';
 list.append(el);el.querySelector('.qwen-markdown').innerText=text;
  el.querySelector('button').onclick=()=>{votes.push(key);sessionStorage.votes=JSON.stringify(votes);shell.replaceChildren(el.querySelector('.response-message-content'));shell.insertAdjacentHTML('beforeend',footer);history.pushState({},'','/c/selected')};}
 card('A','First answer.\\n```agent_action\\n{"action":"unknown_fixture_action"}\\n```\\n===DONE===');
 setTimeout(()=>card('B','Second answer.\\n===DONE==='),650);
};</script>'''


LEGACY=PAGE.replace("list.className='smrm-list'", "list.className='parallel-answers'").replace('smrm-card__prefer-btn','smulti-make-better')
SYMBOL=PAGE.replace('unknown_fixture_action','analyze_rename').replace('Second answer.\\n===DONE===',
    'Second answer.\\n```agent_action\\n{"action":"find_symbol_usages","arguments":{"kind":"function","old_name":"collect_coin"}}\\n```\\n===DONE===')


def bind_local_qwen(app, driver, monkeypatch):
    refs=app.extensions['native_references']
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers.qwen_delivery import QwenDelivery
    for name in ('wait_driver','get_driver'): monkeypatch.setattr(refs.state,name,lambda *a,**kw:driver)
    monkeypatch.setattr(app.extensions['godot_session'].gateway,'current_driver',lambda:driver)
    monkeypatch.setattr(browser_backend,'wait_driver',lambda:driver)
    monkeypatch.setattr(QwenDelivery,'_maybe_harden_background_tab',lambda *_:None)
    monkeypatch.setattr(QwenDelivery,'_ensure_monitor',lambda *_:None)
    monkeypatch.setattr(QwenDelivery,'insert_input_for_send',QwenDelivery.insert_input)
    monkeypatch.setattr(QwenDelivery,'_net_live_text',lambda *_:driver.execute_script('return network'))
    monkeypatch.setattr(QwenDelivery,'net_answer_ready',lambda *_:driver.execute_script('return !!network'))


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio,expect_read',[({'https://chat.qwen.ai/*':p},p==SYMBOL) for p in (PAGE,LEGACY,SYMBOL)],indirect=['local_studio'],ids=['cards','legacy-buttons','symbol-read'])
def test_qwen_judges_complete_cards_before_accepting_network_branch(local_studio,expect_read,client,cold_tf6,monkeypatch):
    http,headers,state,_,(_,_,app)=cold_tf6; refs=app.extensions['native_references'];driver=local_studio
    bind_local_qwen(app,driver,monkeypatch)
    def post(path,**kw):return http.post(path,headers=headers,json=dict(panel_body(app,state,**kw),allow_addons=False,allow_self_edit=False))
    cid=post('/chats/new',site_id='qwen').json['current_id']
    result=post('/chat',chat_id=cid,prompt='test alternatives')
    assert driver.execute_script('return [sends,votes]')==[1,['B']]
    if expect_read:
        assert result.status_code==200 and result.json['read_request']['action']==dict(action='find_symbol_usages',kind='function',old_name='collect_coin'),result.json
        return
    assert result.status_code==200 and result.json['response']=='Second answer.',result.json
    saved='https://chat.qwen.ai/c/selected'
    assert refs.routes.chat_store.find_chat(str(state),cid)['url']==saved
    driver.get('https://chat.qwen.ai/'); assert not post('/chats/open',id=cid).json['history_only'] and driver.current_url==saved
    follow=post('/chat',chat_id=cid,prompt='continue on this branch')
    assert follow.status_code==200 and follow.json['response']=='Continuing B.',follow.json
    assert driver.execute_script('return [sends,votes]')==[1,['B']]


@pytest.mark.needs_live
def test_reported_monaco_cards_and_fallback_vote(local_studio,cold_tf6,tmp_path):
    import json
    from pathlib import Path
    from python.substrate.llm.parsers.qwen_choices import QwenChoices, _DOM
    from parser_base import split_net_text_and_action
    sample=Path(__file__).resolve().parents[3]/'docs/elements.txt'
    if not sample.is_file():pytest.skip('Original Qwen Elements capture not provided')
    driver=local_studio;driver.get('about:blank'); choices=QwenChoices(driver,tmp_path,None)
    driver.execute_script('document.body.innerHTML=arguments[0];',sample.read_text('utf-8'))
    rows=driver.execute_script(_DOM+'return rows(lists().at(-1));')
    actions=[json.loads(split_net_text_and_action(row[1])[1]) for row in rows]
    assert [(a['action'],a['max_depth']) for a in actions]==[('list_files',2),('list_files',3)] and actions[1]['only_exts']==['gd']
    driver.execute_script("window.votes=[];document.querySelectorAll('.smrm-card__prefer-btn').forEach((b,i)=>b.onclick=()=>{votes.push(i);b.setAttribute('aria-pressed','true')})")
    choices.resolve(driver,lambda _:None);choices.resolve(driver,lambda _:None)
    votes=driver.execute_script('return votes');assert len(votes)==1 and choices.action==actions[votes[0]]
    driver.execute_script("document.querySelectorAll('.smrm-card__content .qwen-markdown').forEach(n=>n.innerText='incomplete')")
    # New turn with a new group (not the already judged group).
    saved=driver.execute_script("const l=document.querySelector('.smrm-list');l.remove();return l.outerHTML;")
    choices=QwenChoices(driver,tmp_path,None);driver.execute_script("document.body.insertAdjacentHTML('beforeend',arguments[0]);",saved)
    driver.execute_script("document.querySelectorAll('.smrm-card__prefer-btn').forEach((b,i)=>{b.removeAttribute('aria-pressed');b.onclick=()=>{votes.push(i);b.setAttribute('aria-pressed','true')}})")
    choices.resolve(driver,lambda _:None);choices.resolve(driver,lambda _:None)
    assert driver.execute_script('return votes')==votes+[0] and choices.action['action']=='parse_error'


@pytest.mark.needs_live
def test_unreadable_code_selects_branch_without_executing_it(local_studio,cold_tf6,tmp_path):
    from python.substrate.llm.parsers.qwen_choices import QwenChoices
    driver=local_studio;driver.get('about:blank'); choices=QwenChoices(driver,tmp_path,None)
    driver.execute_script('''document.body.innerHTML='<div class="qwen-chat-message-assistant"><div class="smrm-list"></div></div>';
        const group=document.querySelector('.smrm-list'); window.votes=[];
        for(const key of ['A','B']){
            group.insertAdjacentHTML('beforeend','<div class="smrm-card"><div class="response-message-content phase-answer"><div class="qwen-markdown"><pre class="qwen-markdown-code"><span class="view-lines"></span></pre></div></div><div class="smrm-card__footer"><button class="smrm-card__prefer-btn">Choose</button></div></div>');
            const card=group.lastElementChild;card.querySelector('button').onclick=()=>{votes.push(key);group.replaceWith(card.querySelector('.response-message-content'));};
        }''')
    choices.resolve(driver,lambda _:None);choices.resolve(driver,lambda _:None)
    assert driver.execute_script('return votes')==['A'] and choices.action['action']=='parse_error' and choices.frame['actionRaw'] is None
