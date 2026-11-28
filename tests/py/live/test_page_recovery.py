"""A stalled opening can be abandoned; refreshing the selected page is not a turn."""
import time
from types import SimpleNamespace

import pytest
from flask import request

from .test_browser_composers import ARENA_SEND, bind
from .test_qwen_dock_turn import dock_http
from .test_studio_conversation import local_studio
from .test_ui_bugs_live import isolated_native_project
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA_SEND}],indirect=True)
def test_reload_only_bound_page_even_before_composer_ready(local_studio,cold_tf6,monkeypatch):
    browser=local_studio; post=bind(browser,cold_tf6,monkeypatch)
    cid=post('/chats/new',site_id='arena')['current_id']; url=browser.current_url
    session=cold_tf6[-1][-1].extensions['godot_session']
    ticket=session.ticket=object(); preview=session.pending={'id':'pending-preview'}
    browser.execute_script('document.querySelector("form").remove();window.original=true')
    assert not post('/browser/page_status',chat_id=cid)['ready']
    assert post('/browser/reload',chat_id='other')['kind']=='conflict'
    session.busy=True
    try: assert post('/browser/reload',chat_id=cid)['kind']=='conflict'
    finally: session.busy=False
    browser.execute_script("history.replaceState({},'', '/c/other')")
    assert post('/browser/reload',chat_id=cid)['kind']=='conflict'
    browser.execute_script('history.replaceState({},"",arguments[0])',url)
    original=browser.current_window_handle
    browser.switch_to.window(next(h for h in browser.window_handles if h!=original))
    browser.get(url); browser.execute_script('window.original=true')
    assert post('/browser/reload',chat_id=cid)['kind']=='conflict'
    assert browser.execute_script('return !!window.original')
    browser.switch_to.window(original)
    assert browser.execute_script('return !!window.original')
    assert post('/browser/reload',chat_id=cid)=={'ok':True}
    assert post('/browser/page_status',chat_id=cid)['ready']
    assert browser.current_url==url and browser.current_window_handle==original
    assert browser.execute_script('return [!!window.original,sends,pastes,sent]')==[False,0,[],[]]
    assert session.ticket is ticket and session.pending is preview


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA_SEND+'''<script>
if(performance.getEntriesByType('navigation')[0].type==='reload'){
 document.querySelector('form').setAttribute('aria-hidden','true');
 document.body.insertAdjacentHTML('beforeend','<div role="dialog" aria-modal="true"><textarea name="message"></textarea></div>');}
</script>'''}],indirect=True)
def test_reload_explains_blocked_field_and_allows_only_fresh_edits(local_studio,cold_tf6,monkeypatch):
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    browser=local_studio; post=bind(browser,cold_tf6,monkeypatch)
    cid=post('/chats/new',site_id='arena')['current_id']
    assert post('/chat/live_input',chat_id=cid,seq=1,text='привет')['applied']
    monkeypatch.setattr(ArenaDelivery,'_ensure_monitor',lambda *_:None)
    assert not post('/chat',chat_id=cid,prompt='привет')['ok']
    assert post('/browser/reload',chat_id=cid,seq=4)['ok']
    assert post('/browser/page_status',chat_id=cid)=={'ready':False,'reason':'dialog'}
    assert not post('/chat/live_input',chat_id=cid,seq=5,text='blocked')['applied']
    assert browser.execute_script('return [field.innerText.trim(),sent,pastes,document.querySelector("[role=dialog] textarea").value]')==['',[],[],'']
    browser.execute_script('document.querySelector("[role=dialog]").remove();document.querySelector("form").removeAttribute("aria-hidden")')
    assert post('/browser/page_status',chat_id=cid)['ready']
    assert not post('/chat/live_input',chat_id=cid,seq=3,text='stale')['applied']
    assert post('/chat/live_input',chat_id=cid,seq=6,text='снова')['applied']
    assert browser.execute_script('return [field.innerText.trim(),sent]')==['снова',[]]


