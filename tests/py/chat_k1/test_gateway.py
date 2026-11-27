"""D70/D72 RED-first gateway activation, storage routing and two-insertion port."""
import ast
import hashlib
from importlib import import_module
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from python.kernel.errors import AppError

ROOT = Path(__file__).resolve().parents[3]
GATEWAY = 'python.substrate.assistant.chat_gateway'

def gateway(project, state):
    return import_module(GATEWAY).ChatGateway(project, state, ROOT)

def test_gateway_import_is_inert():
    names = ('python.substrate.llm.runtime_bindings', 'api_backend', 'librarian', 'minilich')
    with patch.dict(sys.modules):
        for name in (*names, GATEWAY):
            sys.modules.pop(name, None)
        module = import_module(GATEWAY)
        assert not any(name in sys.modules for name in names)
        assert callable(module.ChatGateway.send)

def test_activation_is_only_inside_send():
    path = ROOT/'python/substrate/assistant/chat_gateway.py'
    assert path.is_file(), 'gateway missing before D70'
    tree = ast.parse(path.read_text('utf-8'))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ChatGateway')
    send = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'send')
    bindings = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == 'python.substrate.llm'
                and [(i.name,i.asname) for i in n.names] == [('runtime_bindings',None)]]
    assert len(bindings) == 1 and bindings[0] in list(ast.walk(send))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            assert n.level == 0, 'D70: absolute package imports only'
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
             and isinstance(n.func.value,ast.Name) and n.func.value.id == 'runtime_bindings' and n.func.attr == 'register']
    assert len(calls) == 1 and calls[0] in list(ast.walk(send))

def test_default_port_present_and_callable(tmp_path):
    from python.runtime.bootstrap import default_ports
    port = default_ports(tmp_path, 'test', tmp_path.parent/'chat-profile')['chat_gateway']
    assert callable(port.send)

def test_bootstrap_import_lazy_until_default_ports(tmp_path):
    with patch.dict(sys.modules):
        sys.modules.pop('python.runtime.bootstrap', None)
        sys.modules.pop(GATEWAY, None)
        bootstrap = import_module('python.runtime.bootstrap')
        assert GATEWAY not in sys.modules
        ports = bootstrap.default_ports(tmp_path, 'test', tmp_path.parent/'chat-profile')
        assert GATEWAY in sys.modules, 'D72 lazy import insertion missing'
        assert callable(ports['chat_gateway'].send)

@pytest.mark.parametrize('inside', ['state', 'config'])
def test_profile_inside_project_denied_before_io(tmp_path, inside, monkeypatch):
    project = tmp_path/'project'; project.mkdir()
    state = project/'state' if inside == 'state' else tmp_path/'state'
    monkeypatch.setenv('GODOT_AGENT_CONFIG_DIR', str(project/'config' if inside == 'config' else tmp_path/'config'))
    with pytest.raises(AppError) as caught:
        gateway(project,state).send('hello')
    assert caught.value.kind == 'denied'
    assert list(project.rglob('*')) == []

def test_missing_project_not_found(tmp_path):
    with pytest.raises(AppError) as caught:
        gateway(tmp_path/'missing', tmp_path/'state').send('hello')
    assert caught.value.kind == 'not_found'

@pytest.mark.parametrize('mode', ['return', 'exception', 'interrupt'])
def test_lock_profile_route_finally_restores(tmp_path, mode, monkeypatch):
    project = tmp_path/'project'; project.mkdir()
    monkeypatch.setenv('GODOT_AGENT_CONFIG_DIR', str(tmp_path/'config'))
    port = gateway(project,tmp_path/'state')
    binding = import_module('python.substrate.llm.runtime_bindings')
    binding.register()
    api = import_module('python.substrate.llm.api.api_keys')
    backend = import_module('python.substrate.llm.backends.api_backend')
    parser = import_module('python.substrate.llm.parsers.parser_base')
    lock = import_module('python.substrate.context.librarian_read')._LOCK
    before = (os.environ.get(api.ENV_CONFIG_DIR), api._cfg_cache, api._secrets_cache, parser._save_corpus_sample)
    def native(subject,prompt,**kwargs):
        assert lock._is_owned()
        assert Path(api.config_path()).is_relative_to(tmp_path/'state'/'api_config')
        assert Path(subject._base_dir).is_relative_to(tmp_path/'state')
        assert subject._system_text_provider() == 'system-fixed'
        if mode == 'exception': raise ValueError('synthetic failure')
        if mode == 'interrupt': raise KeyboardInterrupt()
        return dict(text='answer', raw='answer\n===DONE===', action=None, finish_reason='stop')
    with patch.object(backend.ApiBackend,'send',native):
        if mode == 'return':
            value = port.send('hello', system_text='system-fixed', provider='ollama', model='offline')
            assert value['done'] is True and value['text'] == 'answer' and value['action'] is None
        else:
            with pytest.raises(ValueError if mode == 'exception' else KeyboardInterrupt):
                port.send('hello', system_text='system-fixed', provider='ollama', model='offline')
    after = (os.environ.get(api.ENV_CONFIG_DIR), api._cfg_cache, api._secrets_cache, parser._save_corpus_sample)
    assert after == before
    assert api._cfg_cache is before[1] and api._secrets_cache is before[2]
    assert list(project.rglob('*')) == []

def test_native_prompt_not_duplicated_and_refreshed():
    port = gateway(ROOT, ROOT.parent.parent.parent/'unused-chat-profile')
    prompts = import_module('python.substrate.llm.api.agent_prompts')
    expected = prompts.PRIMING_TEMPLATE.replace('{godot_version}','4.5').replace('{architecture}','arch').replace('{tree}','tree-one')
    assert port.system_prompt(tree='tree-one',architecture='arch',godot_version='4.5') == expected
    assert port.system_prompt(tree='tree-two',architecture='arch',godot_version='4.5') != expected

def test_bootstrap_exact_two_insertions_preserve_d65():
    from tests.py.composition_revision import before_d130
    current = before_d130('python/runtime/bootstrap.py')
    overlay_import = b'    from python.substrate.engine.structural_overlay import EngineOverlay\n'
    overlay_port = b'            "native_planner": NativePlanner(project_root, state, AGENT_DIR,\n                engine_overlay=EngineOverlay(project_root, state, AGENT_DIR)),\n'
    predecessor_port = b'            "native_planner": NativePlanner(project_root, state, AGENT_DIR),\n'
    assert current.count(overlay_import) == current.count(overlay_port) == 1
    current = current.replace(overlay_import,b'').replace(overlay_port,predecessor_port)
    planner_import = b'    from python.substrate.assistant.native_planner import NativePlanner\n'
    planner_port = b'            "native_planner": NativePlanner(project_root, state, AGENT_DIR),\n'
    assert current.count(planner_import) == current.count(planner_port) == 1
    current = current.replace(planner_import,b'').replace(planner_port,b'')
    assert len(current) == 8592 and current.count(b'\n') == 182 and current.count(b'\r\n') == 0
    assert hashlib.sha256(current).hexdigest() == 'd6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8'
    first = b'    from python.substrate.assistant.chat_gateway import ChatGateway\n'
    second = b'            "chat_gateway": ChatGateway(project_root, state, AGENT_DIR),\n'
    assert current.count(first) == current.count(second) == 1
    before = current.replace(first,b'').replace(second,b'')
    assert len(before) == 8451 and before.count(b'\n') == 180 and before.count(b'\r\n') == 0
    assert hashlib.sha256(before).hexdigest() == '2c0643473d82cf54355a34704afe784548506c3438db1d2b77221cbc5c096d41'
