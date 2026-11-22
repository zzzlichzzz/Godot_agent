"""New UI transport/composition contracts; actual Godot evidence is separate."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def panel():
    path=ROOT/'editor/t1_panel.gd'
    assert path.is_file(), 'missing production T1 panel'
    return path.read_text(encoding='utf-8')

def test_confirm_and_reject_bind_both_preview_identifiers():
    text=panel()
    assert '"approved": true, "plan_id": _pending.get("plan_id", ""), "digest": _pending.get("digest", "")' in text
    assert '"approved": false, "plan_id": _pending.get("plan_id", ""), "digest": _pending.get("digest", "")' in text

def test_root_plugin_composes_accepted_lifecycle_and_new_panel():
    text=(ROOT/'plugin.gd').read_text(encoding='utf-8')
    assert 'res://addons/godot_agent/editor/core/lifecycle.gd' in text
    assert 'res://addons/godot_agent/editor/t1_panel.gd' in text
    assert 'add_control_to_dock' in text and 'T1_PLUGIN_READY' in text

def test_panel_external_profile_gate_precedes_token_read():
    text=panel()
    assert text.index('profile.is_absolute_path()') < text.index('godot_agent_token.txt')
    assert 'profile.to_lower().begins_with(project.to_lower() + "/")' in text
    assert 'directory.is_link("godot_agent_token.txt")' in text

def test_failed_rollback_keeps_last_journal_and_never_claims_success():
    text=panel(); start=text.index('elif route == "/chat/rollback":'); tail=text[start:]
    assert tail.index('parsed.get("state", "") != "ROLLED_BACK"') < tail.index('_last = {}')
    assert 'parsed.get("ok", true) != true' in text

def test_native_entry_and_updater_are_inactive_configuration():
    assert 'script="plugin.gd"' in (ROOT/'plugin.cfg').read_text(encoding='utf-8')
    assert 'agent_entry.gd' in (ROOT/'editor/native/plugin.cfg').read_text(encoding='utf-8')
    assert 'agent_updater' not in (ROOT/'plugin.gd').read_text(encoding='utf-8')
