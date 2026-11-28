"""The real dock can keep drafts local, still dispatch the turn and show the Direct pick."""
import pytest
from flask import request

from .test_qwen_dock_turn import dock_http
from .test_ui_bugs_live import isolated_native_project


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
    p._request_chats("new", {"site_id":"arena"})
    if not await until(func(): return p._current_chat_id!="" and p.get_node("VBoxContainer").visible):
        get_tree().quit(3);return
    p._on_settings_pressed()
    if not p._live_toggle.is_visible_in_tree() or p._live_toggle.button_pressed:
        get_tree().quit(4);return
    p._live_toggle.button_pressed = true
    p._settings_dialog.hide()
    p.input_field.text = "mirror this draft"
    p.input_field.text_changed.emit()
    if not await until(func(): return FileAccess.file_exists("user://mirror-observed")):
        get_tree().quit(5);return
    p._on_settings_pressed()
    p._live_toggle.button_pressed = false
    p._settings_dialog.hide()
    p.input_field.text = "send this only on submit"
    p.input_field.text_changed.emit()
    await get_tree().create_timer(1.2).timeout
    p.send_button.pressed.emit()
    var view = p._view._chat_container
    if not await until(func(): return view.find_children("*","Label",true,false).any(func(n): return "Arena Direct:" in n.text and "A 35 / B 80" in n.text)):
        get_tree().quit(6);return
    get_tree().quit()
'''


@pytest.mark.needs_live
def test_saved_local_drafts_and_direct_summary(dock_http, monkeypatch):
    app, _, state, driver, run_probe = dock_http
    setting = state/'godot_agent_live_input.txt'; setting.write_text('0', 'utf8')
    with app.extensions['native_references'].scope():
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    drafts, sent = [], []

    @app.before_request
    def observe():
        if request.path == '/chat/live_input':
            drafts.append(request.json['text'])
            if drafts[-1] == 'mirror this draft': (state/'mirror-observed').touch()

    def answer(backend, prompt, **_):
        sent.append(prompt)
        driver.current_url = 'https://arena.ai/c/direct-dock'
        backend._parser.events.append(dict(mode='direct', decision='selected', variants=2, selected='B',
            other='A', score_a=35, score_b=80, reason='only_acceptable'))
        return dict(text='OK.\n===DONE===', action=None)

    monkeypatch.setattr(BrowserBackend, 'send', answer)
    run_probe(PROBE)
    assert 'mirror this draft' in drafts and 'send this only on submit' not in drafts
    assert len(sent)==1 and sent[0].endswith('send this only on submit') and setting.read_text()=='0'


@pytest.mark.needs_live
def test_failed_send_restores_panel_without_mirroring(dock_http):
    app, _, state, _, run_probe = dock_http
    turns, late_drafts = [], []

    @app.before_request
    def fail_send():
        if request.path == '/chat':
            turns.append(request.json['prompt'])
            return {'error':'Arena: message not sent', 'kind':'unavailable'}, 400
        if request.path == '/chat/live_input':
            if turns: late_drafts.append(request.json['text'])
            if request.json['text']=='original': (state/'draft-seen').touch()
            return {'ok':True, 'applied':True}

    run_probe(PROBE[:PROBE.index('    p._on_settings_pressed()')] + '''
    p.input_field.text = "original"
    p.input_field.text_changed.emit()
    if not await until(func(): return FileAccess.file_exists("user://draft-seen") and not p._live_inflight):
        get_tree().quit(4);return
    p.send_button.pressed.emit()
    if not await until(func(): return not p._is_network_busy and p.input_field.text=="original"):
        get_tree().quit(5);return
    await get_tree().create_timer(1.4).timeout
    p.input_field.text = "edited"
    p.input_field.text_changed.emit()
    await get_tree().create_timer(0.9).timeout
    get_tree().quit()
''')
    assert turns==['original'] and late_drafts==['edited']
