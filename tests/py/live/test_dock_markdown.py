"""Render a network Markdown answer in the actual dock, live and reopened from history."""
import pytest
from flask import request
from .test_qwen_dock_turn import dock_http
from .test_ui_bugs_live import isolated_native_project


@pytest.mark.needs_live
@pytest.mark.parametrize('site,url',[('arena','https://arena.ai/c/markdown'),('qwen','https://chat.qwen.ai/c/markdown')])
def test_answer_and_history_show_markdown(dock_http,monkeypatch,site,url):
    app,_,state,driver,run_probe=dock_http
    with app.extensions['native_references'].scope():
        from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    source='### Result\n**bold** and `tick`\n```gdscript\nvar a = "**literal**"\n```\n[b]literal[/b]'
    def answer(*a,**k):
        driver.current_url=url;return {'text':source+'\n===DONE==='}
    monkeypatch.setattr(BrowserBackend,'send',answer)
    opened=[]
    @app.after_request
    def observe(response):
        if request.path=='/chats/open': opened.append(response.get_json())
        return response
    run_probe('''@tool
extends EditorPlugin
func _enter_tree(): call_deferred("run")
func until(check: Callable) -> bool:
    var end := Time.get_ticks_msec()+10000
    while not check.call() and Time.get_ticks_msec()<end: await get_tree().create_timer(.05).timeout
    return check.call()
func rendered(p):
    for card in p._view._chat_container.get_children():
        if card is AgentMessageCard:
            var rich: RichTextLabel = card.content
            if rich.get_parsed_text().begins_with("Result\\nbold and tick") and "[font_size=" in rich.text and "[b]bold[/b]" in rich.text and "[code]tick[/code]" in rich.text and "**literal**" in rich.get_parsed_text() and "[b]literal[/b]" in rich.get_parsed_text(): return card
    return null
func run():
    var p = Engine.get_meta("_godot_agent_entry_owner")._dock
    if not await until(func(): return p._link and not p._link.is_inflight()): get_tree().quit(2);return
    p._request_chats("new", {"site_id":"PROVIDER"})
    if not await until(func(): return p._current_chat_id!="" and p.get_node("VBoxContainer").visible): get_tree().quit(3);return
    p.input_field.text="**literal user**";p.send_button.pressed.emit()
    if not await until(func(): return rendered(p)!=null): get_tree().quit(4);return
    var old=rendered(p);p._request_chats("open", {"id":p._current_chat_id})
    if not await until(func(): return not is_instance_valid(old) and rendered(p)!=null): get_tree().quit(5);return
    for card in p._view._chat_container.get_children():
        if card is UserMessageCard and card.content.get_parsed_text()=="**literal user**": get_tree().quit(0);return
    get_tree().quit(6)
'''.replace('PROVIDER',site))
    record,=opened; assert not record['history_only']
    row,=[r for r in record['transcript'] if r['role']=='agent']
    assert row['text']==source and '[b]bold[/b]' in row['display_text']
