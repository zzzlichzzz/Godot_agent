"""D90 input-only revision: exact old/new raw pins, unchanged business goldens."""
import hashlib

PATH='editor/core/resource_publication_observer.gd'
OLD_SHA='fa449727bf5b461b0cdff330bc4d60ced5a6a7765b665098486ea8bf05eb4706'
NEW_SHA='4e61db341215fc73142098265e243fb12a996f5a35348b3fcaa77faf9ed90f47'
OLD=b'extends "agent_resource_executor.gd"'
NEW=b'extends "res://addons/godot_agent/editor/native/agent_resource_executor.gd"'

def revised_fact(fact,before,current):
    if fact['path']!=PATH or fact['bytes']!=370 or fact['sha256']!=OLD_SHA:
        raise ValueError('Only the original D90 observer input may be revised')
    if len(before)!=370 or hashlib.sha256(before).hexdigest()!=OLD_SHA or before.count(OLD)!=1:
        raise ValueError('Original observer input drifted')
    if current!=before.replace(OLD,NEW,1) or len(current)!=409 or hashlib.sha256(current).hexdigest()!=NEW_SHA:
        raise ValueError('Observer change is not the authorized extends-only replacement')
    return dict(fact,bytes=409,sha256=NEW_SHA)


PANEL_PATH='editor/native/agent_panel.gd'
OLD_PANEL_SHA='a751d654842db5097a1dd0e712960a10d3e4272f20edd27bd4b7666f4edaafd7'
NEW_PANEL_SHA='c160c67762741a4b0d55596f4d4c1e44527e2e2c297b6013a61d2a99b8b3ac43'
_OLD_LOC=b'func _locale():\n\tAgentPanelPart1._locale(self)'
_NEW_LOC=b'func _locale():\n\treturn AgentPanelPart1._locale(self)'
_OLD_THM=b'func _T():\n\tAgentPanelPart1._T(self)'
_NEW_THM=b'func _T():\n\treturn AgentPanelPart1._T(self)'


def revised_panel_fact(fact,current):
    """D113 input-only revision for D112 locale/theme return fix; business goldens untouched."""
    if fact['path']!=PANEL_PATH or fact['bytes']!=82171 or fact['sha256']!=OLD_PANEL_SHA:
        raise ValueError('Only the original D112 agent_panel input may be revised')
    if current.count(_NEW_LOC)!=1 or current.count(_NEW_THM)!=1:
        raise ValueError('Panel change is not the authorized two-return replacement')
    reconstructed=current.replace(_NEW_LOC,_OLD_LOC,1).replace(_NEW_THM,_OLD_THM,1)
    if len(reconstructed)!=82171 or hashlib.sha256(reconstructed).hexdigest()!=OLD_PANEL_SHA:
        raise ValueError('Original agent_panel preimage drifted outside D112')
    if len(current)!=82185 or hashlib.sha256(current).hexdigest()!=NEW_PANEL_SHA:
        raise ValueError('Revised agent_panel bytes do not match D112 pin')
    return dict(fact,bytes=82185,sha256=NEW_PANEL_SHA)


