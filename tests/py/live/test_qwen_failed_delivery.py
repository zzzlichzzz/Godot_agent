"""Real Chrome composer, delayed provider notice, explicit retry, and a quoted notice."""
from urllib.parse import quote

import pytest
from .test_studio_conversation import local_studio
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.panel_tf.test_qwen_turn import setup
from tests.py.transfer_t1.test_write import client


PAGE = '''<textarea class="message-input-textarea"></textarea>
<div class="qwen-chat-message-assistant"><div class="error" id="original"></div></div>
<button role="button" aria-label="Regenerate" onclick="regens++">Regenerate</button>
<script>
const msg='Oops! There was an issue connecting to Qwen3.7-Plus.\\nInvalid input chat parent_id old-id is not exist.';
original.innerText=msg;
window.sends=0; window.regens=0;
document.querySelector('textarea').onkeydown=e=>{
 if(e.key!=='Enter')return; e.preventDefault();e.target.value=''; sends++;
 const turn=document.createElement('div'); turn.className='qwen-chat-message-assistant'; document.body.append(turn);
 const quote=document.createElement('div'); quote.className='response-message-content'; turn.append(quote);
 quote.innerHTML='<div class="qwen-markdown"><span role="alert"></span></div>'; quote.firstChild.firstChild.innerText=msg;
 if(sends===1)setTimeout(()=>{const err=document.createElement('div');err.className='response-error';err.innerText=msg;turn.append(err)},900);
 else {quote.firstChild.append('\\n===DONE===');turn.insertAdjacentHTML('beforeend','<div class="response-message-footer"><div class="qwen-chat-package-comp-new-action-control-icons"></div></div>');}
};</script>'''


@pytest.mark.needs_live
@pytest.mark.parametrize('notice',['parent','Network error. Please try again.'])
def test_failed_delivery_then_explicit_retry(local_studio, client, cold_tf6, monkeypatch,notice):
    _, cid, post = setup(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers.qwen_delivery import QwenDelivery
    browser = local_studio
    page=PAGE if notice=='parent' else PAGE.replace(PAGE.split("const msg='")[1].split("';")[0],notice)
    browser.get('data:text/html;charset=utf-8,'+quote(page))
    # Isolate the test tab, clipboard and network; keep actual delivery, waiting and extraction.
    monkeypatch.setattr(browser_backend,'wait_driver',lambda:browser)
    monkeypatch.setattr(QwenDelivery,'switch_to_site_window',lambda *a,**k:None)
    monkeypatch.setattr(QwenDelivery,'_maybe_harden_background_tab',lambda *_:None)
    monkeypatch.setattr(QwenDelivery,'_ensure_monitor',lambda *_:None)
    monkeypatch.setattr(QwenDelivery,'insert_input_for_send',QwenDelivery.insert_input)
    r = post('/chat', chat_id=cid, prompt='one question')
    assert r.status_code!=200 and r.json.get('details')=={'retry_prompt':True}, r.json
    assert browser.execute_script('return [sends,regens]')==[1,0]
    r = post('/chat', chat_id=cid, prompt='one question')
    assert r.status_code==200 and ('is not exist' if notice=='parent' else notice) in r.json['response'],r.json
    assert browser.execute_script('return [sends,regens]')==[2,0]


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://chat.qwen.ai/*':'<textarea></textarea>'}],indirect=True)
def test_completion_fails_before_headers_on_its_own_tab(local_studio):
    from selenium.webdriver.support.ui import WebDriverWait
    from python.substrate.llm.browser.qwen_request_watch import QwenRequestWatch
    browser=local_studio; url='https://chat.qwen.ai/'; endpoint='/api/v2/chat/completions'
    tab=browser.current_window_handle; other=next(h for h in browser.window_handles if h!=tab)
    def fail(path):
        browser.execute_async_script("fetch(arguments[0],{method:'POST'}).catch(()=>{}).then(arguments[1]);",path)
    browser.get(url);fail(endpoint)
    watch=QwenRequestWatch.attach(browser); assert watch is not None
    try:
        browser.switch_to.window(other);browser.get(url);fail(endpoint)
        browser.switch_to.window(tab);fail('/assets/other');assert watch.failure is None
        fail(endpoint+'?chat_id=fixture')
        assert WebDriverWait(browser,3).until(lambda _:watch.failure).startswith('net::ERR_')
    finally: watch.cdp.close()
