"""BUG-014 RED->GREEN: browser/API chat answers must complete without false 8-turn exhaustion."""
import json
from types import SimpleNamespace
import pytest
from python.channels.http.app import create_app
from python.runtime.bootstrap import build_agent, default_ports
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


def _setup_browser_chat(client, cold_tf6, monkeypatch, site_id='deepseek'):
    _, project, _ = client
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']
    dummy_driver = SimpleNamespace(current_url='https://chat.deepseek.com/', execute_script=lambda *a: None)
    monkeypatch.setattr(refs.state, 'wait_driver', lambda timeout=90.0: dummy_driver)
    monkeypatch.setattr(refs.routes, '_navigate', lambda driver, url: True)
    created = http.post('/chats/new', json=panel_body(app, state, kind='site', site_id=site_id), headers=headers)
    assert created.status_code == 200, created.get_json()
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: dummy_driver)
    return http, headers, state, project, app


def test_browser_plain_reply_without_done_marker_completes_first_turn(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers import parser_base

    calls = []

    def fake_send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        calls.append(prompt)
        # Simulate DeepSeek answering a short first prompt cleanly without ===DONE===.
        text = parser_base._strip_done_marker('Привет! Чем помочь по проекту?')
        return {'text': text, 'action': None}

    monkeypatch.setattr(browser_backend.BrowserBackend, 'send', fake_send)
    body = panel_body(app, state, prompt='привет', chat_id=app.extensions['native_references'].state.STATE['current_chat_id'])
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat', json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    assert resp.json['ok'] is True and 'Чем помочь' in resp.json['response']
    assert resp.json['turns_used'] == 1 and len(calls) == 1
    assert 'agent_action' in calls[0] and calls[0].endswith('привет')


def test_browser_write_action_with_stripped_fence_is_judged_and_prepared(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers import parser_base

    calls = []
    write_action = {'action': 'create_file', 'path': 'res://bug014_ok.gd', 'content': 'extends Node\n'}

    def fake_send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        calls.append(prompt)
        # Simulate deepseek_parser.JS_EXTRACT replacing ```agent_action``` with placeholder.
        text = parser_base._strip_done_marker('Создам скрипт.\n— агент предлагает действие (см. ниже) —')
        return {'text': text, 'action': write_action}

    monkeypatch.setattr(browser_backend.BrowserBackend, 'send', fake_send)
    before = physical(project)
    body = panel_body(app, state, prompt='создай bug014_ok.gd')
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat', json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    assert resp.json['pending_confirmation'] is True
    assert resp.json['turns_used'] == 1 and len(calls) == 1 and physical(project) == before


def test_browser_bbcode_wrapped_done_marker_completes_and_strips_wrapper(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers import parser_base

    calls = []

    def fake_send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        calls.append(prompt)
        text = parser_base._strip_done_marker('Ответ.\n[code]===DONE===[/code]')
        return {'text': text, 'action': None}

    monkeypatch.setattr(browser_backend.BrowserBackend, 'send', fake_send)
    body = panel_body(app, state, prompt='проверка')
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat', json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    assert resp.json['turns_used'] == 1 and len(calls) == 1
    assert '===DONE===' not in resp.json['response']


def test_browser_delivery_error_fails_fast_instead_of_eight_turn_loop(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends import browser_backend

    calls = []

    def fake_send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        calls.append(prompt)
        return {'text': '[Ошибка]: Не удалось подтвердить доставку сообщения в DeepSeek.', 'action': None}

    monkeypatch.setattr(browser_backend.BrowserBackend, 'send', fake_send)
    body = panel_body(app, state, prompt='привет')
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat', json=body, headers=headers)
    assert resp.status_code == 400
    assert 'исчерпан лимит шагов диалога' not in resp.json['error']
    assert 'Не удалось подтвердить доставку' in resp.json['error']
    assert len(calls) == 1


def test_api_stop_plain_reply_without_done_completes_while_length_retries(client, monkeypatch):
    _, project, state = client
    state.mkdir(exist_ok=True)
    tok = 'SYNTHETIC-API-STOP-TOKEN'
    (state / 'godot_agent_token.txt').write_text(tok, 'utf-8')
    from python.substrate.assistant.native_bindings import NativeBindings
    NativeBindings().register()
    import api_backend

    replies = [
        {'text': 'Краткий ответ без маркера.', 'raw': 'Краткий ответ без маркера.', 'action': None, 'finish_reason': 'stop'},
        {'text': 'Обрезано', 'raw': 'Обрезано', 'action': None, 'finish_reason': 'length'},
        {'text': 'Дописано.', 'raw': 'Дописано.\n===DONE===', 'action': None, 'finish_reason': 'stop'},
    ]
    monkeypatch.setattr(api_backend.ApiBackend, 'send', lambda self, prompt, **kw: replies.pop(0))
    app = create_app(project, state, native_routes=True)
    headers = {'X-Agent-Token': tok}
    r1 = app.test_client().post('/chat', json={'prompt': 'привет'}, headers=headers)
    assert r1.status_code == 200, r1.get_json()
    assert r1.json['turns_used'] == 1
    r2 = app.test_client().post('/chat', json={'prompt': 'длинный запрос'}, headers=headers)
    assert r2.status_code == 200, r2.get_json()
    assert r2.json['turns_used'] == 2


def test_chat_syncs_chat_id_and_editor_context_from_panel_body(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch, site_id='deepseek')
    refs = app.extensions['native_references']
    saved_cid = refs.state.STATE.pop('current_chat_id', None)
    assert saved_cid
    app.extensions['godot_session'].gateway._record = None
    from python.substrate.llm.browser.backends import browser_backend
    from python.substrate.llm.parsers import parser_base

    calls = []

    def fake_send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        calls.append((prompt, prefer_url))
        return {'text': parser_base._strip_done_marker('Готово.\n===DONE==='), 'action': None}

    monkeypatch.setattr(browser_backend.BrowserBackend, 'send', fake_send)
    body = panel_body(
        app,
        state,
        prompt='проверь контекст',
        chat_id=saved_cid,
        editor_context={'schema_version': 1, 'scene': {'active': 'res://main.tscn'}, 'script': {'open': ['res://main.gd']}},
    )
    body.update(allow_addons=False, allow_self_edit=False)
    resp = http.post('/chat', json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    (prompt, url), = calls
    assert 'deepseek' in (url or '')
    assert 'res://main.tscn' not in prompt and 'res://main.gd' not in prompt and prompt.endswith('проверь контекст')


def test_explicit_chat_does_not_override_next_request_or_fall_back_if_missing(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.api import chat_store
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend

    current = app.extensions['native_references'].state.STATE['current_chat_id']
    other = chat_store.create_chat(str(state), url='https://chat.deepseek.com/a/chat/other')['id']
    calls = []

    def send(self, prompt, **kwargs):
        calls.append(kwargs['prefer_url'])
        return {'text': 'Понял.', 'action': None}

    monkeypatch.setattr(BrowserBackend, 'send', send)
    base = dict(panel_body(app, state, prompt='привет'), allow_addons=False, allow_self_edit=False)
    assert http.post('/chat', json=dict(base, chat_id=other), headers=headers).status_code == 200
    assert calls and all(url.endswith('/other') for url in calls)
    calls.clear()
    missing = http.post('/chat', json=dict(base, chat_id='unknown-chat-id'), headers=headers)
    assert missing.status_code == 400 and missing.json['kind'] == 'not_found' and not calls
    assert http.post('/chat', json=base, headers=headers).status_code == 200
    assert calls and not any(url.endswith('/other') for url in calls)
    assert app.extensions['native_references'].state.STATE['current_chat_id'] == current


@pytest.mark.parametrize('mode', ['marker_in_prose', 'conflicting_action', 'unfinished_fence'])
def test_browser_only_uses_terminal_marker_and_matching_complete_action(client, cold_tf6, monkeypatch, mode):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    from python.substrate.llm.parsers import parser_base

    calls = []
    prose = 'Строка ===DONE=== встречается в тексте, не удаляй её.'
    proposed = {'action': 'create_file', 'path': 'res://other.gd', 'content': 'extends Node\n'}
    checked = dict(proposed, path='res://checked.gd')

    def send(self, prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 2:
            return {'text': 'Готово.', 'action': None}
        if mode == 'marker_in_prose':
            return {'text': prose, 'action': None}
        raw = '```agent_action\n' + json.dumps(checked)
        if mode == 'conflicting_action':
            raw += '\n```'
        parser_base._strip_done_marker(raw)
        return {'text': 'Предлагаю изменение.', 'action': proposed}

    monkeypatch.setattr(BrowserBackend, 'send', send)
    before = physical(project)
    body = dict(panel_body(app, state, prompt='проверь'), allow_addons=False, allow_self_edit=False)
    reply = http.post('/chat', json=body, headers=headers)
    assert reply.status_code == 200 and not reply.json['pending_confirmation']
    assert physical(project) == before
    if mode == 'marker_in_prose':
        assert reply.json['response'] == prose and reply.json['turns_used'] == 1
    else:
        assert reply.json['response'] == 'Готово.' and reply.json['turns_used'] == 2
