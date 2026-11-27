"""Exercise the shipped zero-argument launcher, including a subsequent Explorer launch."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import Request, build_opener, ProxyHandler

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROBE = '''extends SceneTree
func _initialize():
    var link = load("res://addons/godot_agent/editor/native/agent_server_link.gd").new()
    var ok = link._launch_server_process()
    link.free()
    quit(0 if ok else 3)
'''


@pytest.mark.needs_live
def test_packaged_exe_from_godot_then_standalone(tmp_path):
    binary = os.environ.get('GODOT_AGENT_TEST_SERVER_EXE')
    godot = os.environ.get('GODOT_AGENT_GODOT_BIN')
    if os.name != 'nt' or not binary or not godot:
        pytest.skip('requires a packaged Windows EXE and a Godot editor')
    with socket.socket() as sock:
        try: sock.bind(('127.0.0.1', 5000))
        except OSError: pytest.skip('native panel port in use')
    project = tmp_path / 'тест запуска'; addon = project / 'addons/godot_agent'
    native = addon / 'editor/native'; native.mkdir(parents=True)
    for name in ('agent_server.gd', 'agent_server_link.gd'):
        shutil.copyfile(ROOT / 'editor/native' / name, native / name)
    exe = addon / 'python/dist/godot_agent_server.exe'; exe.parent.mkdir(parents=True)
    shutil.copyfile(binary, exe)
    (addon / 'plugin.cfg').write_text('[plugin]\n', 'utf-8')
    (project / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="Проверка запуска"\n', 'utf-8')
    (project / 'launch.gd').write_text(PROBE, 'utf-8')
    (project / 'marker.txt').write_text('startup fixture', 'utf-8')
    env = dict(os.environ, APPDATA=str(tmp_path / 'roaming'), LOCALAPPDATA=str(tmp_path / 'local'),
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    env.pop('GODOT_AGENT_GODOT_BIN', None)
    state = Path(env['APPDATA']) / 'Godot/app_userdata/Проверка запуска'
    endpoint = state / 'http_endpoint.json'
    http = build_opener(ProxyHandler({}))

    def request(path, data=None):
        token = (state / 'godot_agent_token.txt').read_text('utf-8').strip()
        req = Request('http://127.0.0.1:5000'+path, None if data is None else json.dumps(data).encode(),
                      headers={'X-Agent-Token': token, 'Content-Type': 'application/json'})
        with http.open(req, timeout=5) as response: return json.load(response)

    cmd = [godot, '--headless', '--path', str(project)]
    subprocess.run([*cmd, '--import'], cwd=tmp_path, env=env, capture_output=True, timeout=45, check=True)
    first_token = None
    for source, command in [('panel', [*cmd, '--script', 'res://launch.gd']), ('standalone', [str(exe)])]:
        with (tmp_path / (source+'.log')).open('w+b') as log:
            proc = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=log, stderr=log)
            try:
                end = time.monotonic() + 45
                while not endpoint.exists() and time.monotonic() < end:
                    if proc.poll() is not None and (source == 'standalone' or proc.returncode): break
                    time.sleep(.1)
                if not endpoint.exists():
                    log.seek(0); pytest.fail(f'{source} did not start: '+log.read().decode('utf-8','replace')[-2000:])
                assert request('/health')['ok']
                assert Path(request('/init', {})['project_root']) == project
                token = (state / 'godot_agent_token.txt').read_bytes()
                if first_token is None: first_token = token
                elif token != first_token: pytest.fail('The standalone launcher replaced the panel token')
                answer = request('/tools/call', {'name':'read', 'args':{'path':'res://marker.txt'}})
                assert answer['ok'] and 'startup fixture' in str(answer['result']), answer
            finally:
                if endpoint.exists(): request('/server/shutdown', {})
                try: proc.wait(timeout=15)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            deadline = time.monotonic() + 10
            while endpoint.exists() and time.monotonic() < deadline: time.sleep(.1)
            assert proc.returncode == 0 and not endpoint.exists()
