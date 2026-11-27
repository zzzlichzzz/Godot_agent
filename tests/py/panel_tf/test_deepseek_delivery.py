"""Exercise the real HTTP/DeepSeek send pipeline with an isolated composer."""
import json
import threading
from importlib import import_module

import pytest
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

from tests.py.browser.runtime_cases import Clock
from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


class Composer:
    current_url = 'https://chat.deepseek.com/'
    current_window_handle = 'agent'

    def __init__(self, native, mode):
        self.native, self.mode = native, mode
        self.value = ''
        self.insertions, self.submits, self.attachments = [], [], []
        self.accepted = []
        self.accept_after = 0
        self.window_handles = ['agent']

    @property
    def switch_to(self):
        return self

    def window(self, handle):
        assert handle == self.current_window_handle

    def paste(self, _driver, _el, text):
        if len(text) > 4000:
            self.attachments.append(text)
            return False
        self.value = text
        return True

    def execute_script(self, script, *args):
        if script == self.native.JS_SET_INPUT:
            self.insertions.append(args[1])
            self.value = args[1][:5] if self.mode == 'truncated' else args[1]
            return
        if 'querySelector' in script and '#chat-input' in script and not args:
            if self.mode == 'named' and 'textarea[name="search"]' not in script:
                return None
            return None if self.mode == 'no-field' else self
        if args and ('e.value' in script or 'arguments[0].value' in script):
            if self.accept_after:
                self.accept_after -= 1
                if self.accept_after == 0:
                    self.value = ''
                    if self.mode == 'route' and len(self.accepted) == 1:
                        self.current_url = 'https://chat.deepseek.com/a/chat/s/new-chat'
            return self.value
        if 'querySelector' in script and args:
            return bool(self.attachments)
        raise AssertionError('unexpected script')

    def send_keys(self, key):
        assert key == Keys.ENTER
        self.submits.append(self.value)
        if self.mode == 'stale':
            raise StaleElementReferenceException('uncertain dispatch')
        if self.mode == 'unconfirmed' or self.attachments:
            return
        self.accepted.append(self.value)
        self.accept_after = 4


def _body(app, state, **fields):
    return dict(panel_body(app, state, **fields), allow_addons=False, allow_self_edit=False)


def _install_composer(app, monkeypatch, mode, reply):
    # Replay tests restore sys.modules; a parent package can retain an older
    # module attribute. Patch the same qualified import the gateway actually uses.
    browser_backend = import_module('python.substrate.llm.browser.backends.browser_backend')
    from python.substrate.llm.parsers import deepseek_parser as native, parser_base
    composer = Composer(native, mode)
    if mode == 'old-files':
        composer.attachments.append('existing-draft.txt')
    if mode == 'wrong-chat':
        composer.current_url = 'https://chat.deepseek.com/a/chat/s/other'
    gateway = app.extensions['godot_session'].gateway
    driver = gateway.current_driver()
    driver.page = composer
    monkeypatch.setattr(browser_backend, 'wait_driver', lambda: driver)
    clock = Clock()
    monkeypatch.setattr(parser_base, 'time', clock)
    monkeypatch.setattr(native, 'time', clock)
    monkeypatch.setattr(parser_base.BaseSiteParser, '_maybe_harden_background_tab', lambda *a: None)
    monkeypatch.setattr(native.DeepSeekParser, 'is_generating', lambda *a: False)
    monkeypatch.setattr(native.DeepSeekParser, 'extract_answer_snapshot', lambda *a: {})
    monkeypatch.setattr(native.DeepSeekParser, 'count_answers', lambda *a: len(composer.accepted))
    monkeypatch.setattr(native.DeepSeekParser, 'answer_stream', lambda *a: '')
    monkeypatch.setattr(native.DeepSeekParser, 'wait_for_new_answer', lambda *a, **kw: reply(composer.accepted[-1]))
    monkeypatch.setattr(native.DeepSeekParser, 'insert_input_paste_like', lambda self, *a: composer.paste(*a))
    return composer


