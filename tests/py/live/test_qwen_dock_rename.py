"""Observe the commit card in Godot while its distinct provider request is in flight."""
import json
import time

import pytest
from flask import request

from .test_qwen_dock_turn import dock_http
from .test_ui_bugs_live import isolated_native_project
from tests.py.panel_tf.rename_example import ACTION, write_sources


PROBE='''@tool
extends EditorPlugin
func _enter_tree(): call_deferred("run")
func until(check: Callable) -> bool:
    var end := Time.get_ticks_msec()+14000
    while not check.call() and Time.get_ticks_msec()<end:
        await get_tree().create_timer(0.04).timeout
    return check.call()
func run():
    var p = Engine.get_meta("_godot_agent_entry_owner")._dock
    if not await until(func(): return p._link and p._start_screen and not p._link.is_inflight()):
        get_tree().quit(2); return
    p._request_chats("new", {"site_id":"qwen"})
    if not await until(func(): return p._current_chat_id!="" and p.get_node("VBoxContainer").visible):
        get_tree().quit(3); return
    p.input_field.text="Test rename_symbol"
    p.send_button.pressed.emit()
    if not await until(func(): return p._has_pending_action() and not p.confirm_button.disabled):
        get_tree().quit(4); return
    p.confirm_button.pressed.emit()
    var view = p._view._chat_container
    if not await until(func(): return p._is_network_busy and p._pending_request_kind=="rename_report" and view.get_children().any(func(c): return c is AgentMessageCard and c.rollback_entry_id!="" and c.rollback_btn.visible)):
        get_tree().quit(5); return
    var ack := FileAccess.open("user://receipt-visible",FileAccess.WRITE)
    ack.close()
    if not await until(func(): return not p._is_network_busy and view.get_children().any(func(c): return (c is Label and c.text==p._t("rename_report_missing")) or (c is AgentMessageCard and c._full_text=="Dock summary" and c.rollback_entry_id==""))):
        get_tree().quit(6); return
    get_tree().quit(7 if p._has_pending_action() else 0)
'''


@pytest.mark.needs_live
@pytest.mark.parametrize('reply',['summary','provider-error','repeated-action'])
def test_commit_precedes_readonly_followup(dock_http,monkeypatch,reply):
    app,project,state,driver,run_probe=dock_http; before=write_sources(project)
    with app.extensions['native_references'].scope():
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    calls=[]; events=[]
    def send(self,prompt,**kw):
        calls.append(prompt)
        if len(calls)==1:
            driver.current_url='https://chat.qwen.ai/c/dock-rename'
            return dict(text='Предлагаю переименование.',action=ACTION)
        deadline=time.monotonic()+5
        while not (state/'receipt-visible').exists() and time.monotonic()<deadline: time.sleep(.03)
        if reply=='provider-error': raise RuntimeError('Synthetic provider error')
        if reply=='repeated-action': return dict(text='Повторяю.',action=ACTION)
        return dict(text='Dock summary',action=None)
    monkeypatch.setattr(BrowserBackend,'send',send)
    @app.after_request
    def observe(response):
        if request.path in ('/chat','/chat/confirm_action','/chat/rename/report'):
            events.append((request.path,response.json))
        return response
    run_probe(PROBE)
    assert [p for p,_ in events]==['/chat','/chat/confirm_action','/chat/rename/report']
    assert len(calls)==2 and json.loads(calls[1].splitlines()[-1])['state']=='COMMITTED'
    assert events[1][1]['state']=='COMMITTED' and events[1][1]['history_entry_id']
    result=events[2][1]
    assert (result.get('answer')=='Dock summary' if reply=='summary' else bool(result.get('report_warning')))
    assert all(p.read_bytes()==data.replace(b'add_coin',b'gain_coin') for p,data in before.items())
