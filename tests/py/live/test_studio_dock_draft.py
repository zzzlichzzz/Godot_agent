"""Godot keystrokes → authenticated HTTP → offline Chrome composer. No model call."""
import os
from pathlib import Path
import subprocess
from threading import Thread

from flask import request
import pytest
from werkzeug.serving import make_server

from .test_studio_conversation import START, local_studio
from .test_ui_bugs_live import _find_godot, isolated_native_project


PROBE = '''@tool
extends EditorPlugin

func _enter_tree(): call_deferred("run")

func wait_for(check: Callable) -> bool:
    var end := Time.get_ticks_msec() + 12000
    while not check.call() and Time.get_ticks_msec() < end:
        await get_tree().create_timer(0.05).timeout
    return check.call()

func run():
    var panel = Engine.get_meta("_godot_agent_entry_owner")._dock
    if not await wait_for(func(): return panel._link and panel._start_screen and not panel._link.is_inflight()):
        get_tree().quit(2);return
    panel._request_chats("new", {"site_id":"aistudio"})
    if not await wait_for(func(): return panel._current_chat_id!="" and panel.get_node("VBoxContainer").visible):
        get_tree().quit(3);return
    var results := []
    panel._link.short_response.connect(func(id,_result,code,_headers,body):
        if id=="live_input" and code==200: results.append(JSON.parse_string(body.get_string_from_utf8())))
    panel.input_field.insert_text_at_caret("Привет [b] 🌿")
    if not await wait_for(func(): return results.any(func(r): return r.get("reason")=="no_input_field")):
        push_error("Expected an unavailable composer");get_tree().quit(4);return
    if not panel._live_note.visible or panel._live_last_sent==panel.input_field.text:
        push_error("Skipped draft was reported as delivered");get_tree().quit(7);return
    if not await wait_for(func(): return results.back().get("applied")==true):
        push_error("Draft never reached the composer after it appeared");get_tree().quit(5);return
    if panel._live_note.visible:
        push_error("Draft warning did not clear after confirmation");get_tree().quit(8);return
    panel.input_field.insert_text_at_caret("\\nстрока 2")
    if not await wait_for(func(): return results.filter(func(r): return r.get("applied")==true).size()>=2):
        push_error("Second edit not acknowledged");get_tree().quit(6);return
    panel.input_field.insert_text_at_caret("?")
    if not await wait_for(func(): return results.back().get("reason")=="history_only"):
        push_error("Another tab must not receive the draft");get_tree().quit(9);return
    if not panel._live_note.visible or panel._live_dirty or panel._live_last_sent==panel.input_field.text:
        push_error("An unverified tab must require an explicit reopen");get_tree().quit(10);return
    get_tree().quit()
'''


@pytest.mark.needs_live
def test_late_composer_receives_latest_dock_draft_without_send(local_studio, isolated_native_project, monkeypatch):
    from python.channels.http.app import create_app
    godot = _find_godot()
    if not godot: pytest.skip('Godot editor required')
    project, env, _ = isolated_native_project
    settings = project/'project.godot'; enabled = settings.read_text('utf-8')
    settings.write_text(enabled.split('[editor_plugins]')[0], 'utf-8')
    cmd = [godot, '--headless', '--path', str(project)]
    subprocess.run([*cmd, '--import'], env=env, capture_output=True, timeout=65, check=True)
    state = Path(env['APPDATA'] if os.name == 'nt' else env['XDG_DATA_HOME'])/'bug-register-probe'
    state.mkdir(parents=True, exist_ok=True)
    (state/'godot_agent_token.txt').write_text('SYNTHETIC-STUDIO-DRAFT-FIXTURE', 'utf-8')
    app = create_app(project, state); refs = app.extensions['native_references']
    browser = local_studio
    monkeypatch.setattr(refs.state, 'wait_driver', lambda *a, **kw: browser)
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: browser)
    attempts = []; sends = []; draft = 'Привет [b] 🌿'

    @app.before_request
    def mount_late():
        if request.path == '/chat': sends.append(True)
        if request.path == '/chat/live_input' and request.json['text'] == draft and not attempts:
            browser.execute_script('field.hidden=true')
        if request.path == '/chat/live_input' and request.json['text'].endswith('?'):
            browser.switch_to.window(next(h for h in browser.window_handles if h != browser.current_window_handle))
            browser.get(START)

    @app.after_request
    def observe(response):
        if request.path == '/chat/live_input' and request.json['text']:
            attempts.append((request.json['text'], response.json))
            if len(attempts) == 1:
                browser.execute_script('''field.hidden=false;
                    const decoy=field.cloneNode(); decoy.style.opacity=0; field.after(decoy);
                    field.addEventListener('input',()=>queueMicrotask(()=>{
                        const fresh=document.createElement('textarea'); fresh.onkeydown=field.onkeydown;
                        field.replaceWith(fresh);
                    }),{once:true});''')
        return response

    with make_server('127.0.0.1', 0, app) as server:
        link = project/'addons/godot_agent/editor/native/agent_server.gd'
        link.write_text(link.read_text('utf-8').replace('127.0.0.1:5000', f'127.0.0.1:{server.server_port}'), 'utf-8')
        probe = project/'addons/entry_probe'; probe.mkdir()
        (probe/'plugin.cfg').write_text('[plugin]\nname="Draft probe"\nscript="check.gd"\n', 'utf-8')
        (probe/'check.gd').write_text(PROBE, 'utf-8'); settings.write_text(enabled, 'utf-8')
        thread = Thread(target=server.serve_forever); thread.start()
        try:
            run = subprocess.run([*cmd, '--editor'], env=env, capture_output=True, timeout=55)
        finally:
            server.shutdown(); thread.join()
    log = (run.stdout+run.stderr).decode('utf-8', errors='replace')
    assert run.returncode == 0 and 'SCRIPT ERROR' not in log, (attempts, log)
    final = draft+'\nстрока 2'
    assert [(s, r['applied']) for s, r in attempts] == [(draft, False), (draft, False), (draft, True), (final, True), (final+'?', False)]
    assert not sends and browser.execute_script('return [field.value, submitted]') == ['', 0]
    browser.switch_to.window(next(h for h in browser.window_handles if h != browser.current_window_handle))
    assert browser.execute_script('return [...Array.from(document.querySelectorAll("textarea"), e=>e.value), submitted]') == [final, '', 0]
