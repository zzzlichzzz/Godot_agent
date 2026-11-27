"""Offline Studio document in Chrome; real composer, shortcut, URL and chat store."""
import base64
import json
import os
from pathlib import Path
from threading import Thread
from urllib.request import ProxyHandler, build_opener

import pytest

from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.transfer_t1.test_write import client


HOST = 'aistudio.google.com'
START = 'https://' + HOST + '/prompts/new_chat'
PAGE = '''<ms-prompt-box><textarea></textarea></ms-prompt-box><script>
const field=document.querySelector('textarea');window.submitted=0;
field.onkeydown=e=>{if(e.ctrlKey && e.key==='Enter'){
 e.preventDefault();submitted++;const user=document.createElement('div');user.dataset.turnRole='User';
 user.innerText=(window.mode==='unrelated'?'Other conversation: ':'')+field.value;document.body.append(user);
 history.pushState({},'',window.mode==='redirect'?'/library':'/prompts/actual_1');field.value='';
}};</script>'''


@pytest.fixture
def local_studio(tmp_path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    chrome, driver = (os.environ.get(k) for k in ('GODOT_AGENT_CHROME_PATH','GODOT_AGENT_CHROMEDRIVER_PATH'))
    if not all(p and Path(p).is_file() for p in (chrome, driver)): pytest.skip('Local Chrome + ChromeDriver required')
    opts=webdriver.ChromeOptions();opts.binary_location=chrome
    for opt in ('--headless=new','--no-first-run','--disable-sync','--disable-background-networking',
                '--disable-extensions','--proxy-server=127.0.0.1:1',f'--user-data-dir={tmp_path}/browser'):opts.add_argument(opt)
    with webdriver.Chrome(service=Service(driver),options=opts) as browser:
        browser.set_page_load_timeout(8)
        debugger=browser.capabilities['goog:chromeOptions']['debuggerAddress']
        # Only the temporary browser's two test tabs receive this local document.
        # The closed proxy prevents any fallback to a real account or network.
        from websocket import create_connection, WebSocketConnectionClosedException
        def intercept():
            opener=build_opener(ProxyHandler({}))
            with opener.open('http://'+debugger+'/json/list',timeout=3) as r: targets=json.load(r)
            target=next(t for t in targets if t['id']==browser.current_window_handle)
            ws=create_connection(target['webSocketDebuggerUrl'],suppress_origin=True,timeout=3)
            ws.send(json.dumps(dict(id=1,method='Fetch.enable',params={'patterns':[{'urlPattern':START}]})))
            assert json.loads(ws.recv())['id']==1
            ws.settimeout(None)
            def serve():
                i=1
                try:
                    while raw:=ws.recv():
                        event=json.loads(raw)
                        if event.get('method')!='Fetch.requestPaused': continue
                        i+=1
                        ws.send(json.dumps(dict(id=i,method='Fetch.fulfillRequest',params={
                            'requestId':event['params']['requestId'],'responseCode':200,
                            'responseHeaders':[{'name':'Content-Type','value':'text/html; charset=utf-8'}],
                            'body':base64.b64encode(PAGE.encode()).decode()})))
                except (WebSocketConnectionClosedException,OSError): pass
            Thread(target=serve,daemon=True).start()
        intercept()
        browser.switch_to.new_window('tab');intercept()
        yield browser


@pytest.mark.needs_live
def test_confirmed_studio_address_persists_only_in_selected_conversation(local_studio,cold_tf6,monkeypatch):
    http,headers,state,_,(_,_,app)=cold_tf6;refs=app.extensions['native_references'];browser=local_studio
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers.studio_delivery import StudioDelivery
    # This fixture supplies the page, not a model or an external CDP monitor.
    monkeypatch.setattr(StudioDelivery,'_ensure_monitor',lambda *_:None)
    monkeypatch.setattr(StudioDelivery,'_maybe_harden_background_tab',lambda *_:None)
    monkeypatch.setattr(StudioDelivery,'wait_for_new_answer',lambda *a,**k:{'text':'Local answer.','actionRaw':None})
    monkeypatch.setattr(refs.state,'wait_driver',lambda *a,**k:browser)
    monkeypatch.setattr(browser_backend,'wait_driver',lambda:browser)
    monkeypatch.setattr(app.extensions['godot_session'].gateway,'current_driver',lambda:browser)
    def post(path,**kw):return http.post(path,json=dict(panel_body(app,state,**kw),allow_addons=False,allow_self_edit=False),headers=headers)
    for mode in ('accepted','unrelated','redirect','wrong_tab'):
        browser.get(START);assert browser.execute_script('return window.submitted')==0,browser.page_source[-1400:]
        opened=post('/chats/new',site_id='aistudio');cid=opened.json['current_id']
        from selenium.webdriver.support.ui import WebDriverWait
        WebDriverWait(browser,5).until(lambda d:d.execute_script('return window.submitted===0'))
        browser.execute_script('window.mode=arguments[0]',mode);original=browser.current_window_handle
        if mode=='wrong_tab':
            browser.switch_to.window(next(h for h in browser.window_handles if h!=original));browser.get(START)
        response=post('/chat',chat_id=cid,prompt='literal [b] request');saved=refs.routes.chat_store.find_chat(str(state),cid)['url']
        if mode=='accepted':assert saved==START.replace('new_chat','actual_1') and response.status_code==200,response.json
        else:assert saved==START and response.status_code!=200,response.json
        if mode=='wrong_tab':
            assert browser.execute_script('return submitted')==0;browser.close();browser.switch_to.window(original)
        assert browser.execute_script('return submitted')==int(mode!='wrong_tab')
