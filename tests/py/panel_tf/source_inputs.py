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


# Preimages can be recovered with `git show 85c0dabe25d874a29c4099d5e673b864cdf67655:<path>`.
# Keep the original business expectations and verify both byte identities without Git at runtime.
BUG_REGISTER_REVISIONS = {
    'editor/native/agent_entry.gd': (
        24233, 'fea207f0296d429d372a9465c854cee3480b97da2ca5d09150357460a832f31f',
        24968, 'aef2894abe92e9dad6ad9e562be7ca3edf8fb3ae6beb120298c9f69da4871f8b',
    ),
    'editor/native/agent_integration_signals.gd': (
        10061, '4b909fad1fc21ca4a43fc8324b6778c246d5b13ee67623a510e745f14dd97983',
        9352, 'c1139d7c93d9e630bba48b8daced2f61d57853e3054367e7e172ddfec18fe06e',
    ),
    'editor/native/agent_start_screen.gd': (
        203876, '925622c65e3fe4962a9e3f9b36146e4d1a26d45abc120bd257e3ce8391cd6e6a',
        203949, 'd09926528fb9281f63d426e1dabbbd42098d26d66dc026e79eabcf9a912312c3',
    ),
}

# D122 changes presentation and read controls, not native GDScript extraction.
D122_REVISIONS = {
    'editor/native/agent_chat_view.gd': (
        45595, 'bd569440f801db480851e5873c23bd80a7d350d0083d205d5ef27b9ec8490ec8',
        45467, '0ee7e4747293b1006cc8942ec868dc9d27bd6a1d125fa1336984d886347c7196'),
    'editor/native/agent_panel_part2.gd': (
        63440, '8817af1232c73b460edd7b267d5466fb2915efd0faae749a06d170c81393e142',
        63747, 'f0f5860a35698b4b45508e344b6f34317db8a7db183644a51e0317e9e35563a3'),
}


def revised_bug_register_fact(fact, current, revisions=BUG_REGISTER_REVISIONS):
    old_size, old_sha, new_size, new_sha = revisions[fact['path']]
    if (fact['bytes'], fact['sha256']) != (old_size, old_sha):
        raise ValueError('UI bug source preimage differs from captured fixture')
    if (len(current), hashlib.sha256(current).hexdigest()) != (new_size, new_sha):
        raise ValueError('UI bug source differs from the reviewed revision')
    return dict(fact, bytes=new_size, sha256=new_sha)
