# -*- coding: utf-8 -*-
"""Refactor scene node names with automatic reference updates across .tscn and attached GDScripts."""

import hashlib
import os
import re
import tempfile
import threading

import gd_lint
import history_manager
from minilich import ml_project_index
from project_tools import _resolve_safe_path, build_diff_preview, can_write_project_path


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_NODE_NAME_RE = re.compile(r"^[^./:@\"\\]+$")
_replace_file = os.replace


class NodeRefactorError(ValueError):
    pass


class StaleNodeRefactorError(RuntimeError):
    pass


def _project_lock(project_root):
    key = os.path.normcase(os.path.realpath(project_root or "."))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _sha256(data):
    return hashlib.sha256(data).hexdigest() if data is not None else ""


def _read_file_text(abs_path):
    with open(abs_path, "rb") as handle:
        raw = handle.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return raw, text, bom


def _normalize_scene_path(project_root, path, allow_addons=False,
                         allow_self_edit=False, addon_dir=None):
    p = str(path or "").strip().replace("\\", "/")
    if not p.startswith("res://") or not p.lower().endswith(".tscn"):
        raise NodeRefactorError("scene должен быть res:// путём к .tscn: %s" % path)
    if not can_write_project_path(
            p, project_root, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir):
        raise NodeRefactorError("Сцена защищена текущей политикой доступа")
    abs_path = _resolve_safe_path(project_root, p)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError("Файл сцены не найден: %s" % p)
    return p, abs_path


def _normalize_node_name(name):
    n = str(name or "").strip()
    if not n or not _NODE_NAME_RE.match(n):
        raise NodeRefactorError("Недопустимое имя узла: %s" % name)
    return n


def parse_tscn_structure(tscn_text):
    """Parses .tscn text to extract ext_resources, nodes, connections, and animations.
    Returns:
        ext_resources: dict id -> {"type", "path"}
        nodes: list of dicts {"name", "type", "parent", "path", "unique_name", "script_id", "span"}
        connections: list of dicts {"from", "to", "signal", "method", "span"}
        anim_tracks: list of dicts {"path", "span"}
    """
    ext_resources = {}
    # [ext_resource type="Script" path="res://player.gd" id="1_player"]
    ext_re = re.compile(r'\[ext_resource\s+([^\]]+)\]')
    for m in ext_re.finditer(tscn_text):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        if "id" in attrs:
            ext_resources[attrs["id"]] = attrs

    nodes = []
    # [node name="Player" type="CharacterBody2D"]
    # [node name="Gun" type="Node2D" parent="."]
    node_header_re = re.compile(r'\[node\s+([^\]]+)\]')
    matches = list(node_header_re.finditer(tscn_text))

    for i, m in enumerate(matches):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        name = attrs.get("name", "")
        parent = attrs.get("parent", None)  # None for root
        node_type = attrs.get("type", "")

        # Node body goes up to next section or end
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(tscn_text)
        # But stop at [connection] or other section headers
        next_sec = re.search(r'\[(connection|sub_resource|editable)', tscn_text[body_start:body_end])
        if next_sec:
            body_end = body_start + next_sec.start()

        body = tscn_text[body_start:body_end]
        unique_name = bool(re.search(r'unique_name_in_owner\s*=\s*true', body))

        script_id = None
        script_m = re.search(r'script\s*=\s*ExtResource\(["\']?([^"\')\s]+)["\']?\)', body)
        if script_m:
            script_id = script_m.group(1)

        # Compute full hierarchical path from root
        if parent is None:
            full_path = "."
        elif parent == ".":
            full_path = name
        else:
            full_path = parent.rstrip("/") + "/" + name

        nodes.append({
            "name": name,
            "parent": parent,
            "type": node_type,
            "path": full_path,
            "unique_name": unique_name,
            "script_id": script_id,
            "header_span": m.span(),
            "body_span": (body_start, body_end),
        })

    # [connection signal="timeout" from="Timer" to="." method="_on_timer_timeout"]
    connections = []
    conn_re = re.compile(r'\[connection\s+([^\]]+)\]')
    for m in conn_re.finditer(tscn_text):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        connections.append({
            "from": attrs.get("from", ""),
            "to": attrs.get("to", ""),
            "signal": attrs.get("signal", ""),
            "method": attrs.get("method", ""),
            "span": m.span(),
            "raw": m.group(0),
        })

    # Animation tracks: tracks/0/path = NodePath("Gun/Muzzle:position")
    anim_tracks = []
    track_re = re.compile(r'(tracks/\d+/path\s*=\s*NodePath\(\s*["\'])([^"\']+)(["\']\s*\))')
    for m in track_re.finditer(tscn_text):
        anim_tracks.append({
            "full_span": m.span(),
            "path_span": (m.start(2), m.end(2)),
            "path": m.group(2),
        })

    return ext_resources, nodes, connections, anim_tracks


