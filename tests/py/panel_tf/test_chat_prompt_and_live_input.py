"""ADR-0093: Godot panel /chat prompt key, /chat/progress active flag, live_input site sync, and scene UIDs."""
from pathlib import Path
import re
import threading
import pytest
from python.channels.http.app import create_app
from python.runtime.bootstrap import build_agent, default_ports
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_turn import OfflineGateway, packet
from tests.py.transfer_t1.test_write import client, physical

ROOT = Path(__file__).resolve().parents[3]
SCENE_NAMES = (
    'UserMessageCard.tscn', 'AgentMessageCard.tscn', 'DiffPreviewCard.tscn',
    'PlanChecklistCard.tscn', 'PlanStepItem.tscn', 'ToolCallCard.tscn', 'agent_panel.tscn',
)


def _http_with_gateway(client_tuple, packets):
    _, project, state = client_tuple
    state.mkdir(exist_ok=True)
    tok = 'SYNTHETIC-PANEL-CHAT-TOKEN'
    (state / 'godot_agent_token.txt').write_text(tok, 'utf-8')
    ports = default_ports(project, 'cli', state_dir=state)
    gw = OfflineGateway(packets)
    ports['chat_gateway'] = gw
    agent = build_agent(project, profile='cli', state_dir=state, ports=ports)
    app = create_app(project, state, agent=agent, native_routes=True)
    return app.test_client(), app, project, state, gw, {'X-Agent-Token': tok}


def test_chat_accepts_godot_panel_prompt_key_and_rejects_empty(client):
    packets = [
        packet(dict(action='create_file', path='res://ok.gd', content='extends Node\n'), text='Создам файл.'),
        packet(None, text='Обычный текст.', done=True),
    ]
    http, app, project, state, gw, headers = _http_with_gateway(client, packets)
    before = physical(project)
    base = panel_body(app, state)
    base.update(allow_addons=False, allow_self_edit=False)
    r1 = http.post('/chat', json={**base, 'prompt': 'Создай файл ok.gd', 'chat_id': 'c1'}, headers=headers)
    assert r1.status_code == 200, r1.get_json()
    assert r1.json['pending_confirmation'] is True and physical(project) == before
    assert gw.sent[0][0] == 'Создай файл ok.gd'
    assert http.post('/chat/confirm', json={'approved': False}, headers=headers).status_code == 200
    r2 = http.post('/chat', json={**base, 'message': 'От message', 'prompt': 'От prompt'}, headers=headers)
    assert r2.status_code == 200 and gw.sent[1][0] == 'От message'
    assert http.post('/chat', json={**base, 'prompt': ''}, headers=headers).status_code == 400


def test_chat_progress_reports_active_while_turn_busy(client):
    entered, release = threading.Event(), threading.Event()
    observed = {}

    class BlockingGateway(OfflineGateway):
        def send(self, prompt, **kwargs):
            entered.set()
            assert release.wait(5.0)
            return super().send(prompt, **kwargs)

    _, project, state = client
    state.mkdir(exist_ok=True)
    tok = 'SYNTHETIC-PROGRESS-TOKEN'
    (state / 'godot_agent_token.txt').write_text(tok, 'utf-8')
    ports = default_ports(project, 'cli', state_dir=state)
    ports['chat_gateway'] = BlockingGateway([packet(None, text='Done.', done=True)])
    agent = build_agent(project, profile='cli', state_dir=state, ports=ports)
    app = create_app(project, state, agent=agent, native_routes=True)
    headers = {'X-Agent-Token': tok}
    assert app.test_client().get('/chat/progress', headers=headers).json['active'] is False

    def run_chat():
        observed['chat'] = app.test_client().post('/chat', json={'prompt': 'wait'}, headers=headers)

    t = threading.Thread(target=run_chat)
    t.start()
    try:
        assert entered.wait(5.0)
        prog = app.test_client().get('/chat/progress', headers=headers)
        assert prog.status_code == 200
        assert prog.json['busy'] is True and prog.json['active'] is True
    finally:
        release.set()
        t.join(timeout=5.0)
    assert observed['chat'].status_code == 200
    assert app.test_client().get('/chat/progress', headers=headers).json['active'] is False


def test_live_input_uses_selected_deepseek_site_with_fail_closed_policy(cold_tf6, monkeypatch):
    from types import SimpleNamespace
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']
    dummy_driver = SimpleNamespace(current_url='https://chat.deepseek.com/', execute_script=lambda *a: None)
    monkeypatch.setattr(refs.state, 'wait_driver', lambda timeout=90.0: dummy_driver)
    monkeypatch.setattr(refs.routes, '_navigate', lambda driver, url: True)
    created = http.post('/chats/new', json=panel_body(app, state, kind='site', site_id='deepseek'), headers=headers)
    assert created.status_code == 200 and created.json['site_id'] == 'deepseek'
    assert app.extensions['godot_session'].gateway._record is None

    seen = {}
    from python.substrate.llm.parsers import deepseek_parser
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: dummy_driver)
    monkeypatch.setattr(
        deepseek_parser.PARSER,
        'mirror_input',
        lambda driver, text, prefer_url=None: (
            seen.update(driver=driver, text=text, url=prefer_url) or True
        ),
    )
    body = panel_body(app, state, text='hello deepseek', seq=7)
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat/live_input', json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    assert resp.json == {'ok': True, 'applied': True, 'reason': ''}
    assert seen['driver'] is dummy_driver and seen['text'] == 'hello deepseek'
    assert 'deepseek' in (seen['url'] or '')


def test_all_native_scenes_match_script_uid_sidecars():
    mismatches = []
    for name in SCENE_NAMES:
        text = (ROOT / 'editor/native' / name).read_text('utf-8')
        for m in re.finditer(r'uid="(uid://[^"]+)"\s+path="res://addons/godot_agent/([^"]+)"', text):
            uid, rel = m.group(1), m.group(2)
            actual = (ROOT / f'{rel}.uid').read_text('utf-8').strip()
            if uid != actual:
                mismatches.append((name, rel, uid, actual))
    assert mismatches == []


def test_d116_source_input_revisions_prove_preimage_and_refuse_drift():
    from tests.py.panel_tf.source_inputs import D116_REVISIONS, revised_d116_fact
    for path, (old_b, old_sha, new_b, new_sha, _) in D116_REVISIONS.items():
        current = (ROOT / path).read_bytes()
        updated = revised_d116_fact({'path': path, 'bytes': old_b, 'sha256': old_sha}, current)
        assert updated['bytes'] == new_b and updated['sha256'] == new_sha
        with pytest.raises(ValueError):
            revised_d116_fact({'path': path, 'bytes': old_b, 'sha256': old_sha}, current + b'\n')
        with pytest.raises(ValueError):
            revised_d116_fact({'path': path + '.other', 'bytes': old_b, 'sha256': old_sha}, current)
