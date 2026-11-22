"""SEC-T1-OVERLAY: all refused before process invocation or project effects."""
import json
from pathlib import Path
import pytest
from python.kernel.errors import AppError

ROOT = Path(__file__).resolve().parents[3]

def fixture(tmp_path, state=None):
    from python.substrate.engine.structural_overlay import EngineOverlay
    project = tmp_path / 'project'; project.mkdir(exist_ok=True)
    (project / 'project.godot').write_bytes(b'config_version=5\n')
    (project / 'level.tscn').write_bytes(b'[gd_scene format=3]\n\n[node name="Root" type="Node"]\n')
    calls = []
    def runner(argv, **options):
        calls.append(argv)
        return type('Result', (), dict(returncode=7, stdout=b'D:/private/secret traceback'))()
    return EngineOverlay(project, state or tmp_path / 'state', ROOT, godot_bin=tmp_path / 'godot.exe', runner=runner), project, calls

def action():
    return dict(action='edit_scene', scene='res://level.tscn', operations=[])

@pytest.mark.parametrize('relative', ['../outside.tscn', 'res://addons/secret.tscn', 'res://.agent_history/secret.tscn'])
def test_forbidden_target_never_launches_engine(tmp_path, relative):
    adapter, project, calls = fixture(tmp_path)
    request = action(); request['scene'] = relative
    with pytest.raises(AppError) as caught: adapter.prepare(request)
    assert caught.value.kind == 'denied' and not calls

@pytest.mark.parametrize('reference', ['D:/private/include.gdshaderinc', 'user://include.gdshaderinc',
                                      'res://../outside/include.gdshaderinc', 'res://addons/include.gdshaderinc',
                                      '../outside/include.gdshaderinc', '..\\outside\\include.gdshaderinc'])
def test_shader_include_is_policy_checked_before_engine_io(tmp_path, reference):
    adapter, project, calls = fixture(tmp_path)
    (project/'shader.gdshader').write_text('shader_type spatial;\n#include "'+reference+'"\n', encoding='utf-8')
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'denied' and not calls

def test_project_owned_state_is_refused_before_creation(tmp_path):
    adapter, project, calls = fixture(tmp_path, tmp_path / 'project' / 'scratch')
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'denied' and not calls and not (project / 'scratch').exists()

@pytest.mark.parametrize('payload', [b'[ext_resource type="Script" path="res://evil.gd" id="1"]\n', b'script = ExtResource("1")\n'])
def test_script_bearing_asset_refused_before_import(tmp_path, payload):
    adapter, project, calls = fixture(tmp_path)
    (project / 'level.tscn').write_bytes(payload)
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'denied' and not calls

def test_script_autoload_refused_before_import(tmp_path):
    adapter, project, calls = fixture(tmp_path)
    (project / 'project.godot').write_bytes(b'config_version=5\n[autoload]\nDanger="*res://evil.gd"\n')
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'denied' and not calls

def test_engine_diagnostics_are_not_a_client_message(tmp_path):
    adapter, project, calls = fixture(tmp_path)
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'unavailable'
    assert 'private' not in str(caught.value) and 'traceback' not in str(caught.value)
    assert len(calls) == 1

def test_relative_executable_is_not_a_shell_command(tmp_path):
    adapter, project, calls = fixture(tmp_path)
    adapter.godot_bin = 'godot --execute injected'
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'unavailable' and not calls

def test_absent_executable_has_no_implicit_discovery(tmp_path, monkeypatch):
    monkeypatch.delenv('GODOT_AGENT_GODOT_BIN', raising=False)
    adapter, project, calls = fixture(tmp_path)
    adapter.godot_bin = ''
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'unavailable' and not calls

@pytest.mark.parametrize('payload', [
    b'[ext_resource type="Resource" path="res://../outside/secret.tres" id="1"]\n',
    b'[ext_resource type="Resource" path="D:/private/secret.tres" id="1"]\n',
    b'[ext_resource type="Resource" path="user://secret.tres" id="1"]\n',
    b'[ext_resource type="Resource" path="res://addons/secret.tres" id="1"]\n',
    b'[ext_resource type="Scrip\\u0074" path="res://evil.\\u0067d" id="1"]\n',
    b'"script" = ExtResource("1")\n',
])
def test_external_or_encoded_engine_reference_never_imported(tmp_path, payload):
    adapter, project, calls = fixture(tmp_path)
    (project / 'level.tscn').write_bytes(payload)
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'denied' and not calls


@pytest.mark.parametrize('reference',['../owned-plugin/plugin.cfg','..\\owned-plugin\\plugin.cfg','./../owned-plugin/plugin.cfg','..'])
def test_relative_editor_plugin_reference_is_checked_before_engine(tmp_path,reference):
    adapter,project,calls=fixture(tmp_path)
    (project/'project.godot').write_text('config_version=5\n[editor_plugins]\nenabled=PackedStringArray("'+reference+'")\n',encoding='utf-8')
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind=='denied' and not calls


@pytest.mark.parametrize('extension',['gd','gdc'])
def test_relative_executable_resource_reference_is_checked_before_engine(tmp_path,extension):
    adapter,project,calls=fixture(tmp_path)
    (project/'level.tscn').write_text('[gd_scene format=3]\n[ext_resource type="Resource" path="../outside/owned.'+extension+'" id="1"]\n[node name="Root" type="Node"]\n',encoding='utf-8')
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind=='denied' and not calls