def _rel_path_between(from_node, to_node):
    """Calculates Godot relative NodePath string from from_node to to_node.
    Both are relative to root (e.g. '.' or 'Weapon/Gun').
    """
    if from_node == to_node:
        return "."
    from_parts = [] if from_node == "." else from_node.split("/")
    to_parts = [] if to_node == "." else to_node.split("/")

    # Common prefix
    i = 0
    while i < len(from_parts) and i < len(to_parts) and from_parts[i] == to_parts[i]:
        i += 1

    up_count = len(from_parts) - i
    downs = to_parts[i:]

    ups = [".."] * up_count
    parts = ups + downs
    return "/".join(parts) if parts else "."


def find_node_in_scene(nodes, target_spec):
    """Finds node entry in parsed nodes matching target_spec.
    target_spec can be:
      - '%' + name (scene unique name)
      - '.' (root node)
      - 'Path/To/Node' (relative to root)
      - 'NodeName' (single name)
    """
    spec = target_spec.strip().replace("\\", "/")
    if spec.startswith("%"):
        uname = spec[1:]
        for n in nodes:
            if n["unique_name"] and n["name"] == uname:
                return n
        raise NodeRefactorError("Уникальный узел %%%s не найден в сцене" % uname)

    if spec in (".", ""):
        for n in nodes:
            if n["parent"] is None:
                return n
        raise NodeRefactorError("Корневой узел сцены не найден")

    # Exact path match
    for n in nodes:
        if n["path"] == spec:
            return n

    # Single name match (if unique in scene)
    matches = [n for n in nodes if n["name"] == spec]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise NodeRefactorError(
            "Имя узла '%s' неоднозначно (%d совпадений). Укажите полный путь: %s"
            % (spec, len(matches), ", ".join(m["path"] for m in matches))
        )

    raise NodeRefactorError("Узел '%s' не найден в сцене" % spec)


