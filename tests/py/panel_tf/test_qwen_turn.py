"""Reported Qwen reads and navigation while the browser owns the native lock."""
import threading
import time

import pytest

from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


def setup(client, cold_tf6, monkeypatch):
    http, headers, state, _, app = _setup_browser_chat(client, cold_tf6, monkeypatch, 'qwen')
    cid = app.extensions['native_references'].state.STATE['current_chat_id']
    def post(path, **args):
        return app.test_client().post(path, headers=headers, json=dict(panel_body(app, state, **args), allow_addons=False, allow_self_edit=False))
    return app, cid, post


@pytest.mark.parametrize('name,params,expected', [
    ('list_files', {'subdir':'', 'max_entries':2}, 'res://hero.gd'),
    ('list_files', {'dir':'.', 'max_entries':2}, 'res://hero.gd'),
    ('find_symbol_usages', {'kind':'function', 'old_name':'hit', 'declaration_path':'res://hero.gd'}, '"proven_count":1'),
    ('analyze_rename', {'kind':'function', 'old_name':'hit', 'new_name':'strike', 'declaration_path':'res://hero.gd'}, '"risks":[]'),
])
def test_wrapped_read_approval_matches_execution(client, cold_tf6, monkeypatch, name, params, expected):
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    app, cid, post = setup(client, cold_tf6, monkeypatch)
    calls = []
    def send(self, prompt, **kw):
        calls.append(prompt)
        action = {'action':name,'arguments':params} if len(calls)==1 else None
        return {'action':action, 'text':'ok'}
    monkeypatch.setattr(BrowserBackend, 'send', send)
    r = post('/chat', chat_id=cid, prompt='list'); ticket = r.json['read_request']
    assert ticket['action'] == {'action':name, **params} and len(calls)==1
    assert post('/chat', chat_id=cid, prompt='invalid id', turn_id='oops').status_code==400
    r = post('/chat/read/decision', chat_id=cid, request_id=ticket['id'], approved=True)
    assert r.status_code==200 and len(calls)==2 and expected in calls[-1] and 'invalid_input' not in calls[-1]


@pytest.mark.parametrize('action', [
    {'action':'read_file', 'path':'res://one.gd', 'arguments':{'path':'res://two.gd'}},
    {'action':'read_file', 'arguments':{'action':'create_file', 'path':'res://two.gd'}},
])
def test_conflicting_wrapper_never_issues_a_read_ticket(client, cold_tf6, monkeypatch, action):
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    app, cid, post = setup(client, cold_tf6, monkeypatch)
    monkeypatch.setattr(BrowserBackend, 'send', lambda *a,**kw: {'action':action, 'text':'read?'})
    r = post('/chat', chat_id=cid, prompt='read')
    assert r.status_code==400 and r.json['kind']=='invalid_input'
    session = app.extensions['godot_session']
    assert session.ticket is None and session.pending is None


def test_stop_is_bound_to_one_request_even_when_browser_returns_late(client, cold_tf6, monkeypatch):
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    app, cid, post = setup(client, cold_tf6, monkeypatch)
    entered = threading.Event(); responses = []; calls = []
    def send(self, prompt, cancel_cb, **kw):
        calls.append(prompt)
        if len(calls)==1:
            entered.set(); deadline=time.monotonic()+5
            while not cancel_cb() and time.monotonic()<deadline: time.sleep(.01)
            assert cancel_cb()
            return {'action':{'action':'list_files'}, 'text':'late read'}
        assert not cancel_cb()
        return {'action':None, 'text':'new reply'}
    monkeypatch.setattr(BrowserBackend,'send',send)
    old, new = '1'*32, '2'*32
    assert post('/chat/stop',turn_id='0'*32).json['ok']
    assert post('/chat', chat_id=cid, prompt='never sent',turn_id='0'*32).json['stopped'] and not calls
    t=threading.Thread(target=lambda:responses.append(post('/chat',chat_id=cid,prompt='wait',turn_id=old)))
    t.start(); assert entered.wait(3)
    assert post('/chat/stop',turn_id=None).status_code==400
    assert post('/chat/stop',turn_id=old).json['ok']; t.join(3); assert not t.is_alive()
    assert responses[0].status_code!=200 and app.extensions['godot_session'].ticket is None
    assert post('/sites/list').status_code==200
    new_cid=post('/chats/new',kind='site',site_id='qwen').json['current_id']; assert new_cid!=cid
    assert not post('/chat/stop',turn_id=old).json['ok']
    assert post('/chat',chat_id=new_cid,prompt='second',turn_id=new).json['response']=='new reply'
    assert len(calls)==2
