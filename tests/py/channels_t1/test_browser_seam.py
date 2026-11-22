"""Native HTTP sees only its own live ReadOnlyBrowser; no live browser."""
from types import SimpleNamespace
import pytest
from python.channels.http.app import create_app
from tests.py.transfer_t1.test_write import client,physical

class Driver:
    current_url='https://synthetic.invalid/owned-session'
    def execute_script(self,script):
        assert script=='return document.readyState';return 'complete'

def owned():
    from python.substrate.llm.browser.facade import ReadOnlyBrowser
    browser=ReadOnlyBrowser.__new__(ReadOnlyBrowser)
    browser._owned=True;browser._process=SimpleNamespace(poll=lambda:None);browser._driver=Driver()
    return browser

@pytest.fixture
def native_app(client,monkeypatch):
    from python.substrate.llm import runtime_owner
    _,root,state=client;state.mkdir(exist_ok=True)
    (state/'godot_agent_token.txt').write_text('SYNTHETIC-BROWSER-SEAM-TOKEN',encoding='utf-8')
    monkeypatch.setitem(runtime_owner._holder,'owner',None);monkeypatch.setitem(runtime_owner._holder,'driver_error',None)
    app=create_app(root,state,native_routes=True)
    return app,root,{'X-Agent-Token':'SYNTHETIC-BROWSER-SEAM-TOKEN'},runtime_owner

def test_native_status_observes_its_typed_live_owned_browser(native_app):
    app,root,headers,runtime_owner=native_app;before=physical(root);browser=owned()
    app.extensions['godot_session'].gateway._owned_browser=browser;runtime_owner.bind_owner(browser)
    try:
        assert app.extensions['native_references'].state.get_driver() is browser._driver
        response=app.test_client().post('/browser/status',json={},headers=headers)
        assert response.status_code==200
        assert response.get_json()==dict(ready=True,state='complete',url=browser._driver.current_url) and physical(root)==before
    finally:runtime_owner.release_owner(browser)

def test_session_without_browser_does_not_adopt_a_global_owned_browser(native_app):
    app,root,headers,runtime_owner=native_app;before=physical(root);foreign=owned();runtime_owner.bind_owner(foreign)
    try:
        assert app.extensions['native_references'].state.get_driver() is None
        response=app.test_client().post('/browser/status',json={},headers=headers)
        assert response.status_code==200 and response.get_json()==dict(ready=False,state='idle',url='')
        assert app.extensions['godot_session'].gateway._owned_browser is None and physical(root)==before
    finally:runtime_owner.release_owner(foreign)

def test_native_wait_demands_only_its_session_owned_facade(native_app,monkeypatch):
    app,root,_,runtime_owner=native_app;before=physical(root);browser=owned();calls=[]
    gateway=app.extensions['godot_session'].gateway
    def start(timeout=1):
        assert timeout==.01;calls.append('owned-start');gateway._owned_browser=browser;runtime_owner.bind_owner(browser)
        return browser._driver
    monkeypatch.setattr(gateway,'_ensure_browser',start)
    try:
        assert app.extensions['native_references'].state.wait_driver(timeout=.01) is browser._driver
        assert calls==['owned-start'] and physical(root)==before
    finally:
        if calls:runtime_owner.release_owner(browser)
