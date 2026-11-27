"""New adapter cases from measured native A7; no old test code/network."""
import hashlib
import json
from pathlib import Path
import pytest
from python.kernel.errors import AppError

ROOT = Path(__file__).resolve().parents[3]
BASE = b'[gd_resource type="StandardMaterial3D" format=3 uid="uid://cyncsb"]\n\n[resource]\n'
AFTER = BASE + b'roughness = 0.5\n'

@pytest.fixture
def setup(tmp_path):
    from python.substrate.engine.structural_overlay import EngineOverlay
    project, state = tmp_path / 'project', tmp_path / 'state'
    project.mkdir(); state.mkdir()
    (project / 'project.godot').write_bytes(b'config_version=5\n')
    (project / 'material.tres').write_bytes(BASE)
    calls = []
    def runner(argv, **options):
        calls.append((argv, options))
        if '--import' not in argv:
            overlay = Path(argv[argv.index('--path') + 1])
            (overlay / 'material.tres').write_bytes(AFTER)
            Path(argv[-1]).write_text(json.dumps(dict(preview=dict(ok=True, semantic_hash='semantic', dependency_fingerprint='dependency'),
                result=dict(ok=True, resource_hash=hashlib.sha256(AFTER).hexdigest()))), encoding='utf-8')
        return type('Result', (), dict(returncode=0, stdout=b''))()
    adapter = EngineOverlay(project, state, ROOT, godot_bin=tmp_path / 'godot.exe', runner=runner)
    return adapter, project, state, calls

def action():
    return dict(action='edit_resource', resource='res://material.tres', operations=[dict(op='set_property', target=[], property='roughness', value={'type':'float','value':0.5})])

def test_overlay_returns_raw_target_delta_without_project_effects(setup):
    adapter, project, state, calls = setup
    files, warnings = adapter.prepare(action())
    assert files == [dict(path='res://material.tres', before_bytes=BASE, after_bytes=AFTER)]
    assert warnings == [] and (project / 'material.tres').read_bytes() == BASE
    assert not list(state.iterdir()) and len(calls) == 2

def test_owned_editor_import_precedes_configured_harness(setup):
    adapter, project, state, calls = setup
    adapter.prepare(action())
    assert '--import' in calls[0][0] and '--script' in calls[1][0]
    for argv, options in calls:
        assert '--headless' in argv and '--editor' in argv
        assert options['shell'] is False and options['timeout'] <= 120
        scratch = Path(argv[argv.index('--path') + 1])
        assert scratch.is_relative_to(state) and not scratch.is_relative_to(project)


def test_relative_and_transitive_dependencies_only(setup):
    adapter, project, _, _ = setup
    assets=project/'assets';assets.mkdir()
    (assets/'object.tscn').write_bytes(b'[gd_scene format=3]\n[ext_resource type="Resource" path="palette.tres" id="1"]\n')
    (assets/'palette.tres').write_bytes(b'[gd_resource type="Resource" format=3]\n[ext_resource type="Texture2D" path="res://icon.png" id="1"]\n')
    (project/'icon.png').write_bytes(b'png')
    request=dict(action='edit_scene',scene='res://assets/object.tscn',operations=[])
    assert set(adapter._capture(request,'assets/object.tscn'))=={'project.godot','assets/object.tscn','assets/palette.tres','icon.png'}

def test_native_harness_uses_actual_prepare_expected_hash_and_fingerprints():
    harness = ROOT / 'editor/core/structural_overlay.gd'
    assert harness.is_file(), 'missing production primitive harness'
    text = harness.read_text(encoding='utf-8')
    assert 'executor.configure(plugin)' in text
    assert 'executor.prepare(action, expected)' in text and 'executor.execute(action, expected)' in text
    assert 'preview.get("semantic_hash"' in text and 'preview.get("dependency_fingerprint"' in text
    assert 'get_buffer' in text and 'HashingContext.HASH_SHA256' in text

def test_default_composition_injects_one_overlay(tmp_path):
    from python.runtime.bootstrap import default_ports
    project = tmp_path / 'project'; project.mkdir()
    ports = default_ports(str(project), 'test', state_dir=str(tmp_path / 'state'))
    assert ports['native_planner']._engine_overlay is not None

def test_native_planner_returns_file_list_not_overlay_tuple(setup):
    import sys
    from unittest.mock import patch
    with patch.dict(sys.modules):
        from python.substrate.assistant.native_planner import NativePlanner
        adapter, project, state, calls = setup
        planner = NativePlanner(project, state, ROOT, engine_overlay=adapter)
        prepared = planner.prepare(action())
        assert prepared['files'] == [dict(path='res://material.tres', before_bytes=BASE, after_bytes=AFTER)]
        assert prepared['warnings'] == []

def test_new_native_observer_restores_process_registry(setup):
    import ast
    import sys
    from unittest.mock import patch
    paths = ('python/substrate/llm/runtime_bindings.py', 'python/substrate/assistant/native_bindings.py')
    names = ['minilich', 'minilich.ml_data', 'minilich.ml_project_index']
    for path in paths:
        tree = ast.parse((ROOT/path).read_text(encoding='utf-8'))
        bindings = next(node.value for node in tree.body if isinstance(node,ast.Assign)
                        and any(isinstance(target,ast.Name) and target.id=='BINDINGS' for target in node.targets))
        names.extend(name for name,_ in ast.literal_eval(bindings))
    with patch.dict(sys.modules):
        for name in names: sys.modules.pop(name,None)
        before = dict(sys.modules)
        test_native_planner_returns_file_list_not_overlay_tuple(setup)
        assert sys.modules == before

def test_stale_original_after_engine_is_a_conflict(setup):
    adapter, project, state, calls = setup
    original = adapter.runner
    def changed(argv, **options):
        result = original(argv, **options)
        if '--import' not in argv: (project / 'material.tres').write_bytes(b'foreign')
        return result
    adapter.runner = changed
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'conflict'
    assert (project / 'material.tres').read_bytes() == b'foreign'

def test_semantic_native_refusal_does_not_return_a_plan(setup):
    adapter, project, state, calls = setup
    def refused(argv, **options):
        if '--import' not in argv:
            Path(argv[-1]).write_text(json.dumps(dict(preview=dict(ok=False, code='property_denied'), result={})), encoding='utf-8')
        return type('Result', (), dict(returncode=0, stdout=b''))()
    adapter.runner = refused
    with pytest.raises(AppError) as caught: adapter.prepare(action())
    assert caught.value.kind == 'invalid_input'
    assert caught.value.details['native_code'] == 'property_denied'
    assert (project / 'material.tres').read_bytes() == BASE

def test_untagged_sdk_refuses_real_project_before_execute():
    for name in ('scene', 'resource', 'project_settings'):
        path = ROOT / ('editor/native/agent_' + name + '_executor.gd')
        assert path.is_file(), 'missing production guarded SDK'
        text = path.read_text(encoding='utf-8')
        start = text.index('func execute(')
        assert 'if not _t1_owned_overlay():' in text[start:start+400]
        assert 'rebuild_funnel_required' in text[start:start+400]
