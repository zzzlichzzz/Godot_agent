"""Live Godot verification for dialog, subscription, entry and fixture-import regressions."""
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]
GODOT_CANDIDATES = (
    r'D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe',
    r'D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64.exe',
)


def _find_godot():
    env = os.environ.get('GODOT_BIN', '').strip()
    if env and Path(env).is_file():
        return env
    for item in GODOT_CANDIDATES:
        if Path(item).is_file():
            return item
    return shutil.which('godot4') or shutil.which('godot')


def _inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def isolated_native_project(tmp_path):
    project = tmp_path / 'project'
    addon = project / 'addons/godot_agent'
    addon.mkdir(parents=True)
    shutil.copytree(ROOT / 'editor', addon / 'editor')
    shutil.copy2(ROOT / 'plugin.cfg', addon)
    fixtures = addon / 'fixtures'
    fixtures.mkdir()
    shutil.copy2(ROOT / 'fixtures/.gdignore', fixtures)
    untouched = fixtures / 'input.gd'
    untouched.write_text('extends Node\n', 'utf-8')
    source_corpus = ROOT / 'fixtures/projects/corpus/editing/paths_preview'
    shutil.copytree(source_corpus, fixtures / 'paths_preview')
    (project / 'import_control.gd').write_text('extends Node\n', 'utf-8')
    (project / 'project.godot').write_text(
        'config_version=5\n[application]\nconfig/name="bug-register-probe"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="bug-register-probe"\n'
        '[editor_plugins]\nenabled=PackedStringArray("res://addons/godot_agent/plugin.cfg",'
        '"res://addons/entry_probe/plugin.cfg")\n', 'utf-8')
    env = dict(os.environ, APPDATA=str(tmp_path / 'appdata'), LOCALAPPDATA=str(tmp_path / 'local'),
               XDG_DATA_HOME=str(tmp_path / 'data'), XDG_CONFIG_HOME=str(tmp_path / 'config'),
               XDG_CACHE_HOME=str(tmp_path / 'cache'), HOME=str(tmp_path / 'home'),
               BUGREG_PROFILE_ROOT=tmp_path.as_posix())
    return project, env, fixtures


