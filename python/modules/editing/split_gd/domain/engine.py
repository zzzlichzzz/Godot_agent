"""One snapshot's native base -> Control -> fallback method/property sets."""
FALLBACK_METHODS = {
    'get_tree', 'get_parent', 'get_node', 'get_node_or_null', 'get_children',
    'get_child', 'get_child_count', 'get_index', 'has_node', 'find_child',
    'add_child', 'remove_child', 'move_child', 'queue_free', 'is_inside_tree',
    'is_node_ready', 'set_deferred', 'call_deferred', 'set', 'get', 'call',
    'has_method', 'connect', 'disconnect', 'is_connected', 'emit_signal',
    'add_to_group', 'remove_from_group', 'is_in_group', 'get_meta', 'set_meta',
    'has_meta', 'remove_meta', 'grab_focus', 'release_focus', 'has_focus',
    'accept_event', 'get_viewport', 'get_window', 'is_visible_in_tree', 'get_path',
    'get_scene_file_path', 'duplicate', 'get_script', 'set_script', 'get_class',
    'is_class', 'notification', 'notify_property_list_changed', 'set_process',
    'set_physics_process', 'set_process_input', 'set_process_unhandled_input',
    'move_to_front', 'show', 'hide', 'add_theme_color_override',
    'add_theme_constant_override', 'add_theme_font_override',
    'add_theme_font_size_override', 'add_theme_stylebox_override',
    'remove_theme_color_override', 'remove_theme_constant_override',
    'remove_theme_font_override', 'remove_theme_font_size_override',
    'remove_theme_stylebox_override', 'get_theme_color', 'get_theme_constant',
    'get_theme_font', 'get_theme_font_size', 'get_theme_stylebox', 'has_theme_color',
    'has_theme_constant', 'has_theme_font', 'has_theme_font_size', 'has_theme_stylebox',
    'get_theme_default_font', 'get_theme_default_font_size', 'force_update_transform',
}
FALLBACK_PROPS = {
    'visible', 'position', 'size', 'rotation', 'scale', 'pivot_offset', 'modulate',
    'self_modulate', 'custom_minimum_size', 'mouse_filter', 'focus_mode',
    'tooltip_text', 'top_level', 'clip_contents', 'layout_mode', 'anchors_preset',
    'anchor_left', 'anchor_right', 'anchor_top', 'anchor_bottom', 'offset_left',
    'offset_right', 'offset_top', 'offset_bottom', 'size_flags_horizontal',
    'size_flags_vertical', 'theme_type_variation', 'alignment', 'autowrap_mode',
    'text', 'bbcode_enabled', 'scroll_following', 'selection_enabled',
    'context_menu_enabled', 'editable', 'wrap_mode', 'placeholder_text', 'pressed',
    'button_pressed', 'disabled', 'flat', 'icon', 'name', 'owner',
}


def api(classes, base_class='Control'):
    if classes:
        for start in (base_class, 'Control'):
            methods, props, seen, current, guard = set(), set(), set(), start, 0
            while current and current not in seen and guard < 30:
                entry = classes.get(current) or {}
                methods.update(entry.get('methods') or {})
                props.update(entry.get('properties') or [])
                seen.add(current)
                current = entry.get('inherits')
                guard += 1
            if methods:
                return methods, props
    return set(FALLBACK_METHODS), set(FALLBACK_PROPS)
