"""Selected tab and stable Studio URLs, without an account or provider request."""
import pytest

from .test_studio_conversation import START, local_studio
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


@pytest.mark.needs_live
def test_studio_new_and_reopen_in_actual_browser(local_studio, cold_tf6, monkeypatch):
    browser = local_studio
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']; store = refs.routes.chat_store
    monkeypatch.setattr(refs.state, 'wait_driver', lambda: browser)
    monkeypatch.setattr(refs.state, 'get_driver', lambda: browser)
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: browser)
    def post(path, **data):
        return http.post(path, headers=headers, json=dict(panel_body(app, state, **data), allow_addons=False))

    # Model a Studio page which was saved with ?save=true. The transient URL
    # deliberately fails on a fresh navigation; its durable prompt does not.
    saved = START.replace('new_chat', 'conversation_A')
    active, other = browser.window_handles
    browser.switch_to.window(active)
    browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': '''
      document.addEventListener('DOMContentLoaded',()=>{
        if(location.search==='?save=true' || location.pathname.endsWith('/removed')){history.replaceState({},'', '/');return;}
         if(location.pathname.endsWith('conversation_A') || sessionStorage.sticky){
          if(sessionStorage.sticky) history.replaceState({},'', '/');
         if(sessionStorage.action){const b=document.createElement('button');b.innerText='New chat';
           b.onclick=()=>{delete sessionStorage.sticky;location.assign('/prompts/new_chat');};document.body.append(b);}
         for (const [role,text] of [['User','my specific question'],['Model','my specific answer']]){
            const n=document.createElement('div');n.dataset.turnRole=role;n.innerText=text;document.body.append(n);}
        }
      });'''})
    browser.get(saved)
    rec = store.create_chat(str(state),url=saved+'?save=true')
    store.update_chat(str(state),rec['id'],site_id='aistudio')
    for role, text in [('user','my specific question'),('agent','my specific answer')]:
        store.append_transcript(str(state),rec['id'],role,text)
    created = post('/chats/new',site_id='aistudio'); assert created.status_code == 200,created.json
    assert browser.current_window_handle == active and browser.current_url == START
    assert browser.execute_script('return !field.value && !document.querySelector("[data-turn-role]")')
    opened = post('/chats/open',id=rec['id'])
    assert not opened.json['history_only'] and browser.current_url == saved
    assert store.find_chat(str(state),rec['id'])['url'] == saved
    missing = store.create_chat(str(state), url=START.replace('new_chat','removed'))
    store.update_chat(str(state),missing['id'],site_id='aistudio')
    store.append_transcript(str(state),missing['id'],'user','another question')
    assert post('/chats/open',id=missing['id']).json['history_only']
    assert browser.current_window_handle == active and browser.current_url == saved
    rejected = post('/chat/live_input',chat_id=missing['id'],seq=8,text='wrong destination')
    assert rejected.json == {'ok': True, 'applied': False, 'reason': 'history_only'}, rejected.json
    store.update_chat(str(state),rec['id'],url=saved+'-obsolete')
    assert not post('/chats/open',id=rec['id']).json['history_only']
    assert store.find_chat(str(state),rec['id'])['url'] == saved

    # Old installs persisted only new_chat. Rebind only the active, matching
    # conversation; refuse a different transcript even on the right origin.
    store.update_chat(str(state),rec['id'],url=START)
    browser.execute_script('document.querySelector("[data-turn-role=Model]").innerText="other answer"')
    assert post('/chats/open',id=rec['id']).json['history_only']
    assert store.find_chat(str(state),rec['id'])['url'] == START
    browser.get(saved)
    assert not post('/chats/open',id=rec['id']).json['history_only']
    assert store.find_chat(str(state),rec['id'])['url'] == saved
    browser.execute_script('sessionStorage.sticky="true"')
    count=len(store.list_chats(str(state)))
    assert post('/chats/new',site_id='aistudio').status_code != 200
    assert len(store.list_chats(str(state))) == count
    browser.execute_script('sessionStorage.action="true"')
    assert post('/chats/new',site_id='aistudio').status_code == 200
    assert browser.current_window_handle == active and browser.current_url == START
    assert browser.execute_script('return !field.value && !document.querySelector("[data-turn-role]")')
    browser.switch_to.window(other);assert browser.current_url=='about:blank'