D116_REVISIONS = {
    'editor/native/agent_locale.gd': (
        86142, 'cb3e9830e99ea68000ade0587419c2e92d36839797469b4edfe9c62493ba7ee8',
        86445, 'f7d63554cccdde0ea221b21b9e6f1cd1eb9f2edcc39b660c384e9910ff25e1a6',
        (
            ('\n\t"policy_http_locked": "В HTTP-режиме сервера изменение политики addons/ и self-edit через панель отключено (fail-closed).",'.encode('utf-8'), b''),
            ('\n\t"policy_http_locked": "In HTTP server mode, changing addons/ or self-edit policy from the panel is disabled (fail-closed).",'.encode('utf-8'), b''),
        ),
    ),
    'editor/native/agent_panel_part1.gd': (
        62618, '1c52619861f77bc975fa97423c8360826840a7435aca2b6f67f82e0aeecfbd84',
        62362, '415243360397cf925574ec4844eedaace4df510ea267337db8e241d07eb04053',
        (
            (b'static func _load_policy_settings(panel) -> void:\n\tpanel._allow_addons = false\n\tpanel._allow_self_edit = false\n',
             b'static func _load_policy_settings(panel) -> void:\n\tpanel._allow_addons = false\n\tif FileAccess.file_exists(POLICY_SETTING_FILE):\n\t\tvar p = FileAccess.open(POLICY_SETTING_FILE, FileAccess.READ)\n\t\tif p:\n\t\t\tpanel._allow_addons = p.get_as_text().strip_edges() == "1"\n\t\t\tp.close()\n\tpanel._allow_self_edit = false\n'),
            (b'static func _on_allow_addons_toggled(panel, pressed: bool) -> void:\n\tpanel._allow_addons = false\n\tif panel._allow_addons_check:\n\t\tpanel._allow_addons_check.set_pressed_no_signal(false)\n\tif pressed:\n\t\tpanel._notify(panel._t("policy_http_locked"), "status")\n\nstatic func _on_allow_self_edit_toggled(panel, pressed: bool) -> void:\n\tpanel._allow_self_edit = false\n\tif panel._allow_self_edit_check:\n\t\tpanel._allow_self_edit_check.set_pressed_no_signal(false)\n\tif panel._policy_warning_label:\n\t\tpanel._policy_warning_label.visible = false\n\tif pressed:\n\t\tpanel._notify(panel._t("policy_http_locked"), "status")\n',
             b'static func _on_allow_addons_toggled(panel, pressed: bool) -> void:\n\tif not pressed:\n\t\tpanel._allow_addons = false\n\t\tpanel._save_allow_addons_policy()\n\t\treturn\n\tpanel._policy_previous_allow_addons = panel._allow_addons\n\tpanel._allow_addons = false\n\tpanel._request_policy_enable("allow_addons")\n\nstatic func _on_allow_self_edit_toggled(panel, pressed: bool) -> void:\n\tif pressed:\n\t\tpanel._policy_previous_allow_self_edit = panel._allow_self_edit\n\t\tpanel._allow_self_edit = false\n\t\tpanel._request_policy_enable("allow_self_edit")\n\telse:\n\t\tpanel._allow_self_edit = false\n\tif panel._policy_warning_label:\n\t\tpanel._policy_warning_label.visible = panel._allow_self_edit\n'),
        ),
    ),
    'editor/native/agent_panel_part4.gd': (
        56836, 'adaeb41a5d985e92913443bccee50ff5bda26cdc0e59f6a192a0eb43031d8ec1',
        57133, 'cc7fd21b1678922899e0289375e0880f361c9de917bfe21165dd4470c3606cdf',
        (
            (b'panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip") + "\\n" + panel._t("policy_http_locked")\n\t\tpanel._allow_addons_check.button_pressed = false\n\t\tpanel._allow_addons_check.disabled = true',
             b'panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip")\n\t\tpanel._allow_addons_check.button_pressed = panel._allow_addons'),
            (b'panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip") + "\\n" + panel._t("policy_http_locked")\n\t\tpanel._allow_self_edit_check.button_pressed = false\n\t\tpanel._allow_self_edit_check.disabled = true',
             b'panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip")\n\t\tpanel._allow_self_edit_check.button_pressed = false'),
            (b'panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip") + "\\n" + panel._t("policy_http_locked")\n\t\tpanel._allow_addons_check.set_pressed_no_signal(false)\n\t\tpanel._allow_addons_check.disabled = true',
             b'panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip")\n\t\tpanel._allow_addons_check.set_pressed_no_signal(panel._allow_addons)'),
            (b'panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip") + "\\n" + panel._t("policy_http_locked")\n\t\tpanel._allow_self_edit_check.set_pressed_no_signal(false)\n\t\tpanel._allow_self_edit_check.disabled = true',
             b'panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip")\n\t\tpanel._allow_self_edit_check.set_pressed_no_signal(panel._allow_self_edit)'),
        ),
    ),
}


def revised_d116_fact(fact, current):
    """D116 input-only revision for fail-closed policy/locale updates; goldens untouched."""
    spec = D116_REVISIONS.get(fact['path'])
    if spec is None:
        raise ValueError('Not an authorized D116 input: ' + str(fact.get('path')))
    old_bytes, old_sha, new_bytes, new_sha, replacements = spec
    if fact['bytes'] != old_bytes or fact['sha256'] != old_sha:
        raise ValueError('Only the original D116 preimage input may be revised')
    reconstructed = current
    for new_chunk, old_chunk in replacements:
        if reconstructed.count(new_chunk) != 1:
            raise ValueError('Expected unique D116 chunk in ' + fact['path'])
        reconstructed = reconstructed.replace(new_chunk, old_chunk, 1)
    if len(reconstructed) != old_bytes or hashlib.sha256(reconstructed).hexdigest() != old_sha:
        raise ValueError('Original D116 preimage drifted in ' + fact['path'])
    if len(current) != new_bytes or hashlib.sha256(current).hexdigest() != new_sha:
        raise ValueError('Revised D116 bytes do not match pin in ' + fact['path'])
    return dict(fact, bytes=new_bytes, sha256=new_sha)
