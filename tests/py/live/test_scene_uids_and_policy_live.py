"""Live Godot 4.6.3 verification: zero invalid UID warnings and fail-closed policy UI."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = ROOT.parents[1]
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


def test_native_scenes_load_without_uid_warnings_and_policy_is_fail_closed(tmp_path):
    godot = _find_godot()
    if not godot:
        pytest.skip('Godot 4.6 binary not installed')
    probe = tmp_path / 'probe_uid_and_policy.gd'
    probe.write_text("""@tool
extends SceneTree

func _init() -> void:
\tvar scenes := [
\t\t"res://addons/godot_agent/editor/native/UserMessageCard.tscn",
\t\t"res://addons/godot_agent/editor/native/AgentMessageCard.tscn",
\t\t"res://addons/godot_agent/editor/native/DiffPreviewCard.tscn",
\t\t"res://addons/godot_agent/editor/native/PlanChecklistCard.tscn",
\t\t"res://addons/godot_agent/editor/native/PlanStepItem.tscn",
\t\t"res://addons/godot_agent/editor/native/ToolCallCard.tscn",
\t\t"res://addons/godot_agent/editor/native/agent_panel.tscn",
\t]
\tfor sp in scenes:
\t\tvar res = ResourceLoader.load(sp, "", ResourceLoader.CACHE_MODE_IGNORE)
\t\tif res == null:
\t\t\tpush_error("FAILED_LOAD:" + sp)
\t\t\tquit(2)
\t\t\treturn
\tvar panel_scn: PackedScene = ResourceLoader.load("res://addons/godot_agent/editor/native/agent_panel.tscn", "", ResourceLoader.CACHE_MODE_IGNORE)
\tvar panel = panel_scn.instantiate()
\tvar pf := FileAccess.open("user://godot_agent_policy.txt", FileAccess.WRITE)
\tpf.store_string("1")
\tpf.close()
\tvar part1 = load("res://addons/godot_agent/editor/native/agent_panel_part1.gd")
\tvar part4 = load("res://addons/godot_agent/editor/native/agent_panel_part4.gd")
\tpart1._load_policy_settings(panel)
\tif panel._allow_addons or panel._allow_self_edit:
\t\tpush_error("POLICY_NOT_FAIL_CLOSED_ON_LOAD")
\t\tpanel.free()
\t\tquit(3)
\t\treturn
\tpart1._on_allow_addons_toggled(panel, true)
\tpart1._on_allow_self_edit_toggled(panel, true)
\tif panel._allow_addons or panel._allow_self_edit:
\t\tpush_error("POLICY_ELEVATED_BY_TOGGLE")
\t\tpanel.free()
\t\tquit(4)
\t\treturn
\tpart4._on_settings_pressed(panel)
\tif panel._allow_addons_check == null or not panel._allow_addons_check.disabled or panel._allow_addons_check.button_pressed:
\t\tpush_error("ADDONS_CHECK_NOT_LOCKED")
\t\tpanel.free()
\t\tquit(5)
\t\treturn
\tif panel._allow_self_edit_check == null or not panel._allow_self_edit_check.disabled or panel._allow_self_edit_check.button_pressed:
\t\tpush_error("SELF_EDIT_CHECK_NOT_LOCKED")
\t\tpanel.free()
\t\tquit(6)
\t\treturn
\tpanel.free()
\tprint("LIVE_UID_AND_POLICY_OK")
\tquit(0)
""", encoding='utf-8')
    res = subprocess.run([godot, '--headless', '--path', str(PROJECT_ROOT), '--script', str(probe)],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    combined = (res.stdout or '') + '\n' + (res.stderr or '')
    assert res.returncode == 0, combined
    assert 'LIVE_UID_AND_POLICY_OK' in combined, combined
    assert 'invalid UID' not in combined, combined
    assert 'ext_resource' not in combined, combined
