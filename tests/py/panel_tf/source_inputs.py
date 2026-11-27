"""D90 input-only revision: exact old/new raw pins, unchanged business goldens."""
import hashlib
import json
from pathlib import Path


_REVISIONS = Path(__file__).resolve().parents[3] / 'fixtures/corpus/scene_model'
D128 = json.loads((_REVISIONS / 'd128_revision.json').read_bytes())
D129 = json.loads((_REVISIONS / 'd129_revision.json').read_bytes())


def _before_revision(revision, path, current):
    """Reverse only reviewed edits so earlier source-revision proofs still run on their actual input."""
    if path not in revision:
        return current
    spec = revision[path]
    if [len(current), hashlib.sha256(current).hexdigest()] != spec['after']:
        raise ValueError('Unexpected source input: ' + path)
    lines = current.decode('utf-8').splitlines(True)
    for start, end, old in reversed(spec['reverse']):
        lines[start:end] = [old]
    previous = ''.join(lines).encode('utf-8')
    if [len(previous), hashlib.sha256(previous).hexdigest()] != spec['before']:
        raise ValueError('Unexpected source preimage: ' + path)
    return previous


def before_d128(path, current):
    return _before_revision(D128, path, _before_revision(D129, path, current))

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

# D123 visual changes. The start screen already has a reviewed intermediate revision above.
D123_REVISIONS = {
    'editor/native/agent_start_screen.gd': (
        203949, 'd09926528fb9281f63d426e1dabbbd42098d26d66dc026e79eabcf9a912312c3',
        202647, 'd4d47329378386973e8a073f7b077bbd9e1cd1d531f6a6baebb9706fc10f2258'),
    'editor/native/agent_theme.gd': (
        14364, 'a541a1816049b5d17f203809de9287dd742ba64b70aa6c33f80fdd8f7137d18a',
        14124, 'dcddcbbf0eacbd28f0bd9cd2a21c0ded165c40401ade649f28f95249b0c9e11d'),
    'editor/native/UserMessageCard.gd': (
        6192, '8fd1c6623cbd2ec26b8ddc37811edb2e33b0f2025a301980c65c79546dab861a',
        6189, 'adba37306b5dd3e083124852167355aa9434a0c100624d738ea30019fcf3b002'),
    'editor/native/agent_read_consent.gd': (
        3137, '37077ff88fcbd7b52c3db7b9d59491024161fa546190f080048e4c5b8b86c540',
        3835, '38a967c3bf0967a6eaab3786d5d56c5a5c0b111d5e45efa84d0a0cc22a57ddc8'),
}


D125_CONSENT = 'editor/native/agent_read_consent.gd'


def revised_dock_fact(fact, current):
    prior = BUG_REGISTER_REVISIONS.get(fact['path'])
    if prior:
        if (fact['bytes'], fact['sha256']) != prior[:2]:
            raise ValueError('Pre-D123 start screen input drifted')
        fact = dict(fact, bytes=prior[2], sha256=prior[3])
    if fact['path'] == D125_CONSENT:
        old_size, old_sha, size, sha = D123_REVISIONS[D125_CONSENT]
        if (fact['bytes'], fact['sha256']) != (old_size, old_sha):
            raise ValueError('Original consent helper drifted')
        return revised_bug_register_fact(dict(fact, bytes=size, sha256=sha), current, {D125_CONSENT: (
            size, sha, 6633, '3e5fd1a26ada34a9412afd1990cf01b0fe58e5521abe3143188c0eaa8cac825b')})
    return revised_bug_register_fact(fact, current, D123_REVISIONS)


def revised_bug_register_fact(fact, current, revisions=BUG_REGISTER_REVISIONS):
    old_size, old_sha, new_size, new_sha = revisions[fact['path']]
    if (fact['bytes'], fact['sha256']) != (old_size, old_sha):
        raise ValueError('UI bug source preimage differs from captured fixture')
    if (len(current), hashlib.sha256(current).hexdigest()) != (new_size, new_sha):
        raise ValueError('UI bug source differs from the reviewed revision')
    return dict(fact, bytes=new_size, sha256=new_sha)


D124_TRANSCRIPT = 'editor/native/agent_panel_part2.gd'


