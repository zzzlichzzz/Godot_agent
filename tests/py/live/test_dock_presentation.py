"""Render the dock's home and a synthetic conversation in two isolated editor palettes."""
import os
import subprocess

import pytest

from .test_ui_bugs_live import _find_godot, isolated_native_project


PROBE = '''@tool
extends EditorPlugin

const NATIVE := "res://addons/godot_agent/editor/native/"
var clicked: Array[String] = []
var _view
var _current_chat_id := "preview"

func _enter_tree() -> void:
    call_deferred("measure")

func measure() -> void:
    var viewport := SubViewport.new()
    viewport.disable_3d = true
    viewport.size = Vector2i(250, 640)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    add_child(viewport)
    # A standalone viewport has a grey clear colour; an actual dock sits over the editor.
    var backdrop := ColorRect.new()
    backdrop.color = EditorInterface.get_editor_theme().get_color("base_color", "Editor")
    viewport.add_child(backdrop)
    backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var surface := PanelContainer.new()
    surface.theme = EditorInterface.get_editor_theme()
    surface.add_theme_stylebox_override("panel", surface.theme.get_stylebox("panel", "TabContainer"))
    viewport.add_child(surface)
    surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var margin := MarginContainer.new()
    for edge in ["left", "top", "right", "bottom"]:
        margin.add_theme_constant_override("margin_" + edge, 8)
    surface.add_child(margin)
    load(NATIVE + "agent_locale.gd").set_lang("ru")
    var screen = load(NATIVE + "agent_start_screen.gd").new()
    margin.add_child(screen)
    screen.set_server_running(true)
    var theme_service = screen._T()
    var light := OS.get_environment("PALETTE") == "light"
    var bg: Color = theme_service.color("bg_1")
    var fg: Color = theme_service.color("dim")
    var l1 := bg.srgb_to_linear().get_luminance()
    var l2 := fg.srgb_to_linear().get_luminance()
    var contrast := (maxf(l1, l2) + 0.05) / (minf(l1, l2) + 0.05)
    var ok: bool = (bg.get_luminance() > 0.5) == light and contrast >= 4.5
    screen.chats_tab_requested.connect(func(): clicked.append("chats"))
    screen.sites_tab_requested.connect(func(): clicked.append("sites"))
    screen.api_tab_requested.connect(func(): clicked.append("api"))
    var rows: Array = [screen.find_child("OpenHistory", true, false), screen.find_child("BrowserChat", true, false), screen._api_key_btn]
    for width in [250, 420]:
        viewport.size.x = width
        for i in 8:
            await get_tree().process_frame
        ok = within_width(screen, width) and ok
        ok = ok and rows[0].global_position.y < viewport.size.y / 2.0
        ok = await capture(viewport, "home", width) and ok
    for button in rows:
        ok = ok and button.icon != null and button.focus_mode == Control.FOCUS_ALL
        button.pressed.emit()
    ok = ok and clicked == ["chats", "sites", "api"]
    screen.hide()
    var conversation := VBoxContainer.new()
    margin.add_child(conversation)
    _view = load(NATIVE + "agent_chat_view.gd").new()
    add_child(_view)
    _view.setup(conversation)
    _view.add_user_message("Где сцена подписывается на сигнал?")
    var text := '[b]Найду места подключения[/b]\\nПроверю скрипты проекта и покажу строки, где встречается [code]collected[/code].'
    var args := '{"action":"search_project","query":"collected","only_exts":[lb]"gd"[rb]}'
    _view.add_agent_message(text + "\\n" + args)
    var card = _view._chat_container.get_child(-1)
    var toggle = card.find_child("PayloadToggle", true, false)
    var detail = card.find_child("PayloadText", true, false)
    if not toggle or not detail:
        push_error("Missing transcript disclosure")
        get_tree().quit(2)
        return
    ok = ok and not detail.visible and toggle.focus_mode == Control.FOCUS_ALL
    toggle.button_pressed = true
    ok = ok and detail.visible and '"only_exts":["gd"]' in detail.get_parsed_text()
    toggle.button_pressed = false
    ok = ok and card._copy_text().ends_with('"only_exts":["gd"]}') and card.get_text().ends_with(args)
    ok = ok and not card.rollback_btn.visible and not card.copy_btn.disabled
    load(NATIVE + "agent_read_consent.gd").offer(self, {"chat_id": _current_chat_id,
        "action": {"action": "search_project", "query": "collected", "only_exts": ["gd"]}})
    var composer := HBoxContainer.new()
    conversation.add_child(composer)
    var field := TextEdit.new()
    field.placeholder_text = "Сообщение…"
    field.custom_minimum_size.y = 60
    field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    composer.add_child(field)
    theme_service.style_input(field)
    var send := Button.new()
    send.text = "Отправить"
    composer.add_child(send)
    theme_service.style_button(send, "accent", false)
    send.icon = theme_service.icon(&"ArrowRight")
    for width in [250, 420]:
        viewport.size.x = width
        for i in 8:
            await get_tree().process_frame
        ok = within_width(conversation, width) and ok
        ok = await capture(viewport, "chat", width) and ok
    var long_answer := ("Длинный ответ со строками [code]GDScript[/code].\\n").repeat(50)
    card.setup(long_answer)
    ok = ok and not toggle.visible and card.expand_btn.visible and not card.expand_btn.disabled
    card.expand_btn.pressed.emit()
    ok = ok and not card.content.fit_content and card.get_text() == long_answer
    card.expand_btn.pressed.emit()
    card.setup("JSON?\\n{broken}")
    ok = ok and not toggle.visible and "{broken}" in card.content.get_parsed_text()
    card.setup("")
    card.append_text(text + "\\n" + args)
    ok = ok and not toggle.visible and "search_project" in card.content.get_parsed_text()
    print("DOCK_LAYOUT_OK" if ok else "DOCK_LAYOUT_FAILED", " bg=", bg, " contrast=", contrast, " actions=", clicked)
    get_tree().quit(0 if ok else 2)

func within_width(parent: Control, width: int) -> bool:
    for node in parent.find_children("*", "Control", true, false):
        if node.is_visible_in_tree():
            var rect: Rect2 = node.get_global_rect()
            if rect.position.x < 0 or rect.end.x > width + 1:
                push_error("Dock overflow: %s %s at %s" % [node.get_path(), rect, width])
                return false
    return true

func capture(viewport: SubViewport, page: String, width: int) -> bool:
    if OS.get_environment("CAPTURE") != "1":
        return true
    RenderingServer.force_draw(false)
    var image := viewport.get_texture().get_image()
    return image.save_png(OS.get_environment("PREVIEW").path_join("%s-%d.png" % [page, width])) == OK
'''