@pytest.mark.needs_live
def test_ui_dialogs_signal_cleanup_and_entry_idempotency_live(tmp_path, isolated_native_project):
    godot = _find_godot()
    if not godot:
        pytest.skip('Godot 4.6 binary not installed')
    project, env, fixtures = isolated_native_project
    before = _inventory(fixtures)
    probe = tmp_path / 'probe_ui_bugs.gd'
    probe.write_text("""@tool
extends SceneTree

var _ran := false

func _init() -> void:
\tprocess_frame.connect(_run)

func _run() -> void:
\tif _ran:
\t\treturn
\t_ran = true
\tif process_frame.is_connected(_run):
\t\tprocess_frame.disconnect(_run)
\tif not ProjectSettings.globalize_path("user://").replace("\\\\", "/").begins_with(OS.get_environment("BUGREG_PROFILE_ROOT") + "/"):
\t\tpush_error("PROFILE_NOT_ISOLATED")
\t\tquit(5)
\t\treturn
\tvar failed := false
\t# BUG-001: StartScreen dialogs must not force exclusive conflicts
\tvar ScreenScript = load("res://addons/godot_agent/editor/native/agent_start_screen.gd")
\tvar screen = ScreenScript.new()
\tget_root().add_child(screen)
\tvar competing := AcceptDialog.new()
\tcompeting.exclusive = true
\tget_root().add_child(competing)
\tcompeting.popup_centered()
\tscreen._api_build_pick_dialog()
\tscreen._api_pick_dialog.popup_centered()
\tscreen._request_chat_delete("c1", "TestChat")
\tif not competing.visible or not screen._api_pick_dialog.visible or not screen._delete_dialog.visible:
\t\tpush_error("DIALOG_STILL_EXCLUSIVE")
\t\tfailed = true
\tscreen._delete_dialog.hide()
\tscreen._rebuild_ui()
\tawait process_frame
\tscreen._request_chat_delete("c2", "SecondChat")
\tif not is_instance_valid(screen._delete_dialog) or not screen._delete_dialog.visible:
\t\tpush_error("DIALOG_NOT_RECREATED")
\t\tfailed = true
\tget_root().remove_child(screen)
\tscreen.free()
\tcompeting.free()

\t# BUG-002: freed watched nodes must not trigger Parameter "obj" is null in signal teardown
\tvar SigScript = load("res://addons/godot_agent/editor/native/agent_integration_signals.gd")
\tvar sig = SigScript.new(null)
\tvar scene_root := Node.new()
\tvar child := Node.new()
\tscene_root.add_child(child)
\tget_root().add_child(scene_root)
\tsig._watch_subtree(scene_root)
\tscene_root.remove_child(child)
\tif child.renamed.get_connections().size() != 0:
\t\tpush_error("DETACHED_NODE_STILL_WATCHED")
\t\tfailed = true
\tscene_root.add_child(child)
\tif child.renamed.get_connections().size() != 1:
\t\tpush_error("REATTACHED_NODE_NOT_WATCHED_ONCE")
\t\tfailed = true
\tscene_root.free()
\tvar off_tree := Node.new()
\tsig._watch_subtree(off_tree)
\toff_tree.free()
\tsig._clear_node_watch()
\tsig.detach()

\tif failed:
\t\tquit(2)
\t\treturn
\tprint("LIVE_UI_BUGS_OK")
\tquit(0)
""", encoding='utf-8')
    res = subprocess.run([godot, '--headless', '--path', str(project), '--script', str(probe)], env=env,
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    combined = (res.stdout or '') + '\n' + (res.stderr or '')
    assert res.returncode == 0, combined
    assert 'LIVE_UI_BUGS_OK' in combined, combined
    assert 'Parameter "obj" is null' not in combined, combined
    assert 'exclusive child' not in combined, combined
    assert 'DIALOG_STILL_EXCLUSIVE' not in combined, combined

    entry_probe = project / 'addons/entry_probe'
    entry_probe.mkdir()
    (entry_probe / 'plugin.cfg').write_text('[plugin]\nname="Entry probe"\nscript="probe.gd"\n', 'utf-8')
    (entry_probe / 'probe.gd').write_text('''@tool
extends EditorPlugin

func _enter_tree() -> void:
	call_deferred("_probe")

func _probe() -> void:
	if not ProjectSettings.globalize_path("user://").replace("\\\\", "/").begins_with(OS.get_environment("BUGREG_PROFILE_ROOT") + "/"):
		push_error("EDITOR_PROFILE_NOT_ISOLATED")
		get_tree().quit(5)
		return
	var key := &"_godot_agent_entry_owner"
	var owner = Engine.get_meta(key) if Engine.has_meta(key) else null
	if not is_instance_valid(owner) or not is_instance_valid(owner._dock):
		get_tree().quit(3)
		return
	var dock = owner._dock
	var first_signals = owner._signals_integration
	owner._enter_tree()
	var duplicate = owner.get_script().new()
	add_child(duplicate)
	var ok: bool = owner._dock == dock and duplicate._dock == null and owner._integrations.size() == 2
	duplicate.free()
	ok = ok and Engine.get_meta(key) == owner and is_instance_valid(dock)
	owner._exit_tree()
	ok = ok and not Engine.has_meta(key) and owner._dock == null and first_signals.subscription_count() == 0
	await get_tree().process_frame
	ok = ok and not is_instance_valid(dock)
	owner._enter_tree()
	ok = ok and Engine.has_meta(key) and Engine.get_meta(key) == owner and is_instance_valid(owner._dock)
	ok = ok and owner._signals_integration.subscription_count() == 6 and owner._integrations.size() == 2
	for frame in range(500):
		await get_tree().process_frame
		if FileAccess.file_exists("res://import_control.gd.uid"):
			break
	ok = ok and FileAccess.file_exists("res://import_control.gd.uid")
	if ok:
		print("ENTRY_LIFECYCLE_OK")
	get_tree().quit(0 if ok else 4)
''', 'utf-8')
    ed = subprocess.run([godot, '--headless', '--editor', '--path', str(project), '--quit-after', '1500'], env=env,
                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
    ed_out = (ed.stdout or '') + '\n' + (ed.stderr or '')
    assert ed.returncode == 0, ed_out
    assert 'ENTRY_LIFECYCLE_OK' in ed_out, ed_out
    assert ed_out.count('[Godot Agent] \u0422\u043e\u0447\u043a\u0430 \u0432\u0445\u043e\u0434\u0430 agent_entry.gd \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u0430:') == 2, ed_out
    assert 'Parameter "obj" is null' not in ed_out, ed_out
    assert 'exclusive child' not in ed_out, ed_out
    assert 'SCRIPT ERROR' not in ed_out, ed_out
    assert _inventory(fixtures) == before
