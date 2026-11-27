"""Stored transcript, selected browser page and ability to write are independent."""
import pytest

from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


@pytest.mark.parametrize('scenario', ['placeholder', 'driver_down', 'redirect', 'missing_page', 'ready'])
def test_open_saved_studio(scenario, cold_tf6, monkeypatch):
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']; store = refs.routes.chat_store
    prefix = 'https://aistudio.google.com/prompts/'
    target = prefix + ('new_chat' if scenario == 'placeholder' else 'saved')
    rec = store.create_chat(str(state), url=target)
    cid = rec['id']; store.update_chat(str(state), cid, site_id='aistudio')
    store.append_transcript(str(state), cid, 'user', '[b]мой текст[/b]')
    visits = []; deliveries = []
    class Driver:
        current_url = target if scenario != 'redirect' else prefix + 'unrelated'
        current_window_handle = 'owned'
        def execute_script(self, js, *args):
            if js == 'return document.readyState': return 'complete'
            return scenario == 'ready'
    driver = Driver()
    def launch():
        visits.append('launch')
        if scenario == 'driver_down': raise RuntimeError('Порт браузера 9222 занят.')
        return driver
    monkeypatch.setattr(refs.state, 'wait_driver', launch)
    monkeypatch.setattr(refs.routes, '_navigate', lambda d, u: visits.append(u) or True)
    gw = app.extensions['godot_session'].gateway
    monkeypatch.setattr(gw, 'current_driver', lambda: driver)
    def post(path, **fields):
        return http.post(path, json=dict(panel_body(app, state, **fields), allow_addons=False, allow_self_edit=False), headers=headers)
    opened = post('/chats/open', id=cid)
    assert opened.status_code == 200 and opened.json['current_id'] == cid
    assert opened.json['transcript'][0]['text'] == '[b]мой текст[/b]'
    assert opened.json['history_only'] == (scenario != 'ready')
    if scenario == 'ready': return
    assert opened.json['warning'] and ('9222' in opened.json['warning'] if scenario == 'driver_down' else True)
    if scenario == 'placeholder': assert not visits
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    monkeypatch.setattr(BrowserBackend, 'send', lambda *a, **kw: deliveries.append('send') or {'text':'wrong'})
    assert not post('/chat/live_input', chat_id=cid, seq=10, text='draft').json['applied']
    assert post('/chat', chat_id=cid, prompt='не отправлять', ignore_site_mismatch=True).status_code != 200
    assert not deliveries and store.find_chat(str(state), cid)['url'] == target
