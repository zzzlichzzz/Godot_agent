"""BUG-004/010/011: native agent_panel locale/theme wrappers must return scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT.parents[1]
GODOT_CANDIDATES = (
    Path(r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe"),
    Path(r"D:\vajno\Godot\Godot v4.6\Godot_v4.6-stable_win64_console.exe"),
)


def _godot_binary():
    chosen = os.environ.get("GODOT_BIN", "")
    if chosen and Path(chosen).is_file():
        return Path(chosen)
    for path in GODOT_CANDIDATES:
        if path.is_file():
            return path
    found = shutil.which("godot") or shutil.which("godot4")
    return Path(found) if found else None


def test_agent_panel_locale_and_theme_wrappers_return_part_results():
    src = (ROOT / "editor/native/agent_panel.gd").read_text("utf-8")
    loc = re.search(r"func _locale\(\):\n\t([^\n]+)", src)
    thm = re.search(r"func _T\(\):\n\t([^\n]+)", src)
    assert loc and loc.group(1).strip() == "return AgentPanelPart1._locale(self)"
    assert thm and thm.group(1).strip() == "return AgentPanelPart1._T(self)"


@pytest.mark.needs_live
def test_real_godot_panel_locale_theme_uid_and_sites_render(tmp_path):
    binary = _godot_binary()
    if binary is None:
        pytest.skip("Godot binary unavailable")
    probe = tmp_path / "panel_locale_probe.gd"
    out_file = tmp_path / "probe_result.json"
    probe.write_text(f"""extends SceneTree

var _ran := false

func _init() -> void:
\tprocess_frame.connect(_run)

func _run() -> void:
\tif _ran:
\t\treturn
\t_ran = true
\tvar PanelScript = load("res://addons/godot_agent/editor/native/agent_panel.gd")
\tvar StatusScene = load("res://addons/godot_agent/editor/native/AgentStatusBar.tscn")
\tvar ScreenScript = load("res://addons/godot_agent/editor/native/agent_start_screen.gd")
\tvar panel = PanelScript.new()
\tvar loc = panel._locale()
\tvar theme = panel._T()
\tvar ok = loc != null and theme != null
\tvar hint = ""
\tvar opened = ""
\tvar upd = ""
\tif ok:
\t\thint = panel._t("api_chat_hint") % ["OpenRouter", "gpt-4o"]
\t\topened = panel._t("chat_opened") % "SyntheticChat"
\t\tupd = panel._t("update_current_version") % "1.0.0"
\tvar status_bar = StatusScene.instantiate() if StatusScene != null else null
\tvar screen = ScreenScript.new()
\tget_root().add_child(screen)
\tscreen.set_sites([
\t\t{{"id": "aistudio", "name": "Google AI Studio", "url": "https://aistudio.google.com"}},
\t\t{{"id": "deepseek", "name": "DeepSeek", "url": "https://chat.deepseek.com"}},
\t\t{{"id": "qwen", "name": "Qwen", "url": "https://chat.qwen.ai"}},
\t])
\tvar site_buttons := []
\tfor child in screen._sites_list.get_children():
\t\tif child is Button:
\t\t\tsite_buttons.append(child.text)
\tvar payload = {{
\t\t"loc_nonnull": loc != null,
\t\t"theme_nonnull": theme != null,
\t\t"hint": hint,
\t\t"opened": opened,
\t\t"upd": upd,
\t\t"status_bar_ok": status_bar != null,
\t\t"site_buttons": site_buttons,
\t}}
\tvar f = FileAccess.open({json.dumps(str(out_file))}, FileAccess.WRITE)
\tf.store_string(JSON.stringify(payload))
\tf.close()
\tvar status_ok: bool = status_bar != null
\tif status_ok:
\t\tstatus_bar.free()
\tget_root().remove_child(screen)
\tscreen.free()
\tpanel.free()
\tquit(0 if ok and status_ok and site_buttons.size() >= 3 else 1)
""", encoding="utf-8")

    run = subprocess.run(
        [str(binary), "--headless", "--path", str(PROJECT), "-s", str(probe)],
        cwd=str(PROJECT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert out_file.is_file(), run.stdout
    data = json.loads(out_file.read_text("utf-8"))
    assert run.returncode == 0, (json.dumps(data, ensure_ascii=False), run.stdout)
    assert data["loc_nonnull"] is True, data
    assert data["theme_nonnull"] is True, data
    assert data["status_bar_ok"] is True, data
    assert "uid://" not in (run.stdout or "").lower() or "invalid uid" not in (run.stdout or "").lower(), run.stdout
    assert len(data["site_buttons"]) >= 3, data
    assert {"Google AI Studio", "DeepSeek", "Qwen"} <= set(data["site_buttons"]), data
    assert "OpenRouter" in data["hint"] and "gpt-4o" in data["hint"]
    assert "SyntheticChat" in data["opened"]
    assert "1.0.0" in data["upd"]