@pytest.mark.parametrize('mode', ['ok', 'named', 'route', 'truncated', 'stale', 'unconfirmed', 'old-files', 'wrong-chat', 'no-field'])
def test_deepseek_first_message_has_bounded_delivery(client, cold_tf6, monkeypatch, mode):
    http, headers, state, _, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    composer = _install_composer(app, monkeypatch, mode, lambda prompt: {
        'text': 'Привет!' if prompt.endswith('привет') else 'Служебное подтверждение.', 'actionRaw': None})
    response = http.post('/chat', json=_body(app, state, prompt='привет'), headers=headers)
    if mode in ('ok', 'named', 'route'):
        assert response.status_code == 200, response.get_json()
        assert response.json['response'] == 'Привет!'
        prompt, = composer.submits
        assert 'agent_action' in prompt and '===DONE===' in prompt and 'res://hero.gd' not in prompt
        assert prompt.endswith('привет')
        assert composer.submits == composer.accepted == composer.insertions
        if mode == 'route':
            assert app.extensions['godot_session'].gateway._selection()['url'] == composer.current_url
    else:
        if mode == 'wrong-chat':
            assert response.status_code == 409 and response.json['kind'] == 'conflict'
        else:
            assert response.status_code == 400 and 'DeepSeek' in response.json['error'], response.get_json()
        assert len(composer.submits) == (1 if mode in ('stale', 'unconfirmed') else 0)
        assert len(composer.insertions) == (0 if mode in ('old-files', 'wrong-chat', 'no-field') else 1)
        assert not composer.accepted
        if mode == 'no-field':
            # No text was touched; a composer appearing later can safely mirror again.
            composer.mode = 'named'
            mirror = http.post('/chat/live_input', json=_body(app, state, text='привет', seq=1), headers=headers)
            assert mirror.json == {'ok': True, 'applied': True, 'reason': ''}
            assert composer.value == 'привет' and not composer.submits
        elif mode in ('truncated', 'stale', 'unconfirmed'):
            mirror = http.post('/chat/live_input', json=_body(app, state, text='привет', seq=1), headers=headers)
            assert mirror.json == {'ok': True, 'applied': False, 'reason': 'send_unresolved'}
    assert composer.attachments == (['existing-draft.txt'] if mode == 'old-files' else [])


