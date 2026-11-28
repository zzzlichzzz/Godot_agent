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
PAGES={'https://'+host+'/*':PAGE for host in ['aistudio.google.com','chat.deepseek.com','chat.qwen.ai','www.kimi.ai','www.kimi.com','arena.ai']}


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[PAGES],indirect=True)
def test_reopen_warm_arena_conversation_without_a_second_get(local_studio,cold_tf6,monkeypatch):
    from .test_browser_composers import bind
    browser=local_studio; post=bind(browser,cold_tf6,monkeypatch)
    cid=post('/chats/new',site_id='arena')['current_id']; url='https://arena.ai/c/already-open'
    http,headers,state,_,(_,_,app)=cold_tf6;store=app.extensions['native_references'].routes.chat_store
    store.update_chat(str(state),cid,url=url,primed=True)
    # The provider assigned this permanent route in-page. A fresh GET requires login again.
    browser.execute_script("history.replaceState({},'',arguments[0]);document.querySelector('textarea').value='unsent'",url)
    browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',{'source':"if(location.pathname.startsWith('/c/'))location.replace('/login')"})
    opened=post('/chats/open',id=cid)
    assert not opened['history_only'],opened.get('warning')
    assert browser.current_url==url and browser.execute_script('return document.querySelector("textarea").value')=='unsent'

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


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[PAGES],indirect=True)
def test_kimi_global_launch_first_reply_and_legacy_chat(local_studio,cold_tf6,monkeypatch):
    from python.substrate.assistant.provider_conversation import FirstReply
    from python.substrate.assistant.saved_page import site_for_record
    from python.substrate.llm.browser import sites
    from python.kernel.errors import AppError
    browser=local_studio; http,headers,state,_,(_,_,app)=cold_tf6
    refs=app.extensions['native_references']; store=refs.routes.chat_store
    monkeypatch.setattr(refs.state,'wait_driver',lambda:browser)
    def post(path,**kw):return http.post(path,headers=headers,json=panel_body(app,state,**kw)).get_json()
    home='https://www.kimi.ai/?chat_enter_method=new_chat'; old='https://www.kimi.com/chat/original'
    assert next(s for s in post('/sites/list')['sites'] if s['id']=='kimi')['new_chat_url']==home
    other,active=browser.window_handles
    browser.switch_to.window(other);browser.get(old);browser.switch_to.window(active)
    cid=post('/chats/new',site_id='kimi')['current_id']; rec=store.find_chat(str(state),cid)
    assert rec['url']==browser.current_url==home and sites.detect_site(home)['id']=='kimi'
    site=site_for_record(rec); first=FirstReply(browser,site,home)
    browser.execute_script("history.replaceState({},'', '/chat/provisional'); document.body.insertAdjacentHTML('beforeend','<p class=user-message>hello</p>'); setTimeout(()=>history.replaceState({},'', '/chat/global_1'),350)")
    assert first.confirmed(browser,'hello',accepted=True)=='https://www.kimi.ai/chat/global_1'
    assert browser.current_window_handle==active
    store.update_chat(str(state),cid,url=old);opened=post('/chats/open',id=cid)
    assert not opened['history_only'] and browser.current_url==old
    browser.get('https://www.kimi.ai/chat/original')
    with pytest.raises(AppError):refs.routes.selected_page.require(store.find_chat(str(state),cid),browser)
    browser.switch_to.window(other);assert browser.current_url==old


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[PAGES],indirect=True)
def test_kimi_delivery_uses_selected_composer_and_stream(local_studio,monkeypatch):
    from python.substrate.assistant.native_bindings import NativeBindings
    NativeBindings().register()
    from python.kernel.errors import AppError
    from python.substrate.llm.browser import cdp_ws, sites
    from python.substrate.llm.parsers.kimi_delivery import KimiDelivery
    browser=local_studio; other,active=browser.window_handles; site=sites.get_site('kimi'); home=site['new_chat_url']
    browser.switch_to.window(other);browser.get('https://www.kimi.com/chat/original')
    browser.switch_to.window(active);browser.get(home);parser=KimiDelivery(site,browser)
    port=int(browser.capabilities['goog:chromeOptions']['debuggerAddress'].split(':')[1])
    monkeypatch.setattr(cdp_ws,'find_page_ws_url_for_target',lambda h,lookup=cdp_ws.find_page_ws_url_for_target:lookup(h,port=port))
    monitor=parser._ensure_monitor(browser)
    try:
        assert monitor._cdp.send_command('Target.getTargetInfo')['targetInfo']['targetId']==active
        assert parser.mirror_input(browser,'hello',prefer_url=home)
        assert parser.find_input(browser).text=='hello'
        browser.switch_to.window(other)
        with pytest.raises(AppError):parser.mirror_input(browser,'wrong',prefer_url=home)
        assert browser.current_window_handle==other and not parser.find_input(browser).text
    finally:monitor._cdp.close()