def prepare_node_rename(project_root, scene_godot_path, target_spec, new_name,
                        update_scripts=True, allow_addons=False,
                        allow_self_edit=False, addon_dir=None):
    """Prepares atomic node rename with diffs for .tscn and all attached scripts."""
    scene_path, abs_scene = _normalize_scene_path(
        project_root, scene_godot_path, allow_addons=allow_addons,
        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    new_name = _normalize_node_name(new_name)

    raw_scene, tscn_text, bom = _read_file_text(abs_scene)
    ext_resources, nodes, connections, anim_tracks = parse_tscn_structure(tscn_text)

    target_node = find_node_in_scene(nodes, target_spec)
    old_name = target_node["name"]
    old_path = target_node["path"]

    if old_name == new_name:
        raise NodeRefactorError("Новое имя узла совпадает со старым: %s" % new_name)

    # Check for name collision among siblings
    target_parent = target_node["parent"]
    for n in nodes:
        if n["parent"] == target_parent and n["name"] == new_name:
            raise NodeRefactorError("Узел с именем '%s' уже существует в той же ветке" % new_name)

    # Compute new_path
    if target_parent is None:
        new_path = "."
    elif target_parent == ".":
        new_path = new_name
    else:
        new_path = target_parent.rstrip("/") + "/" + new_name

    is_unique = target_node["unique_name"]
    occurrences_count = 0
    files_to_modify = []

    # -------------------------------------------------------------------------
    # 1. Update .tscn
    # -------------------------------------------------------------------------
    tscn_replacements = []

    # a) Rename node header: [node name="OldName" ...] -> name="NewName"
    h_start, h_end = target_node["header_span"]
    header_text = tscn_text[h_start:h_end]
    new_header_text = re.sub(
        r'(\bname\s*=\s*")' + re.escape(old_name) + r'(")',
        r'\g<1>' + new_name + r'\2',
        header_text,
        count=1
    )
    tscn_replacements.append((h_start, h_end, new_header_text))
    occurrences_count += 1

    # b) Update children parent="..."
    # If old_path was "Weapon", child parent="Weapon" -> "Rifle"
    # If child parent="Weapon/Gun" -> "Rifle/Gun"
    if old_path != ".":
        for n in nodes:
            if n["parent"] is None or n["parent"] == ".":
                continue
            p = n["parent"]
            if p == old_path or p.startswith(old_path + "/"):
                if p == old_path:
                    new_parent = new_path
                else:
                    new_parent = new_path + p[len(old_path):]
                nh_start, nh_end = n["header_span"]
                cur_header = tscn_text[nh_start:nh_end]
                updated_header = re.sub(
                    r'(\bparent\s*=\s*")' + re.escape(p) + r'(")',
                    r'\g<1>' + new_parent + r'\2',
                    cur_header,
                    count=1
                )
                if updated_header != cur_header:
                    tscn_replacements.append((nh_start, nh_end, updated_header))
                    occurrences_count += 1

    # c) Update connections: [connection from="..." to="..."]
    for conn in connections:
        c_start, c_end = conn["span"]
        cur_conn = tscn_text[c_start:c_end]
        mod_conn = cur_conn
        for attr in ("from", "to"):
            val = conn[attr]
            if val == old_path or (old_path != "." and val.startswith(old_path + "/")):
                if val == old_path:
                    new_val = new_path
                else:
                    new_val = new_path + val[len(old_path):]
                mod_conn = re.sub(
                    r'(\b' + attr + r'\s*=\s*")' + re.escape(val) + r'(")',
                    r'\g<1>' + new_val + r'\2',
                    mod_conn,
                    count=1
                )
        if mod_conn != cur_conn:
            tscn_replacements.append((c_start, c_end, mod_conn))
            occurrences_count += 1

    # d) Update Animation tracks: tracks/0/path = NodePath("OldPath/Child:prop")
    for tr in anim_tracks:
        track_path = tr["path"]
        # Track path format: "Node/SubNode:property" or "%UniqueNode:property"
        prop_split = track_path.split(":")
        node_part = prop_split[0]
        prop_part = ":" + ":".join(prop_split[1:]) if len(prop_split) > 1 else ""

        new_node_part = None
        if is_unique and node_part == ("%" + old_name):
            new_node_part = "%" + new_name
        elif old_path != ".":
            if node_part == old_path:
                new_node_part = new_path
            elif node_part.startswith(old_path + "/"):
                new_node_part = new_path + node_part[len(old_path):]

        if new_node_part is not None:
            new_track_path = new_node_part + prop_part
            p_start, p_end = tr["path_span"]
            tscn_replacements.append((p_start, p_end, new_track_path))
            occurrences_count += 1

    # Apply all tscn replacements in reverse order of spans
    new_tscn_text = tscn_text
    for start, end, repl in sorted(tscn_replacements, key=lambda x: x[0], reverse=True):
        new_tscn_text = new_tscn_text[:start] + repl + new_tscn_text[end:]

    tscn_diff = build_diff_preview(tscn_text, new_tscn_text)
    tscn_diff["path"] = scene_path
    tscn_diff["action"] = "patch_file"

    after_tscn_bytes = (b"\xef\xbb\xbf" if bom else b"") + new_tscn_text.encode("utf-8")
    files_to_modify.append({
        "action": "patch_file",
        "path": scene_path,
        "absolute": abs_scene,
        "before_hash": _sha256(raw_scene),
        "before_bytes": raw_scene,
        "after_bytes": after_tscn_bytes,
        "diff": tscn_diff,
        "occurrences": occurrences_count,
    })

    # -------------------------------------------------------------------------
    # 2. Update GDScripts attached to the scene
    # -------------------------------------------------------------------------
    if update_scripts:
        # Collect scripts attached to nodes in this scene
        attached_scripts = {}
        for n in nodes:
            sid = n["script_id"]
            if sid and sid in ext_resources:
                res_meta = ext_resources[sid]
                script_godot_path = res_meta.get("path")
                if script_godot_path and script_godot_path.endswith(".gd"):
                    attached_scripts.setdefault(script_godot_path, []).append(n)

        for script_godot_path, script_nodes in attached_scripts.items():
            if not can_write_project_path(
                    script_godot_path, project_root,
                    allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            abs_script = _resolve_safe_path(project_root, script_godot_path)
            if not os.path.isfile(abs_script):
                continue

            raw_scr, scr_text, scr_bom = _read_file_text(abs_script)
            mod_scr_text = scr_text
            scr_changes = 0

            # Calculate relative path from each node using this script to the target node
            paths_to_replace = []
            for snode in script_nodes:
                from_path = snode["path"]
                rel_old = _rel_path_between(from_path, old_path)
                rel_new = _rel_path_between(from_path, new_path)
                if rel_old != rel_new:
                    paths_to_replace.append((rel_old, rel_new))

            # Also include direct paths from root if script is on root
            if any(snode["path"] == "." for snode in script_nodes) and old_path != ".":
                paths_to_replace.append((old_path, new_path))

            # Deduplicate
            seen = set()
            unique_paths = []
            for ro, rn in paths_to_replace:
                if (ro, rn) not in seen:
                    seen.add((ro, rn))
                    unique_paths.append((ro, rn))

            # 1. Unique name replacement: %OldName -> %NewName
            if is_unique:
                # %OldName
                mod_scr_text, count1 = re.subn(
                    r'(%|\$"%|get_node\(["\']%)' + re.escape(old_name) + r'(\b|["\'])',
                    r'\g<1>' + new_name + r'\2',
                    mod_scr_text
                )
                scr_changes += count1

            # 2. NodePath & Dollar syntax replacement:
            # $Path, $"Path", get_node("Path"), get_node_or_null("Path"), has_node("Path")
            for ro, rn in unique_paths:
                ro_pat = re.escape(ro)
                # Unquoted: $Gun or $Gun/Muzzle
                mod_scr_text, count2 = re.subn(
                    r'(\$)' + ro_pat + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                    r'\g<1>' + rn + r'\2\3',
                    mod_scr_text
                )
                scr_changes += count2

                # Quoted: $"Gun", $"Gun/Muzzle", get_node("Gun"), get_node("Gun/Muzzle"), etc.
                mod_scr_text, count3 = re.subn(
                    r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' +
                    ro_pat +
                    r'((?:/[^"\']*)?)(["\'])',
                    r'\g<1>' + rn + r'\2\3',
                    mod_scr_text
                )
                scr_changes += count3

            # 3. find_child("OldName")
            mod_scr_text, count4 = re.subn(
                r'(\bfind_child\s*\(\s*["\'])' + re.escape(old_name) + r'(["\'])',
                r'\g<1>' + new_name + r'\2',
                mod_scr_text
            )
            scr_changes += count4

            if scr_changes > 0 and mod_scr_text != scr_text:
                # Lint GDScript
                lint_errors = gd_lint.lint_gdscript(mod_scr_text)
                if lint_errors:
                    raise NodeRefactorError(
                        "После обновления узла в скрипте %s обнаружена синтаксическая ошибка: %s"
                        % (script_godot_path, lint_errors[0])
                    )

                scr_diff = build_diff_preview(scr_text, mod_scr_text)
                scr_diff["path"] = script_godot_path
                scr_diff["action"] = "patch_file"

                after_scr_bytes = (b"\xef\xbb\xbf" if scr_bom else b"") + mod_scr_text.encode("utf-8")
                files_to_modify.append({
                    "action": "patch_file",
                    "path": script_godot_path,
                    "absolute": abs_script,
                    "before_hash": _sha256(raw_scr),
                    "before_bytes": raw_scr,
                    "after_bytes": after_scr_bytes,
                    "diff": scr_diff,
                    "occurrences": scr_changes,
                })
                occurrences_count += scr_changes

    return {
        "action": "rename_node",
        "scene": scene_path,
        "scene_res": scene_path,
        "old_name": old_name,
        "new_name": new_name,
        "old_path": old_path,
        "new_path": new_path,
        "target_node_path": old_path,
        "files": files_to_modify,
        "reference_count": occurrences_count,
        "affected_paths": [item["path"] for item in files_to_modify],
    }


def prepare_node_reparent(project_root, scene_godot_path, target_spec, new_parent_spec,
                          update_scripts=True, allow_addons=False,
                          allow_self_edit=False, addon_dir=None):
    """Prepares atomic node reparenting in a scene with automatic path recalculation
    in .tscn hierarchy, connections, animation tracks, and attached GDScripts.
    """
    scene_path, abs_scene = _normalize_scene_path(
        project_root, scene_godot_path, allow_addons=allow_addons,
        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    raw_scene, tscn_text, bom = _read_file_text(abs_scene)
    ext_resources, nodes, connections, anim_tracks = parse_tscn_structure(tscn_text)

    target_node = find_node_in_scene(nodes, target_spec)
    new_parent_node = find_node_in_scene(nodes, new_parent_spec)

    target_name = target_node["name"]
    old_path = target_node["path"]
    new_parent_path = new_parent_node["path"]

    # Safety checks
    if target_node["parent"] is None:
        raise NodeRefactorError("Нельзя перемещать корневой узел сцены")

    if old_path == new_parent_path:
        raise NodeRefactorError("Нельзя переместить узел в самого себя")

    if new_parent_path.startswith(old_path + "/"):
        raise NodeRefactorError("Нельзя переместить узел в его собственного потомка")

    current_parent_path = "." if target_node["parent"] in (".", None) else target_node["parent"]
    norm_new_parent = "." if new_parent_path == "." else new_parent_path
    if current_parent_path == norm_new_parent:
        raise NodeRefactorError("Узел '%s' уже находится у этого родителя" % target_name)

    # Check for name collision under the new parent
    for n in nodes:
        n_parent = "." if n["parent"] in (".", None) else n["parent"]
        if n_parent == norm_new_parent and n["name"] == target_name and n["path"] != old_path:
            raise NodeRefactorError("Узел с именем '%s' уже существует в целевом родителе" % target_name)

    # Compute new path and new parent attribute
    if norm_new_parent == ".":
        new_path = target_name
        new_parent_attr = "."
    else:
        new_path = norm_new_parent + "/" + target_name
        new_parent_attr = norm_new_parent

    occurrences_count = 0
    files_to_modify = []
    tscn_replacements = []

    # 1. Update target node header: parent="..."
    h_start, h_end = target_node["header_span"]
    cur_header = tscn_text[h_start:h_end]
    if re.search(r'\bparent\s*=\s*"[^"]*"', cur_header):
        new_header = re.sub(r'(\bparent\s*=\s*")[^"]*(")', r'\g<1>' + new_parent_attr + r'\2', cur_header, count=1)
    else:
        # Insert parent attribute before closing bracket
        new_header = cur_header[:-1].rstrip() + ' parent="%s"]' % new_parent_attr
    if new_header != cur_header:
        tscn_replacements.append((h_start, h_end, new_header))
        occurrences_count += 1

    # 2. Update descendants' parent attributes in .tscn
    for n in nodes:
        p = n["parent"]
        if not p or p == ".":
            continue
        if p == old_path or p.startswith(old_path + "/"):
            new_p = new_path if p == old_path else new_path + p[len(old_path):]
            nh_start, nh_end = n["header_span"]
            ch = tscn_text[nh_start:nh_end]
            uh = re.sub(r'(\bparent\s*=\s*")[^"]*(")', r'\g<1>' + new_p + r'\2', ch, count=1)
            if uh != ch:
                tscn_replacements.append((nh_start, nh_end, uh))
                occurrences_count += 1

    # 3. Update connections: [connection from="..." to="..."]
    for conn in connections:
        c_start, c_end = conn["span"]
        cur_conn = tscn_text[c_start:c_end]
        mod_conn = cur_conn
        for attr in ("from", "to"):
            val = conn[attr]
            if val == old_path or val.startswith(old_path + "/"):
                new_val = new_path if val == old_path else new_path + val[len(old_path):]
                mod_conn = re.sub(
                    r'(\b' + attr + r'\s*=\s*")' + re.escape(val) + r'(")',
                    r'\g<1>' + new_val + r'\2',
                    mod_conn,
                    count=1
                )
        if mod_conn != cur_conn:
            tscn_replacements.append((c_start, c_end, mod_conn))
            occurrences_count += 1

    # 4. Update Animation tracks
    for tr in anim_tracks:
        prop_split = tr["path"].split(":")
        node_part = prop_split[0]
        prop_part = ":" + ":".join(prop_split[1:]) if len(prop_split) > 1 else ""
        if node_part == old_path or node_part.startswith(old_path + "/"):
            new_node_part = new_path if node_part == old_path else new_path + node_part[len(old_path):]
            p_start, p_end = tr["path_span"]
            tscn_replacements.append((p_start, p_end, new_node_part + prop_part))
            occurrences_count += 1

    # Apply tscn replacements
    new_tscn_text = tscn_text
    for start, end, repl in sorted(tscn_replacements, key=lambda x: x[0], reverse=True):
        new_tscn_text = new_tscn_text[:start] + repl + new_tscn_text[end:]

    tscn_diff = build_diff_preview(tscn_text, new_tscn_text)
    tscn_diff["path"] = scene_path
    tscn_diff["action"] = "patch_file"

    after_tscn_bytes = (b"\xef\xbb\xbf" if bom else b"") + new_tscn_text.encode("utf-8")
    files_to_modify.append({
        "action": "patch_file",
        "path": scene_path,
        "absolute": abs_scene,
        "before_hash": _sha256(raw_scene),
        "before_bytes": raw_scene,
        "after_bytes": after_tscn_bytes,
        "diff": tscn_diff,
        "occurrences": occurrences_count,
    })

    # 5. Update GDScripts attached to the scene
    if update_scripts:
        attached_scripts = {}
        for n in nodes:
            sid = n["script_id"]
            if sid and sid in ext_resources:
                res_meta = ext_resources[sid]
                script_godot_path = res_meta.get("path")
                if script_godot_path and script_godot_path.endswith(".gd"):
                    attached_scripts.setdefault(script_godot_path, []).append(n)

        # Collect all moved nodes (target + descendants)
        moved_subtree = [target_node]
        for n in nodes:
            if n["path"] != old_path and (n["parent"] == old_path or (n["parent"] and n["parent"].startswith(old_path + "/"))):
                moved_subtree.append(n)

        def _subtree_new_path(p):
            if p == old_path:
                return new_path
            if p.startswith(old_path + "/"):
                return new_path + p[len(old_path):]
            return p

        for script_godot_path, script_nodes in attached_scripts.items():
            if not can_write_project_path(
                    script_godot_path, project_root,
                    allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            abs_script = _resolve_safe_path(project_root, script_godot_path)
            if not os.path.isfile(abs_script):
                continue

            raw_scr, scr_text, scr_bom = _read_file_text(abs_script)
            mod_scr_text = scr_text
            scr_changes = 0

            # Calculate path mappings for each moved node from each script node
            paths_to_replace = []
            for mnode in moved_subtree:
                m_old = mnode["path"]
                m_new = _subtree_new_path(m_old)
                for snode in script_nodes:
                    from_old = snode["path"]
                    from_new = _subtree_new_path(from_old)
                    rel_old = _rel_path_between(from_old, m_old)
                    rel_new = _rel_path_between(from_new, m_new)
                    if rel_old != rel_new:
                        paths_to_replace.append((rel_old, rel_new))
                if any(snode["path"] == "." for snode in script_nodes) and m_old != ".":
                    paths_to_replace.append((m_old, m_new))

            seen = set()
            unique_paths = []
            for ro, rn in paths_to_replace:
                if (ro, rn) not in seen:
                    seen.add((ro, rn))
                    unique_paths.append((ro, rn))

            # Replace paths in script
            for ro, rn in unique_paths:
                ro_pat = re.escape(ro)
                # Unquoted: $Path
                # In GDScript, paths containing '..' or non-identifier tokens must be quoted: $"../Path"
                if rn.startswith("..") or any(not part.isidentifier() for part in rn.split("/") if part):
                    mod_scr_text, count2 = re.subn(
                        r'\$' + ro_pat + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                        r'$"' + rn + r'\1"',
                        mod_scr_text
                    )
                else:
                    mod_scr_text, count2 = re.subn(
                        r'(\$)' + ro_pat + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                        r'\g<1>' + rn + r'\2\3',
                        mod_scr_text
                    )
                scr_changes += count2

                # Quoted: $"Path", get_node("Path"), etc.
                mod_scr_text, count3 = re.subn(
                    r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' +
                    ro_pat +
                    r'((?:/[^"\']*)?)(["\'])',
                    r'\g<1>' + rn + r'\2\3',
                    mod_scr_text
                )
                scr_changes += count3

            if scr_changes > 0 and mod_scr_text != scr_text:
                lint_errors = gd_lint.lint_gdscript(mod_scr_text)
                if lint_errors:
                    raise NodeRefactorError(
                        "После перемещения узла в скрипте %s обнаружена синтаксическая ошибка: %s"
                        % (script_godot_path, lint_errors[0])
                    )

                scr_diff = build_diff_preview(scr_text, mod_scr_text)
                scr_diff["path"] = script_godot_path
                scr_diff["action"] = "patch_file"

                after_scr_bytes = (b"\xef\xbb\xbf" if scr_bom else b"") + mod_scr_text.encode("utf-8")
                files_to_modify.append({
                    "action": "patch_file",
                    "path": script_godot_path,
                    "absolute": abs_script,
                    "before_hash": _sha256(raw_scr),
                    "before_bytes": raw_scr,
                    "after_bytes": after_scr_bytes,
                    "diff": scr_diff,
                    "occurrences": scr_changes,
                })
                occurrences_count += scr_changes

    return {
        "action": "reparent_node",
        "scene": scene_path,
        "scene_res": scene_path,
        "target_node": target_name,
        "old_path": old_path,
        "new_parent": new_parent_path,
        "new_path": new_path,
        "target_node_path": old_path,
        "files": files_to_modify,
        "reference_count": occurrences_count,
        "affected_paths": [item["path"] for item in files_to_modify],
    }


def prepare_node_deletion(project_root, scene_godot_path, target_spec,
                          cleanup_code=True, allow_addons=False,
                          allow_self_edit=False, addon_dir=None):
    """Prepares atomic node and subtree deletion from a scene with automatic
    removal of signal connections, animation tracks, and safe commenting of
    references in attached GDScripts.
    """
    scene_path, abs_scene = _normalize_scene_path(
        project_root, scene_godot_path, allow_addons=allow_addons,
        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    raw_scene, tscn_text, bom = _read_file_text(abs_scene)
    ext_resources, nodes, connections, anim_tracks = parse_tscn_structure(tscn_text)

    target_node = find_node_in_scene(nodes, target_spec)
    target_name = target_node["name"]
    old_path = target_node["path"]

    if target_node["parent"] is None:
        raise NodeRefactorError("Нельзя удалить корневой узел сцены")

    # Collect target node + all descendants
    deleted_nodes = [target_node]
    deleted_paths = {old_path}
    deleted_unames = set()
    if target_node["unique_name"]:
        deleted_unames.add(target_name)

    for n in nodes:
        p = n["parent"]
        if p and (p == old_path or p.startswith(old_path + "/")):
            deleted_nodes.append(n)
            deleted_paths.add(n["path"])
            if n["unique_name"]:
                deleted_unames.add(n["name"])

    occurrences_count = 0
    files_to_modify = []
    tscn_replacements = []

    # 1. Remove nodes from .tscn
    for dn in deleted_nodes:
        h_start = dn["header_span"][0]
        b_end = dn["body_span"][1]
        while b_end < len(tscn_text) and tscn_text[b_end] in ("\r", "\n"):
            b_end += 1
        tscn_replacements.append((h_start, b_end, ""))
        occurrences_count += 1

    # 2. Remove signal connections
    for conn in connections:
        if conn["from"] in deleted_paths or conn["to"] in deleted_paths:
            c_start, c_end = conn["span"]
            while c_end < len(tscn_text) and tscn_text[c_end] in ("\r", "\n"):
                c_end += 1
            tscn_replacements.append((c_start, c_end, ""))
            occurrences_count += 1

    # 3. Remove Animation tracks
    for tr in anim_tracks:
        prop_split = tr["path"].split(":")
        node_part = prop_split[0]
        if node_part in deleted_paths or (node_part.startswith("%") and node_part[1:] in deleted_unames):
            f_start, f_end = tr["full_span"]
            while f_end < len(tscn_text) and tscn_text[f_end] in ("\r", "\n"):
                f_end += 1
            tscn_replacements.append((f_start, f_end, ""))
            occurrences_count += 1

    # Apply tscn replacements
    new_tscn_text = tscn_text
    for start, end, repl in sorted(tscn_replacements, key=lambda x: x[0], reverse=True):
        new_tscn_text = new_tscn_text[:start] + repl + new_tscn_text[end:]

    tscn_diff = build_diff_preview(tscn_text, new_tscn_text)
    tscn_diff["path"] = scene_path
    tscn_diff["action"] = "patch_file"

    after_tscn_bytes = (b"\xef\xbb\xbf" if bom else b"") + new_tscn_text.encode("utf-8")
    files_to_modify.append({
        "action": "patch_file",
        "path": scene_path,
        "absolute": abs_scene,
        "before_hash": _sha256(raw_scene),
        "before_bytes": raw_scene,
        "after_bytes": after_tscn_bytes,
        "diff": tscn_diff,
        "occurrences": occurrences_count,
    })

    # 4. Scan attached GDScripts for references and record warnings (do not modify scripts
    # to prevent IndentationError, broken variable logic, or unwanted pass spam)
    warnings = []
    if cleanup_code:
        attached_scripts = {}
        for n in nodes:
            if n["path"] in deleted_paths:
                continue
            sid = n["script_id"]
            if sid and sid in ext_resources:
                res_meta = ext_resources[sid]
                script_godot_path = res_meta.get("path")
                if script_godot_path and script_godot_path.endswith(".gd"):
                    attached_scripts.setdefault(script_godot_path, []).append(n)

        for script_godot_path, script_nodes in attached_scripts.items():
            if not can_write_project_path(
                    script_godot_path, project_root,
                    allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            abs_script = _resolve_safe_path(project_root, script_godot_path)
            if not os.path.isfile(abs_script):
                continue

            raw_scr, scr_text, scr_bom = _read_file_text(abs_script)
            target_rel_paths = set()
            for snode in script_nodes:
                for dp in deleted_paths:
                    target_rel_paths.add(_rel_path_between(snode["path"], dp))
            if any(snode["path"] == "." for snode in script_nodes):
                target_rel_paths.update(deleted_paths)

            lines = scr_text.splitlines()
            for line_idx, line in enumerate(lines, 1):
                stripped = line.lstrip()
                if not stripped or stripped.startswith("#"):
                    continue

                matched = False
                # Check target rel paths
                for ro in target_rel_paths:
                    ro_pat = re.escape(ro)
                    if (re.search(r'\$' + ro_pat + r'(\b|/)', line) or
                        re.search(r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' + ro_pat + r'(\b|/|["\'])', line)):
                        matched = True
                        break

                if not matched:
                    # Check unique names
                    for un in deleted_unames:
                        un_pat = re.escape(un)
                        if re.search(r'(%|\$"%|get_node\(["\']%)' + un_pat + r'(\b|["\'])', line):
                            matched = True
                            break

                if matched:
                    warnings.append({
                        "file": script_godot_path,
                        "line": line_idx,
                        "code": stripped,
                        "message": "Ссылка на удаляемый узел '%s' в %s:%d: %s" % (
                            target_name, script_godot_path, line_idx, stripped
                        )
                    })

    return {
        "action": "delete_node",
        "scene": scene_path,
        "scene_res": scene_path,
        "target_node": target_name,
        "target_node_path": old_path,
        "deleted_nodes": [n["path"] for n in deleted_nodes],
        "files": files_to_modify,
        "reference_count": occurrences_count,
        "affected_paths": [item["path"] for item in files_to_modify],
        "warnings": warnings,
    }


def apply_prepared_node_refactor(project_root, prepared, chat_id=None,
                                 chat_title=None, allow_addons=False,
                                 allow_self_edit=False, addon_dir=None):
    """Atomically applies prepared node refactoring (rename, reparent, delete)
    to .tscn and scripts with rollback support.
    """
    files = prepared.get("files") or []
    if not files:
        raise NodeRefactorError("Подготовленная транзакция не содержит изменений")

    scene_path = prepared["scene"]
    action_type = prepared.get("action", "rename_node")

    with _project_lock(project_root):
        # Freshness and policy checks happen together before the first write.
        policy_paths = [scene_path]
        policy_paths.extend(item.get("path") or "" for item in files)
        for candidate in policy_paths:
            if not candidate:
                raise NodeRefactorError(
                    "Подготовленная транзакция содержит пустой путь")
            if not can_write_project_path(
                    candidate, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                raise NodeRefactorError(
                    "Путь защищён текущей политикой доступа: %s" % candidate)
        for item in files:
            expected_absolute = _resolve_safe_path(project_root, item["path"])
            supplied_absolute = os.path.realpath(item.get("absolute") or "")
            if os.path.normcase(supplied_absolute) != os.path.normcase(
                expected_absolute):
                raise NodeRefactorError(
                    "Абсолютный путь не соответствует res://-пути: %s" %
                    item["path"])

        for item in files:
            if not os.path.isfile(item["absolute"]):
                raise StaleNodeRefactorError("Файл удалён: %s" % item["path"])
            with open(item["absolute"], "rb") as h:
                if _sha256(h.read()) != item["before_hash"]:
                    raise StaleNodeRefactorError("Файл изменился после предпросмотра: %s" % item["path"])

        # 2. Record batch change in history_manager
        states = []
        batch_paths = []
        for item in files:
            states.append({
                "path": item["path"],
                "before_bytes": item["before_bytes"],
                "after_bytes": item["after_bytes"],
            })
            batch_paths.append(item["path"])

        entry_id = history_manager.record_batch_change(
            project_root, action_type, batch_paths,
            chat_id=chat_id, chat_title=chat_title, states=states
        )

        temps = []
        try:
            # 3. Write temp files
            for item in files:
                parent = os.path.dirname(item["absolute"])
                os.makedirs(parent, exist_ok=True)
                fd, temp_path = tempfile.mkstemp(prefix=".agent_node_refactor_", dir=parent)
                with os.fdopen(fd, "wb") as h:
                    h.write(item["after_bytes"])
                    h.flush()
                    os.fsync(h.fileno())
                temps.append((temp_path, item["absolute"]))

            # 4. Atomic replace
            for temp_path, target_path in temps:
                _replace_file(temp_path, target_path)

            # 5. Commit to history
            history_manager.commit_change(project_root, entry_id)

        except Exception:
            # Roll back on error
            for item in files:
                if item.get("before_bytes") is not None:
                    try:
                        with open(item["absolute"], "wb") as h:
                            h.write(item["before_bytes"])
                    except Exception:
                        pass
            history_manager.abort_change(project_root, entry_id)
            raise

        finally:
            for temp_path, _ in temps:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass

        # Update indexer
        changed_paths = [item["path"] for item in files]
        try:
            ml_project_index.update_entries(project_root, changed_rels=changed_paths)
        except Exception:
            pass

        return {
            "entry_id": entry_id,
            "action": action_type,
            "scene": scene_path,
            "scene_res": scene_path,
            "old_name": prepared.get("old_name", ""),
            "new_name": prepared.get("new_name", ""),
            "old_path": prepared.get("old_path", ""),
            "new_path": prepared.get("new_path", ""),
            "target_node_path": prepared.get("target_node_path", prepared.get("old_path", "")),
            "new_parent": prepared.get("new_parent", ""),
            "deleted_nodes": prepared.get("deleted_nodes", []),
            "changed_paths": changed_paths,
            "reference_count": prepared.get("reference_count", 0),
            "file_count": len(files),
        }


apply_prepared_node_rename = apply_prepared_node_refactor
apply_prepared_node_reparent = apply_prepared_node_refactor
apply_prepared_node_deletion = apply_prepared_node_refactor