PROBE = '''@tool
extends EditorPlugin
func _enter_tree(): call_deferred("run")
func until(check: Callable) -> bool:
    var end := Time.get_ticks_msec()+10000
    while not check.call() and Time.get_ticks_msec()<end:
        await get_tree().create_timer(0.05).timeout
    return check.call()
func has_notice(panel, key: String) -> bool:
    for child in panel._view._chat_container.get_children():
        if child is Label and child.text == panel._t(key) and child.is_visible_in_tree(): return true
    return false
func run():
    var p = Engine.get_meta("_godot_agent_entry_owner")._dock
    if not await until(func(): return p._link and p._start_screen and not p._link.is_inflight()):
        get_tree().quit(2);return
    var host = p.get_parent()
    while host and not host is EditorDock: host = host.get_parent()
    if host: host.make_visible()
    else: Engine.get_meta("_godot_agent_entry_owner")._promote_dock_tab()
    var start = p._start_screen
    start.new_chat_requested.emit("arena")
    if not await until(func(): return FileAccess.file_exists("user://opening")):
        get_tree().quit(3);return
    var menu = start._loading_view.get_node("LoadingMenu")
    if not menu.is_visible_in_tree(): get_tree().quit(4);return
    menu.pressed.emit()
    if not start._home.is_visible_in_tree(): get_tree().quit(5);return
    FileAccess.open("user://release-opening",FileAccess.WRITE).close()
    if not await until(func(): return FileAccess.file_exists("user://opening-finished")):
        get_tree().quit(6);return
    await get_tree().create_timer(0.3).timeout
    if not start._home.is_visible_in_tree() or p._current_chat_id!="": get_tree().quit(7);return
    start.load_chat_requested.emit("missing")
    if not await until(func(): return start._home.is_visible_in_tree() and not start.is_loading()):
        get_tree().quit(8);return
    start.new_chat_requested.emit("arena")
    if not await until(func(): return p._bar_btn_reload.is_visible_in_tree() and not p._bar_btn_reload.disabled):
        get_tree().quit(9);return
    var current = p._current_chat_id
    if not await until(func(): return FileAccess.file_exists("user://mirroring") and not p._link.is_inflight()):
        get_tree().quit(14);return
    p.input_field.text = "черновик\\nсо второй строкой"
    p.input_field.text_changed.emit()
    p._bar_btn_reload.pressed.emit()
    if p._link.is_inflight() or not p._reloading_page: get_tree().quit(15);return
    FileAccess.open("user://release-mirror",FileAccess.WRITE).close()
    if not await until(func(): return FileAccess.file_exists("user://reloaded") and not p._reloading_page):
        get_tree().quit(10);return
    if not await until(func(): return has_notice(p,"page_dialog")):
        get_tree().quit(12);return
    FileAccess.open("user://dialog-dismissed",FileAccess.WRITE).close()
    if not await until(func(): return has_notice(p,"page_ready")):
        get_tree().quit(13);return
    if p.input_field.text!="черновик\\nсо второй строкой" or p._current_chat_id!=current or p.send_button.disabled:
        get_tree().quit(11);return
    get_tree().quit()
'''


@pytest.mark.needs_live
def test_dock_menu_ignores_late_opening_and_reload_keeps_draft(dock_http):
    app, _, state, driver, run_probe = dock_http
    calls=[]; refreshes=[]
    driver.timeouts=SimpleNamespace(page_load=30)
    driver.set_page_load_timeout=lambda t:setattr(driver.timeouts,'page_load',t)
    driver.refresh=lambda:refreshes.append(driver.current_url)
    driver.execute_script=lambda *_:'dialog' if refreshes and not (state/'dialog-dismissed').exists() else True

    @app.after_request
    def observe(response):
        path=request.path; calls.append((path, (request.get_json(silent=True) or {}).get('text')))
        if path=='/chats/new' and not (state/'opening').exists():
            (state/'opening').touch(); until=time.monotonic()+8
            while not (state/'release-opening').exists() and time.monotonic()<until: time.sleep(.03)
            (state/'opening-finished').touch()
        if path=='/chat/live_input' and not (state/'mirroring').exists():
            (state/'mirroring').touch(); until=time.monotonic()+4
            while not (state/'release-mirror').exists() and time.monotonic()<until: time.sleep(.03)
        if path=='/browser/reload' and response.json.get('ok'): (state/'reloaded').touch()
        return response

    run_probe(PROBE)
    assert refreshes==['https://arena.ai/text/direct'] and driver.timeouts.page_load==30
    assert [p for p,_ in calls if p in ('/chats/new','/chats/open','/browser/reload','/chat')]==[
        '/chats/new','/chats/open','/chats/new','/browser/reload']
    assert not any(text for route,text in calls if route=='/chat/live_input')
