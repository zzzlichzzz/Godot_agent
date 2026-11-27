"""A saved chat must reopen in the selected tab even with an unrelated newer tab."""
from urllib.parse import urljoin
import pytest
from .test_studio_conversation import local_studio
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client

PAGE='''<ms-prompt-box><textarea name="message" class="message-input-textarea" id="chat-input"></textarea></ms-prompt-box>
<div class="chat-input-editor" contenteditable="true"></div><aside><a href="/c/original">Auto title</a></aside>
<script>if(location.pathname.endsWith('/original')){
 document.body.insertAdjacentHTML('beforeend','<p data-turn-role="User" class="qwen-chat-message-user">specific request</p><p class="qwen-chat-message-user">internal tool continuation</p><div data-turn-role="Model" class="qwen-chat-message-assistant"><div class="response-message-content phase-answer"><div class="qwen-markdown"><p><b>specific</b> <code>answer</code></p><pre><div class="qwen-markdown-code-header"><span>json</span></div>{"action":"list_files"}</pre><p>===DONE===</p></div></div></div>');
}</script>'''
PAGES={'https://'+host+'/*':PAGE for host in ['aistudio.google.com','chat.deepseek.com','chat.qwen.ai','www.kimi.com','arena.ai']}

@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[PAGES],indirect=True,ids=['six-modes'])
def test_reopen_all_sites_and_repair_legacy_qwen(local_studio,cold_tf6,monkeypatch):
    from python.substrate.llm.browser import sites
    from python.substrate.assistant.provider_conversation import permanent
    browser=local_studio; http,headers,state,_,(_,_,app)=cold_tf6
    refs=app.extensions['native_references']; store=refs.routes.chat_store
    for name in ('wait_driver','get_driver'): monkeypatch.setattr(refs.state,name,lambda:browser)
    active,other=browser.window_handles; browser.switch_to.window(active)
    def post(path,**data):return http.post(path,headers=headers,json=panel_body(app,state,**data)).get_json()
    for sid,prefix in [('qwen','/c/'),('aistudio','/prompts/'),('deepseek','/a/chat/s/'),('kimi','/chat/'),('arena','/c/'),('arena_battle','/c/')]:
        site=sites.get_site(sid); home=site['new_chat_url']; saved=urljoin(home,prefix+('battle' if sid=='arena_battle' else 'original'))
        created=post('/chats/new',site_id=sid); cid=created['current_id']
        assert browser.current_url==home and store.find_chat(str(state),cid)['url']==home
        store.update_chat(str(state),cid,url=saved)
        for role,txt in [('user','specific request'),('agent','**specific** `answer`\n```json\n{"action":"list_files"}\n```' if sid=='qwen' else 'specific answer')]:store.append_transcript(str(state),cid,role,txt)
        opened=post('/chats/open',id=cid)
        assert not opened['history_only'] and opened['site_id']==sid and browser.current_url==saved,(sid,opened)
        assert browser.current_window_handle==active
        if sid=='qwen':
            store.update_chat(str(state),cid,url=home);browser.get(home)
            assert not post('/chats/open',id=cid)['history_only']
            assert browser.current_url==store.find_chat(str(state),cid)['url']==saved
            wrong=store.create_chat(str(state),url=home);store.update_chat(str(state),wrong['id'],site_id=sid)
            for role,txt in [('user','specific request'),('agent','different answer')]:store.append_transcript(str(state),wrong['id'],role,txt)
            browser.get(home);assert post('/chats/open',id=wrong['id'])['history_only'] and browser.current_url==home
        if sid=='kimi':assert not permanent(site,urljoin(home,'/chat/provisional'))
    browser.switch_to.window(other);assert browser.current_url=='about:blank'
