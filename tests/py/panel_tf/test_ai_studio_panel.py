"""AI Studio panel reports: instruction identity, page error and all five approved tools."""
import hashlib
import json
from importlib import import_module

from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


def test_ai_studio_instructions_survive_list_and_provider_error(client,cold_tf6,monkeypatch):
    http,headers,state,_,app=_setup_browser_chat(client,cold_tf6,monkeypatch,'aistudio')
    from python.substrate.llm.api import chat_store
    cid=app.extensions['native_references'].state.STATE['current_chat_id']
    def post(route, **fields):
        return http.post(route,json=dict(panel_body(app,state,**fields),allow_addons=False,allow_self_edit=False),headers=headers)
    def current():return next(c for c in post('/chats/list').json['chats'] if c['id']==cid)
    assert not current()['prompt_stale']
    calls=[];notice="Model 2:57 AM error  Model isn't available right now. Please wait a minute and try again."
    replies=iter([notice,'[b]Важно[/b]','Цитата: '+notice])
    def send(_,prompt,**kw):calls.append(prompt);return dict(text=next(replies),action=None)
    monkeypatch.setattr(import_module('python.substrate.llm.browser.backends.browser_backend').BrowserBackend,'send',send)
    failure=post('/chat',chat_id=cid,prompt='один')
    assert failure.json.get('kind')=='unavailable' and len(calls)==1
    assert not current()['primed'] and notice not in (state/'agent_chats.json').read_text('utf8')
    assert post('/chat',chat_id=cid,prompt='два').json['answer']=='[b]Важно[/b]'
    system=calls[1].split('\n\n=== CURRENT REQUEST')[0]
    assert chat_store.find_chat(str(state),cid)['prompt_hash']==hashlib.sha256(system.encode()).hexdigest()
    assert current()['primed'] and not current()['prompt_stale']
    assert post('/chat',chat_id=cid,prompt='три').json['answer']=='Цитата: '+notice and calls[2]=='три'
    chat_store.update_chat(str(state),cid,prompt_hash='different-delivered-instructions')
    assert current()['prompt_stale']


def test_panel_draft_is_delivered_only_to_selected_studio_prompt(client,cold_tf6,monkeypatch):
    from python.substrate.llm.parsers.studio_draft import _EDIT
    http,headers,state,_,app=_setup_browser_chat(client,cold_tf6,monkeypatch,'aistudio')
    refs=app.extensions['native_references'];gateway=app.extensions['godot_session'].gateway
    url='https://aistudio.google.com/prompts/new_chat';calls=[]
    driver=gateway.current_driver();driver.current_url=url
    driver.execute_script=lambda script,target,text:calls.append((script,target,text)) or True
    refs.routes.chat_store.update_chat(str(state),refs.state.STATE['current_chat_id'],url=url)
    def draft(seq,text):
        body=dict(panel_body(app,state,seq=seq,text=text),allow_addons=False,allow_self_edit=False)
        response=http.post('/chat/live_input',json=body,headers=headers)
        assert response.status_code==200,response.json
        return response.json
    assert draft(10,'draft')['applied'] and not draft(9,'old')['applied']
    driver.current_url=url.replace('new_chat','other');driver.window_handles=[]
    assert not draft(11,'wrong tab')['applied'] and calls==[(_EDIT,url,'draft')]


def test_five_approved_reads_and_actual_librarian_outcome(client,cold_tf6,monkeypatch):
    http,headers,state,root,app=_setup_browser_chat(client,cold_tf6,monkeypatch,'aistudio');before=physical(root)
    cid=app.extensions['native_references'].state.STATE['current_chat_id']; data=[]
    actions=iter([dict(action='search_project',query='hit',only_exts=['gd']),
        dict(action='read_function',path='res://hero.gd',names=['hit']),dict(action='list_scene',path='res://level.tscn'),
        dict(action='ask_librarian',query='hero',budget_chars=2000),dict(action='gather_context',sections=['project','tools','runtime']),None])
    def send(_,prompt,**kw):
        if prompt.startswith('Результат чтения:'):data.append(json.loads(prompt.split('\n')[1])[0])
        return dict(text='Проверено.',action=next(actions))
    monkeypatch.setattr(import_module('python.substrate.llm.browser.backends.browser_backend').BrowserBackend,'send',send)
    def post(path,**kw):
        r=http.post(path,json=dict(panel_body(app,state,chat_id=cid,**kw),allow_addons=False,allow_self_edit=False),headers=headers)
        assert r.status_code==200,r.json
        return r.json
    result=post('/chat',prompt='Проверь проект')
    for _ in range(5):result=post('/chat/read/decision',approved=True,request_id=result['read_request']['id'])
    assert result['state']=='final' and physical(root)==before
    assert data[0]['matches'] and 'func hit' in str(data[1]) and data[2]['nodes'][0]['name']=='Root'
    assert isinstance(data[3],str) and data[3].strip() and 'hero' in data[3].lower()
    assert 'project' in data[4]['sections'] and 'runtime' in str(data[4]['unavailable'])
    assert [(row['read_tool'],row['read_results']) for row in json.loads((state/'agent_turn_timings.json').read_text('utf8')) if 'read_tool' in row]==[(n,['ok']) for n in ('search','functions','scene','ask','context')]
