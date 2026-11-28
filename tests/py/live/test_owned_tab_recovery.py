"""Native panel navigation after the user closes the monitored tab or the entire window."""
import os
from pathlib import Path
from uuid import uuid4

import pytest

from .test_browser_composers import ARENA_SEND
from .test_studio_conversation import serve_document
from tests.py.transfer_t1.conftest import isolated_chat_native_generation, extra_aliases


@pytest.fixture
def binaries():
    paths={k:os.environ.get(k) for k in ('GODOT_AGENT_CHROME_PATH','GODOT_AGENT_CHROMEDRIVER_PATH')}
    if not all(p and Path(p).is_file() for p in paths.values()): pytest.skip('Local Chrome + ChromeDriver required')
    return paths


@pytest.mark.needs_live
def test_new_chat_after_closing_monitored_tab_then_last_window(binaries,tmp_path,monkeypatch):
    from python.channels.http.app import create_app
    project=tmp_path/'project';project.mkdir();(project/'project.godot').write_text('config_version=5\n')
    state=tmp_path/'state';state.mkdir();token='SYNTHETIC-OWNED-TAB-TEST'
    (state/'godot_agent_token.txt').write_text(token);headers={'X-Agent-Token':token}
    app=create_app(project,state); http=app.test_client(); gw=app.extensions['godot_session'].gateway
    from python.substrate.llm.browser import facade, sites
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    from python.substrate.llm.parsers.arena_parser import ArenaParser
    routes=app.extensions['native_references'].routes; navigate=routes._navigate
    for k,v in binaries.items():monkeypatch.setenv(k,v)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path)); base=facade.ReadOnlyBrowser
    class IsolatedBrowser(base):
        def __init__(self,*args):
            profile=tmp_path/('Godot_AI_Profile_B1_'+uuid4().hex);profile.mkdir()
            super().__init__(*args,live_profile=profile)
    monkeypatch.setattr(facade,'ReadOnlyBrowser',IsolatedBrowser)
    def local(driver,url):
        serve_document(driver,{'https://arena.ai/*':ARENA_SEND}); return navigate(driver,url)
    monkeypatch.setattr(routes,'_navigate',local)
    site=sites.get_site('arena');url=site['new_chat_url']
    def new():
        response=http.post('/chats/new',json={'site_id':'arena'},headers=headers)
        assert response.status_code==200,response.json
        d=gw.current_driver(); p=ArenaDelivery(site,d,url); mon=p._ensure_monitor(d)
        assert p.find_input(d) and mon and mon._arena_target_id.lower()==d.current_window_handle.lower()
        return d,response.json['current_id']
    try:
        d,first=new(); first_tab=d.current_window_handle
        d.switch_to.new_window('tab'); other=d.current_window_handle;d.execute_script('window.untouched=true')
        d.switch_to.window(first_tab);d.close()
        assert http.post('/browser/page_status',json={'chat_id':first},headers=headers).json=={'ready':False}
        assert http.post('/browser/reload',json={'chat_id':first},headers=headers).status_code==409
        assert d.window_handles==[other]
        same,second=new();assert same is d and d.current_window_handle not in (first_tab,other) and first!=second
        second_tab=d.current_window_handle;d.switch_to.window(other)
        assert d.current_url=='about:blank' and d.execute_script('return window.untouched')
        d.close();d.switch_to.window(second_tab);d.close()
        fresh,third=new();assert third not in (first,second) and fresh.current_window_handle not in (first_tab,other,second_tab)
    finally:
        if ArenaParser._monitor:
            ArenaParser._monitor._cdp.close();ArenaParser._monitor=None
        gw.close()
