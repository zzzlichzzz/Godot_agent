"""Stop a loopback server under the open Godot dock; its restart button starts process #2."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from .test_ui_bugs_live import _find_godot, isolated_native_project


SERVER = '''from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json, os, sys, threading, time, traceback

root=Path(os.environ['RESTART_FIXTURE']);port_file=root/'port'
generation=2 if port_file.exists() else 1
def record_failure(kind,error,tb):
    (root/'fixture-error').write_text(''.join(traceback.format_exception(kind,error,tb)),encoding='utf-8')
sys.excepthook=record_failure
current='other' if generation==2 else None
log_lock=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self): self.respond({})
    def do_POST(self): self.respond(json.loads(self.rfile.read(int(self.headers['Content-Length'])) or '{}'))
    def respond(self,body):
        global current
        with log_lock, (root/'requests.jsonl').open('a') as out:
            out.write(json.dumps([generation,self.path,body.get('id')])+'\\n')
        if self.path=='/chats/open': current=body['id']
        if self.path=='/health' and generation==1: time.sleep(5.5)
        payload={'ok':True}
        if self.path in ('/chats/open','/chats/list'):
            payload=dict(current_id=current,chats=[dict(id='original',title='Test')],kind='api',title='Test',transcript=[])
        data=json.dumps(payload).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)))
        try: self.end_headers();self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
with ThreadingHTTPServer(('127.0.0.1',int(port_file.read_text()) if generation==2 else 0),Handler) as server:
    port_file.write_text(str(server.server_port));server.timeout=.15;end=time.monotonic()+90
    while not (root/('stop'+str(generation))).exists() and time.monotonic()<end: server.handle_request()
(root/('closed'+str(generation))).touch()
'''

PROBE = '''@tool
extends EditorPlugin

func _enter_tree() -> void:
    call_deferred("run")

func _exit_tree() -> void:
    # The Windows console launcher can wait for its child even after the editor exits.
    FileAccess.open(OS.get_environment("RESTART_FIXTURE").path_join("stop2"),FileAccess.WRITE).close()

func wait_until(check: Callable) -> bool:
    var end := Time.get_ticks_msec()+32000
    while not bool(check.call()) and Time.get_ticks_msec()<end:
        await get_tree().create_timer(0.1).timeout
    return bool(check.call())

func run() -> void:
    var owner = Engine.get_meta("_godot_agent_entry_owner")
    var panel = owner._dock
    if not await wait_until(func(): return panel._link!=null and panel._link._http!=null and panel._start_screen!=null and not panel._link.is_inflight() and not panel._is_network_busy):
        push_error("Dock initialization timed out");get_tree().quit(7);return
    # In 4.6 add_control_to_dock wraps legacy controls in an EditorDock.
    var host = panel.get_parent()
    while host != null and not host is EditorDock:
        host = host.get_parent()
    if host: host.make_visible()
    else: owner._promote_dock_tab()
    panel._request_chats("open", {"id":"original"})
    if not await wait_until(func(): return panel._current_chat_id=="original" and panel.get_node("VBoxContainer").is_visible_in_tree()):
        push_error("First open: id=%s dock=%s chat=%s" % [panel._current_chat_id,panel.is_visible_in_tree(),panel.get_node("VBoxContainer").visible]);get_tree().quit(2);return
    panel.input_field.text = "draft [literal]"
    var observation := {"timeout":false,"offline":false}
    panel._link.server_state_changed.connect(func(running):
        if not running: observation.offline = true)
    panel._link.short_response.connect(func(id,result,_code,_h,_b):
        if id=="health" and result==HTTPRequest.RESULT_TIMEOUT: observation.timeout = true)
    if not await wait_until(func(): return observation.timeout) or observation.offline or panel._recover_button.visible:
        push_error("Connected but slow server was reported offline");get_tree().quit(9);return
    FileAccess.open(OS.get_environment("RESTART_FIXTURE").path_join("stop1"),FileAccess.WRITE).close()
    if not await wait_until(func(): return FileAccess.file_exists(OS.get_environment("RESTART_FIXTURE").path_join("closed1"))):
        push_error("Fixture listener did not close");get_tree().quit(8);return
    if not await wait_until(func(): return panel._recover_button.is_visible_in_tree() and panel._server_down):
        push_error("No restart offer: visible=%s down=%s needs=%s chat=%s link=%s short=%s" % [panel.get_node("VBoxContainer").is_visible_in_tree(),panel._server_down,panel._needs_reopen,panel._current_chat_id,panel._link.is_inflight(),panel._link._short_id]);get_tree().quit(3);return
    if not panel.send_button.disabled or panel._recover_button.text!=panel._t("srv_restart_chat"):
        push_error("Disconnected composer state");get_tree().quit(4);return
    panel._recover_button.pressed.emit()
    if not await wait_until(func(): return not panel._recover_button.visible and not panel._link.is_inflight()):
        push_error("No successful reopen");get_tree().quit(5);return
    await get_tree().create_timer(0.7).timeout
    if panel.input_field.text!="draft [literal]" or panel._current_chat_id!="original" or panel.send_button.disabled:
        push_error("Lost chat, draft or send control");get_tree().quit(6);return
    print("ACTIVE_CHAT_RESTART_OK");get_tree().quit()
'''


@pytest.mark.needs_live
def test_active_chat_restarts_without_resending(isolated_native_project, tmp_path):
    godot = _find_godot()
    if not godot: pytest.skip('Godot editor required')
    project, env, _ = isolated_native_project
    # The sandbox has a fresh LOCALAPPDATA; use this interpreter instead of a
    # WindowsApps python launcher that looks up runtimes in the user's profile.
    env = dict(env, RESTART_FIXTURE=str(tmp_path), PATH=str(Path(sys.executable).parent)+os.pathsep+env['PATH'])
    script = project/'main.py'; script.write_text(SERVER, 'utf-8')
    port_file = tmp_path/'port'; settings=project/'project.godot'; enabled=settings.read_text('utf-8')
    with subprocess.Popen([sys.executable, str(script)],env=env) as initial:
        try:
            end=time.monotonic()+5
            while not port_file.exists() and initial.poll() is None and time.monotonic()<end: time.sleep(.05)
            link=project/'addons/godot_agent/editor/native/agent_server.gd'
            link.write_text(link.read_text('utf-8').replace('127.0.0.1:5000','127.0.0.1:'+port_file.read_text()),'utf-8')
            settings.write_text(enabled.split('[editor_plugins]')[0],'utf-8')
            subprocess.run([godot,'--headless','--import','--path',str(project)],env=env,capture_output=True,check=True,timeout=65)
            probe=project/'addons/entry_probe';probe.mkdir()
            (probe/'plugin.cfg').write_text('[plugin]\nname="Restart probe"\nscript="check.gd"\n','utf-8')
            (probe/'check.gd').write_text(PROBE,'utf-8');settings.write_text(enabled,'utf-8')
            # The launched server outlives the editor and can inherit stdout on Windows.
            # Wait for the editor process itself, not for EOF on its child's pipe.
            output=tmp_path/'editor.log'
            with output.open('wb') as log_file:
                proc=subprocess.run([godot,'--headless','--editor','--path',str(project)],env=env,timeout=100,
                                    stdout=log_file,stderr=subprocess.STDOUT)
            log=output.read_text('utf-8',errors='replace')
            if (tmp_path/'fixture-error').exists(): pytest.fail((tmp_path/'fixture-error').read_text('utf-8'))
            assert proc.returncode==0 and 'ACTIVE_CHAT_RESTART_OK' in log and 'SCRIPT ERROR' not in log,log
            requests=[json.loads(line) for line in (tmp_path/'requests.jsonl').read_text().splitlines()]
            assert [r for r in requests if r[1]=='/chats/open']==[[1,'/chats/open','original'],[2,'/chats/open','original']]
            assert not any(r[1]=='/chat' for r in requests)
        finally:
            for i in (1,2): (tmp_path/f'stop{i}').touch()
