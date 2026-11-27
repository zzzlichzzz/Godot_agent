"""Conversation identity across a first reply, a new page and a second open."""
import pytest

from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


@pytest.mark.parametrize('site,path', [('qwen','/c/alpha'),('kimi','/chat/alpha'),
                                      ('arena','/c/alpha'),('arena_battle','/c/alpha')])
def test_send_saves_then_open_navigates_from_new_page(client,cold_tf6,monkeypatch,site,path):
    from urllib.parse import urljoin
    from python.substrate.llm.browser import sites
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    http,headers,state,_,app=_setup_browser_chat(client,cold_tf6,monkeypatch,site)
    gw=app.extensions['godot_session'].gateway; refs=app.extensions['native_references']
    driver=gw.current_driver(); home=sites.get_site(site)['new_chat_url']; saved=urljoin(home,path)
    cid=refs.state.STATE['current_chat_id']; store=refs.routes.chat_store
    def post(route,**args):
        return http.post(route,json=dict(panel_body(app,state,**args),allow_addons=False,allow_self_edit=False),headers=headers)
    def reply(self,prompt,**kw):
        assert kw['prefer_url']==home
        driver.page.current_url=saved
        return {'text':'Specific reply.','action':None}
    monkeypatch.setattr(BrowserBackend,'send',reply)
    assert post('/chat',chat_id=cid,prompt='Specific request.').status_code==200
    assert store.find_chat(str(state),cid)['url']==saved
    driver.page.current_url=home
    driver.page.execute_script=lambda js,*a:'complete' if js=='return document.readyState' else True
    opened=post('/chats/open',id=cid).json
    assert not opened['history_only'] and driver.current_url==saved and opened['site_id']==site
    driver.page.current_url=home
    assert not post('/chat/live_input',chat_id=cid,seq=81,text='not for this page').json['applied']
    store.update_chat(str(state),cid,url=home)
    driver.page.execute_script=lambda js,*a:[]
    assert post('/chats/open',id=cid).json['history_only']