@pytest.mark.needs_live
@pytest.mark.parametrize('palette', ['dark', 'light'])
def test_dock_layout_and_navigation(palette, isolated_native_project, tmp_path):
    godot = _find_godot()
    if not godot:
        pytest.skip('Godot 4.6 binary not installed')
    project, env, _ = isolated_native_project
    settings = project / 'project.godot'
    settings.write_text('config_version=5\n', 'utf-8')
    check = project / 'addons/check'
    check.mkdir()
    (check / 'plugin.cfg').write_text('[plugin]\nname="Layout"\nscript="check.gd"\n', 'utf-8')
    (check / 'check.gd').write_text(PROBE, 'utf-8')
    profile = tmp_path / 'appdata/Godot'
    profile.mkdir(parents=True)
    preset = 'Light' if palette == 'light' else 'Default'
    (profile / 'editor_settings-4.6.tres').write_text('[gd_resource type="EditorSettings" format=3]\n\n'
        f'[resource]\ninterface/theme/color_preset = "{preset}"\n'
        'interface/theme/follow_system_theme = false\ninterface/editor/display_scale = 2\n', 'utf-8')
    # The live fixture redirects all profiles. XDG config is the equivalent on Linux.
    xdg = tmp_path / 'config/godot'
    xdg.mkdir(parents=True, exist_ok=True)
    (xdg / 'editor_settings-4.6.tres').write_bytes((profile / 'editor_settings-4.6.tres').read_bytes())
    # Resolve global card classes and scene imports before running the probe plugin.
    subprocess.run([godot, '--headless', '--import', '--path', str(project)], env=env,
                   capture_output=True, check=True, timeout=75)
    settings.write_text('config_version=5\n[editor_plugins]\n'
        'enabled=PackedStringArray("res://addons/check/plugin.cfg")\n', 'utf-8')
    capture = os.environ.get('GODOT_AGENT_DOCK_CAPTURE') == '1'
    flags = ['--rendering-method', 'gl_compatibility'] if capture else ['--headless']
    proc = subprocess.run([godot, *flags, '--editor', '--path', str(project), '--quit-after', '900'],
        env=dict(env, PALETTE=palette, PREVIEW=str(tmp_path), CAPTURE=str(int(capture))),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=75)
    log = proc.stdout + proc.stderr
    assert proc.returncode == 0 and 'DOCK_LAYOUT_OK' in log and 'SCRIPT ERROR' not in log, log