def test_new_deepseek_chat_user_journey(client, cold_tf6, monkeypatch):
    http, headers, state, project, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    cid = app.extensions['native_references'].state.STATE['current_chat_id']
    marker = 'RAW_SCENE_PROPERTY_DO_NOT_SEND'
    (project/'large.tscn').write_text(
        '[gd_scene format=3]\n\n[node name="LargeRoot" type="Label"]\n'
        f'text = "{marker * 8000}"\n', encoding='utf-8')
    before = physical(project)
    snapshot = {'schema_version': 1, 'scene': {'active': 'res://large.tscn', 'source': marker * 8000}}

    def answer(prompt):
        action = None
        if '\nРезультат чтения:\n' in prompt or prompt.startswith('Результат чтения:\n'):
            assert 'LargeRoot' in prompt and len(prompt) < 2500
            text = 'Корневой узел — LargeRoot.'
        elif prompt.endswith('привет'):
            text = 'Привет!'
        elif prompt.endswith('какой узел в открытой сцене?'):
            assert 'res://large.tscn' not in prompt
            action = {'action': 'list_scene', 'max_chars': 500}
            text = 'Посмотрю структуру.'
        elif prompt.endswith('создай скрипт'):
            action = {'action': 'create_file', 'path': 'res://journey.gd', 'content': 'extends Node\n'}
            text = 'Вот предпросмотр.'
        elif prompt.endswith('спасибо'):
            text = 'Пожалуйста!'
        else:
            text = 'Служебное подтверждение.'  # The old gateway sends a separate setup request.
        return {'text': text+'\n===DONE===', 'actionRaw': json.dumps(action) if action else None}

    composer = _install_composer(app, monkeypatch, 'route', answer)

    def post(path, **fields):
        response = http.post(path, json=_body(app, state, **fields), headers=headers)
        assert response.status_code == 200, response.json
        return response.json

    def send(text, count, editor_context=snapshot):
        start = len(composer.submits)
        result = post('/chat', prompt=text, chat_id=cid, editor_context=editor_context)
        assert len(composer.submits) - start == count
        return result

    assert post('/chat/live_input', text='привет', seq=1)['applied']
    assert composer.value == 'привет' and not composer.submits
    assert send('привет', 1)['response'] == 'Привет!'
    ask_scene = lambda: send('какой узел в открытой сцене?', 1)['read_request']
    ticket = ask_scene()
    def decide(ticket, approved):
        return post('/chat/read/decision', chat_id=cid, request_id=ticket['id'], approved=approved)
    assert ticket['action']['path'] == 'res://large.tscn'
    assert 'LargeRoot' not in ''.join(composer.submits)
    assert decide(ticket, False)['state'] == 'final' and len(composer.submits) == 2
    ticket = ask_scene()
    for wrong in ({'chat_id':'other'}, {'request_id':'expired'}, {'approved':'yes'}):
        body = dict(chat_id=cid, request_id=ticket['id'], approved=True); body.update(wrong)
        assert http.post('/chat/read/decision', json=_body(app,state,**body), headers=headers).status_code in (400,409)
    assert decide(ticket, True)['response'] == 'Корневой узел — LargeRoot.'
    assert http.post('/chat/read/decision', json=_body(app,state,chat_id=cid,request_id=ticket['id'],approved=True), headers=headers).status_code == 409
    assert 'agent_action' not in composer.submits[1]  # No repeated instructions for the same chat and map.
    assert physical(project) == before

    def preview():
        result = send('создай скрипт', 1, {})
        assert result['pending_confirmation'] and physical(project) == before
        plan = result['preview']
        return {'plan_id': plan['plan_id'], 'digest': plan['digest']}

    assert post('/chat/confirm', approved=False, **preview())['state'] == 'REJECTED'
    receipt = post('/chat/confirm', approved=True, **preview())
    assert receipt['state'] == 'COMMITTED' and (project/'journey.gd').read_bytes() == b'extends Node\n'
    assert send('спасибо', 1, {})['response'] == 'Пожалуйста!'
    assert composer.submits[-1] == 'спасибо'
    assert post('/chat/rollback', plan_id=receipt['plan_id'], entry_id=receipt['entry_id'])['state'] == 'ROLLED_BACK'
    assert send('спасибо', 1, {})['response'] == 'Пожалуйста!'
    assert composer.submits[-1] == 'спасибо'
    assert physical(project) == before
    assert all(marker not in prompt for prompt in composer.submits) and not composer.attachments


def test_mirror_does_not_use_a_stale_chat_or_touch_browser_during_turn(client, cold_tf6, monkeypatch):
    http, headers, state, _, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    from python.substrate.context.librarian_read import _LOCK
    from python.substrate.llm.parsers import deepseek_parser
    gateway = app.extensions['godot_session'].gateway
    stale = {'id': 'previous', 'kind': 'api'}
    gateway._record = stale
    composer = Composer(deepseek_parser, 'named')
    gateway.current_driver().page = composer
    assert http.post('/chat/live_input', json=_body(app, state, text='draft', seq=1), headers=headers).json['applied']
    assert gateway._record is stale
    responses = []

    def mirror():
        response = app.test_client().post('/chat/live_input', json=_body(app, state, text='late', seq=2), headers=headers)
        responses.append(response.json)

    with _LOCK:
        thread = threading.Thread(target=mirror)
        thread.start()
        thread.join(3)
        assert not thread.is_alive()
    assert responses[0]['reason'] == 'busy'
    assert composer.insertions == ['draft'] and not composer.submits
    composer.attachments.append('existing-draft.txt')
    blocked = http.post('/chat/live_input', json=_body(app, state, text='', seq=3), headers=headers)
    assert not blocked.json['applied'] and composer.insertions == ['draft']
    assert composer.attachments == ['existing-draft.txt']
