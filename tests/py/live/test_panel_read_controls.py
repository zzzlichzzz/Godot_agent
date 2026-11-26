"""Press real Godot read controls; record decisions instead of touching an HTTP listener."""
import subprocess

import pytest
from tests.py.live.test_ui_bugs_live import _find_godot, isolated_native_project


@pytest.mark.needs_live
def test_read_buttons_badge_pause_and_chat_reset(isolated_native_project):
    godot = _find_godot()
    if not godot:
        pytest.skip('Godot unavailable')
    project, env, _ = isolated_native_project
    (project / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="read-ui-probe"\n', 'utf8')
    def run(*args):
        res = subprocess.run([godot, '--headless', '--path', str(project), *args], env=env,
                             capture_output=True, text=True, errors='replace', timeout=50)
        output = res.stdout + res.stderr
        assert res.returncode == 0 and 'SCRIPT ERROR' not in output, output
        return output
    run('--import')
    (project / 'probe.gd').write_text('''extends SceneTree
const Consent = preload("res://addons/godot_agent/editor/native/agent_read_consent.gd")
class Transport:
    var calls := []
    func request(url, _headers, method, body):
        assert(url.ends_with("/chat/read/decision") and method == HTTPClient.METHOD_POST)
        calls.append(JSON.parse_string(body))
        return OK
var _view
var _current_chat_id := "chat-A"
var _is_network_busy := false
var _pending_request_kind := ""
var http_request := Transport.new()
func _set_ui_busy(flag): _is_network_busy = flag
func _policy_json(body): return JSON.stringify(body)
func _json_headers(): return []
func _init(): call_deferred("journey")
func offer(id, pause=false):
    Consent.offer(self, {"chat_id": _current_chat_id, "id": id, "pause": pause, "action": {"action":"read_file","path":"res://hero.gd"}})
func click(index):
    var card = _view._chat_container.get_child(-1)
    assert("res://hero.gd" in card.find_child("RequestedAction", true, false).text)
    card.find_child("Choices", true, false).get_child(index).pressed.emit()
    _set_ui_busy(false)
    Consent.finish(self, true)
func journey():
    _view = load("res://addons/godot_agent/editor/native/agent_chat_view.gd").new()
    root.add_child(_view)
    _view._root_vbox = VBoxContainer.new()
    _view.add_child(_view._root_vbox)
    _view._chat_container = VBoxContainer.new()
    _view._root_vbox.add_child(_view._chat_container)
    offer("deny")
    assert(http_request.calls.is_empty())
    click(2)
    assert(not http_request.calls.back().approved)
    offer("once")
    click(0)
    offer("always")
    assert(http_request.calls.size() == 2 and http_request.calls.back().approved)
    click(1)
    assert(not _view._auto_approve_all)
    offer("auto")
    assert(http_request.calls.back() == {"chat_id":"chat-A","request_id":"auto","approved":true})
    _set_ui_busy(false)
    Consent.finish(self, true)
    offer("eighth", true)
    assert(http_request.calls.size() == 4)
    click(0)
    _view._root_vbox.get_node(Consent.BADGE).pressed.emit()
    offer("ask_again")
    assert(http_request.calls.size() == 5)
    click(1)
    _view.clear()
    _current_chat_id = "chat-B"
    offer("switched")
    assert(http_request.calls.size() == 6 and not _view._root_vbox.has_node(Consent.BADGE))
    print("READ_CONTROLS_OK")
    quit()
''', 'utf8')
    assert 'READ_CONTROLS_OK' in run('--script', 'res://probe.gd', '--quit-after', '240')
