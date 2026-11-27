"""Drive the real dock through a failed read continuation and a late reply during ＋."""
import os
from pathlib import Path
import subprocess
from threading import Thread
import time
from types import SimpleNamespace

import pytest
from flask import request
from werkzeug.serving import make_server

from .test_ui_bugs_live import _find_godot, isolated_native_project


PROBE = '''@tool
extends EditorPlugin
func _enter_tree(): call_deferred("run")
func until(check: Callable) -> bool:
    var end := Time.get_ticks_msec() + 10000
    while not check.call() and Time.get_ticks_msec() < end:
        await get_tree().create_timer(0.05).timeout
    return check.call()
func run():
    var p = Engine.get_meta("_godot_agent_entry_owner")._dock
    if not await until(func(): return p._link and p._start_screen and not p._link.is_inflight()):
        get_tree().quit(2);return
    p._request_chats("new", {"site_id":"qwen"})
    if not await until(func(): return p._current_chat_id!="" and p.get_node("VBoxContainer").visible):
        get_tree().quit(3);return
    var original: String = p._current_chat_id
    if not await until(func(): return p._chat_select.allow_reselect and p._chat_select.selected >= 0 and not p._link.is_inflight()):
        get_tree().quit(10);return
    p._chat_select.item_selected.emit(p._chat_select.selected)
    if not await until(func(): return FileAccess.file_exists("user://opened-current") and p.get_node("VBoxContainer").visible):
        get_tree().quit(11);return
    p.input_field.text = "user question"
    p.send_button.pressed.emit()
    var view = p._view._chat_container
    if not await until(func(): return view.find_child("Choices",true,false)!=null):
        get_tree().quit(4);return
    view.find_child("Choices",true,false).get_child(0).pressed.emit()
    if not await until(func(): return not p._is_network_busy and p.input_field.text=="user question"):
        get_tree().quit(5);return
    p.input_field.text += " edited"
    p.send_button.pressed.emit()
    if not await until(func(): return FileAccess.file_exists("user://third-dispatched")):
        get_tree().quit(6);return
    p._bar_btn_new.pressed.emit()
    var sites = p._start_screen._sites_list
    if not await until(func(): return p._start_screen.visible and p._start_screen._sites_view.visible and sites.get_children().any(func(b): return b is Button and "qwen" in b.text.to_lower())):
        get_tree().quit(7);return
    for site in sites.get_children():
        if site is Button and "qwen" in site.text.to_lower():
            site.pressed.emit(); break
    if not await until(func(): return original!=p._current_chat_id and p.get_node("VBoxContainer").visible):
        get_tree().quit(8);return
    if p.input_field.text!="" or p._chat_drafts.get(original)!="user question edited" or view.find_child("Choices",true,false):
        get_tree().quit(9);return
    get_tree().quit()
'''


@pytest.fixture
def dock_http(isolated_native_project, monkeypatch):
    from python.channels.http.app import create_app

    godot = _find_godot()
    if not godot: pytest.skip('Godot editor required')
    project, env, _ = isolated_native_project
    settings = project/'project.godot'; enabled = settings.read_text('utf-8')
    settings.write_text(enabled.split('[editor_plugins]')[0], 'utf-8')
    cmd = [godot, '--headless', '--path', str(project)]
    subprocess.run([*cmd, '--import'], env=env, capture_output=True, timeout=65, check=True)
    state = Path(env['APPDATA' if os.name=='nt' else 'XDG_DATA_HOME'])/'bug-register-probe'
    state.mkdir(exist_ok=True, parents=True)
    (state/'godot_agent_token.txt').write_text('SYNTHETIC-QWEN-PANEL-FIXTURE', 'utf-8')
    app = create_app(project, state); refs = app.extensions['native_references']
    driver = SimpleNamespace(current_url='about:blank', current_window_handle='test', execute_script=lambda *a: True)
    monkeypatch.setattr(refs.state, 'wait_driver', lambda *a, **kw: driver)
    monkeypatch.setattr(refs.routes, '_navigate', lambda _, url: setattr(driver, 'current_url', url) or True)
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: driver)

    def run_probe(script):
        with make_server('127.0.0.1', 0, app, threaded=True) as server:
            link = project/'addons/godot_agent/editor/native/agent_server.gd'
            link.write_text(link.read_text('utf-8').replace('127.0.0.1:5000', f'127.0.0.1:{server.server_port}'), 'utf-8')
            probe = project/'addons/entry_probe'; probe.mkdir()
            (probe/'check.gd').write_text(script, 'utf-8')
            (probe/'plugin.cfg').write_text('[plugin]\nname="Turn probe"\nscript="check.gd"\n', 'utf-8')
            settings.write_text(enabled, 'utf-8')
            thread=Thread(target=server.serve_forever); thread.start()
            try: run=subprocess.run([*cmd, '--editor'], env=env, capture_output=True, timeout=65)
            finally: server.shutdown(); thread.join()
        log=(run.stdout+run.stderr).decode('utf-8', errors='replace')
        assert run.returncode==0 and 'SCRIPT ERROR' not in log, (run.returncode,log)

    return app, project, state, driver, run_probe


@pytest.mark.needs_live
def test_error_restores_original_and_plus_releases_wait(dock_http, monkeypatch):
    from python.kernel.errors import AppError
    app, _, state, driver, run_probe = dock_http
    with app.extensions['native_references'].scope():
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    calls, events = [], []

    def send(self, prompt, cancel_cb, **kw):
        calls.append(prompt)
        if len(calls)==1:
            driver.current_url='https://chat.qwen.ai/c/panel-test'
            return {'text':'read?', 'action':{'action':'list_files','arguments':{'max_entries':2}}}
        if len(calls)==2: raise AppError('unavailable', 'Qwen error', details={'retry_prompt':True})
        (state/'third-dispatched').touch(); deadline=time.monotonic()+12
        while not cancel_cb() and time.monotonic()<deadline: time.sleep(.02)
        assert cancel_cb()
        return {'text':'late read', 'action':{'action':'list_files'}}

    monkeypatch.setattr(BrowserBackend, 'send', send)
    @app.after_request
    def observe(response):
        if request.path=='/chats/open' and not response.json['history_only']: (state/'opened-current').touch()
        if request.path in ('/chat', '/chat/read/decision', '/chat/stop', '/sites/list', '/chats/new'):
            events.append((request.path, request.json.get('turn_id'), response.status_code))
        return response

    run_probe(PROBE)
    assert len(calls)==3 and calls[0].endswith('user question') and calls[2].endswith('user question edited')
    stop, = [key for path,key,_ in events if path=='/chat/stop']
    end=events.index(('/chat',stop,409))
    assert [p for p,_,_ in events[end+1:] if p in ('/sites/list','/chats/new')]==['/sites/list','/chats/new']
    assert app.extensions['godot_session'].ticket is None