def revised_transcript_fact(fact, current):
    added = b'\n\t\tif kind in ["chat", "read_decision", "confirm"]:'
    if current.count(added) != 1:
        raise ValueError('Missing D124 transcript warning guard')
    prior = revised_bug_register_fact(fact, current.replace(added, b'', 1), D122_REVISIONS)
    return revised_bug_register_fact(prior, current, {D124_TRANSCRIPT: (
        63747, 'f0f5860a35698b4b45508e344b6f34317db8a7db183644a51e0317e9e35563a3',
        63798, 'ceabe7f6480885b3364c9614f478a75ddeb4e76a1721cb333ebc89b812956d44')})


D124_VISUAL = {
    'editor/native/AgentMessageCard.gd': (12277, '9bc3142692acbd67d7ef53fedd569994dc33ddeb3495a81aa73fdcfa3ca24fa7',
        12409, '169f7689c3a296fbf3c80a86f23d7f40ffb075114662de40dee23dacb3f7d70e'),
    'editor/native/agent_start_screen.gd': (*D123_REVISIONS['editor/native/agent_start_screen.gd'][2:],
        203818, 'e0a170679c0c5c4ba8ab165205f06079ef44332a9a7bb18b36df6b2c5caaae38'),
    'editor/native/agent_theme.gd': (*D123_REVISIONS['editor/native/agent_theme.gd'][2:],
        14503, 'cd8503bc71498711eb5b81518ff41836e87e613c09a98fd1b847cd988a9e3da6'),
    'editor/native/agent_locale.gd': (*D116_REVISIONS['editor/native/agent_locale.gd'][2:4],
        86711, '2965bc09f3b7a6814ba0f1572238b1bb1ca00a5fc482a8d35b92d4eb043f01a8'),
}


def before_workspace_labels(current):
    path = 'editor/native/agent_locale.gd'
    if (len(current), hashlib.sha256(current).hexdigest()) != D124_VISUAL[path][2:]:
        raise ValueError('Unexpected workspace labels revision')
    return b''.join(line for line in current.splitlines(True) if not line.startswith(b'\t"workspace_'))


def revised_workspace_fact(fact, current):
    path = fact['path']
    if path in D116_REVISIONS:
        fact = revised_d116_fact(fact, before_workspace_labels(current))
    else:
        for revisions in (BUG_REGISTER_REVISIONS, D123_REVISIONS):
            if path in revisions:
                old_size, old_sha, size, sha = revisions[path]
                if (fact['bytes'], fact['sha256']) != (old_size, old_sha):
                    raise ValueError('Prior dock input drifted: ' + path)
                fact = dict(fact, bytes=size, sha256=sha)
    return revised_bug_register_fact(fact, current, D124_VISUAL)


D126_CHAT = {
    'editor/native/AgentMessageCard.gd': (*D124_VISUAL['editor/native/AgentMessageCard.gd'][2:],
        13856, '3635e2b165391935e1c0c20e7c23a3af1a14f0f4213f711eb87111743d540cdf'),
    'editor/native/UserMessageCard.gd': (*D123_REVISIONS['editor/native/UserMessageCard.gd'][2:],
        5465, '4d4b772831a85bf18b5fa898e9a133a9745b5d2f84c65997ff06aa3fe1a5d419'),
    'editor/native/agent_theme.gd': (*D124_VISUAL['editor/native/agent_theme.gd'][2:],
        14662, '22a35099be21744853a16d925f3e077de8936ad52dd51f9bed4127ee655745e2'),
}


D127_TYPOGRAPHY = {
    'editor/native/AgentMessageCard.gd': (*D126_CHAT['editor/native/AgentMessageCard.gd'][2:],
        13925, 'baa2cd4ccf5d258828cd6f95b1597e78406a75fd4c1d1e403c9af07128fbe5bd'),
    'editor/native/agent_theme.gd': (*D126_CHAT['editor/native/agent_theme.gd'][2:],
        16284, '2cfde8ee63b3860fc59bc16b1ac6d63d0863045415f662c209af02e2f8900fe2'),
}


def revised_chat_fact(fact, current):
    later = fact['path'] in D127_TYPOGRAPHY
    chain = (D123_REVISIONS, D124_VISUAL, D126_CHAT) if later else (D123_REVISIONS, D124_VISUAL)
    for versions in chain:
        if fact['path'] in versions:
            size, sha, after_size, after_sha = versions[fact['path']]
            if (fact['bytes'], fact['sha256']) != (size, sha):
                raise ValueError('Unexpected prior chat input: ' + fact['path'])
            fact = dict(fact, bytes=after_size, sha256=after_sha)
    return revised_bug_register_fact(fact, current, D127_TYPOGRAPHY if later else D126_CHAT)
