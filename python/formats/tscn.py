# formats/tscn.py - один разбор .tscn/.tres на весь агент (R-04).
# Заменяет: project_tools.describe_scene, node_refactor.parse_tscn_structure,
# scene_deps, tscn_lint.
# structure/fields: ported verbatim, эталон ba0535d4dec43c32750e601a6ca86e377abc6af3.
# node_refactor.py:73-160; scene_deps.py:68,102-172; хеши в manifest.json корпуса.
# serialize не реализуется: модель теряет детали формата, поэтому только patch
# исходного текста по смещениям, без реконструкции, удаления BOM и перевода EOL.

import re

__all__ = ("structure", "fields", "patch", "rows")

_ATTR_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)')


def structure(text):
    """Ответ node_refactor.parse_tscn_structure, включая tuple и символьные spans.

    Возвращает (ext_resources, nodes, connections, anim_tracks). Упрощённые
    регулярки эталона намеренно сохранены; fields имеет другое поведение.
    """
    ext_resources = {}
    ext_re = re.compile(r'\[ext_resource\s+([^\]]+)\]')
    for m in ext_re.finditer(text):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        if "id" in attrs:
            ext_resources[attrs["id"]] = attrs

    nodes = []
    node_header_re = re.compile(r'\[node\s+([^\]]+)\]')
    matches = list(node_header_re.finditer(text))
    for i, m in enumerate(matches):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        name = attrs.get("name", "")
        parent = attrs.get("parent", None)
        node_type = attrs.get("type", "")

        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        next_sec = re.search(r'\[(connection|sub_resource|editable)', text[body_start:body_end])
        if next_sec:
            body_end = body_start + next_sec.start()
        body = text[body_start:body_end]
        unique_name = bool(re.search(r'unique_name_in_owner\s*=\s*true', body))
        script_id = None
        script_m = re.search(r'script\s*=\s*ExtResource\(["\']?([^"\')\s]+)["\']?\)', body)
        if script_m:
            script_id = script_m.group(1)

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

    connections = []
    conn_re = re.compile(r'\[connection\s+([^\]]+)\]')
    for m in conn_re.finditer(text):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        connections.append({
            "from": attrs.get("from", ""),
            "to": attrs.get("to", ""),
            "signal": attrs.get("signal", ""),
            "method": attrs.get("method", ""),
            "span": m.span(),
            "raw": m.group(0),
        })

    anim_tracks = []
    track_re = re.compile(r'(tracks/\d+/path\s*=\s*NodePath\(\s*["\'])([^"\']+)(["\']\s*\))')
    for m in track_re.finditer(text):
        anim_tracks.append({
            "full_span": m.span(),
            "path_span": (m.start(2), m.end(2)),
            "path": m.group(2),
        })
    return ext_resources, nodes, connections, anim_tracks


def _parse_attrs(head):
    res = {}
    for key, raw in _ATTR_RE.findall(head):
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = raw[1:-1]
        res[key] = raw
    return res


def _attr_id(raw):
    if not raw:
        return None
    match = re.match(r'^\s*(?:ExtResource|SubResource)\(\s*["\']?([^"\')]+)["\']?\s*\)\s*$',
                     str(raw))
    return match.group(1) if match else None


def fields(text):
    """Ответ scene_deps.parse_scene: (ext, nodes, connections), без новых полей."""
    ext = {}
    nodes = []
    connections = []
    cur_node = None
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("[ext_resource") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            if a.get("id"):
                ext[a["id"]] = {"type": a.get("type", ""), "path": a.get("path", "")}
            cur_node = None
        elif stripped.startswith("[node") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            name = a.get("name", "")
            parent = a.get("parent")
            if parent is None:
                path = "."
            elif parent == ".":
                path = name
            else:
                path = parent + "/" + name
            cur_node = {
                "name": name,
                "type": a.get("type"),
                "parent": parent,
                "path": path,
                "script_id": None,
                "instance_id": _attr_id(a.get("instance")),
            }
            nodes.append(cur_node)
        elif stripped.startswith("[connection") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            connections.append({
                "signal": a.get("signal", ""),
                "from": a.get("from", ""),
                "to": a.get("to", ""),
                "method": a.get("method", ""),
            })
            cur_node = None
        elif stripped.startswith("["):
            cur_node = None
        elif cur_node is not None and stripped.startswith("script"):
            m = re.match(r'script\s*=\s*ExtResource\(\s*"([^"]+)"\s*\)', stripped)
            if m:
                cur_node["script_id"] = m.group(1)
    return ext, nodes, connections


def patch(text, edits):
    """Применяет непересекающиеся ((start, end), replacement) к исходному тексту.

    Смещения — индексы символов Python, end исключён; все относятся к исходному
    text. Порядок входного списка не важен, список не изменяется. Пустой список
    возвращает исходный текст без каких-либо преобразований.
    """
    for (start, end), replacement in sorted(edits, key=lambda edit: edit[0][0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def rows(text):
    """Literal describe_scene parsing view, project_tools.py:1280-1335.

    Frozen ba0535d4dec43c32750e601a6ca86e377abc6af3; hashes/locals oracle in
    fixtures/corpus/scene_model/tree/manifest.json. Preserves duplicate/missing
    resource rows and the reference's line rules. Caller supplies decoded text.
    Depth/path/render belong to the consumer. No IO or reconstruction.
    """
    ext = {}
    ext_rows = []
    sub_rows = []
    for m in re.finditer(r'\[ext_resource\b[^\]]*\]', text):
        head = m.group(0)
        pm = re.search(r'path="([^"]+)"', head)
        im = re.search(r'\bid="?([^"\s\]]+)"?', head)
        tm = re.search(r'\btype="([^"]+)"', head)
        um = re.search(r'\buid="([^"]+)"', head)
        if pm and im:
            ext[im.group(1)] = pm.group(1)
        ext_rows.append({'id': im.group(1) if im else '?',
                         'type': tm.group(1) if tm else '?',
                         'path': pm.group(1) if pm else '?',
                         'uid': um.group(1) if um else None})
    for m in re.finditer(r'\[sub_resource\b[^\]]*\]', text):
        head = m.group(0)
        im = re.search(r'\bid="?([^"\s\]]+)"?', head)
        tm = re.search(r'\btype="([^"]+)"', head)
        sub_rows.append({'id': im.group(1) if im else '?', 'type': tm.group(1) if tm else '?'})
    nodes = []
    connections = []
    cur = None
    for line in text.replace('\r\n', '\n').split('\n'):
        s = line.strip()
        if s.startswith('[node '):
            nm = re.search(r'name="([^"]+)"', s)
            tm = re.search(r'type="([^"]+)"', s)
            pm = re.search(r'parent="([^"]*)"', s)
            im = re.search(r'instance=ExtResource\(\s*"?([^")\s]+)"?\s*\)', s)
            cur = {'name': nm.group(1) if nm else '?', 'type': tm.group(1) if tm else '',
                   'parent': pm.group(1) if pm else None,
                   'script': None, 'instance': ext.get(im.group(1)) if im else None}
            nodes.append(cur)
        elif s.startswith('[connection '):
            sig = re.search(r'signal="([^"]+)"', s)
            frm = re.search(r'from="([^"]*)"', s)
            to = re.search(r'to="([^"]*)"', s)
            met = re.search(r'method="([^"]+)"', s)
            if sig and frm and to and met:
                connections.append({'from': frm.group(1), 'to': to.group(1),
                                    'signal': sig.group(1), 'method': met.group(1)})
            cur = None
        elif s.startswith('['):
            cur = None
        elif cur is not None and re.match(r'script\s*=', s):
            sm = re.search(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)', s)
            if sm:
                cur['script'] = ext.get(sm.group(1))
    return {'nodes': nodes, 'connections': connections,
            'resources': {'ext': ext_rows, 'sub': sub_rows}}


# C.5 append-only facts; accepted structure/fields/patch/rows remain unchanged.
# Explicit C.5 facts do not change the closed star-exported format operations.


def to_snake(name):
    """Literal scene_deps.py:73-99; approximation, not Godot execution."""
    out = []
    prev = ''
    for i, ch in enumerate(name):
        if ch in '-. ':
            out.append('_')
            prev = ch
            continue
        if ch.isupper():
            if prev and prev.islower():
                out.append('_')
            elif prev.isupper() and i + 1 < len(name) and name[i + 1].islower():
                out.append('_')
            out.append(ch.lower())
        elif ch.isdigit():
            if prev and prev.islower():
                out.append('_')
            out.append(ch)
        else:
            out.append(ch)
        prev = ch
    value = ''.join(out)
    while '__' in value:
        value = value.replace('__', '_')
    return value.strip('_').lower()


def method_referenced(text, method):
    """Literal reference needle, even in comments; no improved validation."""
    return 'method="%s"' % method in text


def script_referenced(text, res_path):
    """Literal analyze_script_action prefilter, not resource graph traversal."""
    return 'path="%s"' % res_path in text


# C.6 append-only operations; accepted operations and closed __all__ unchanged.
def normalize_node_name(name):
    value = str(name or '').strip()
    if not value or not re.match(r'^[^./:@"\\]+$', value):
        raise ValueError('Недопустимое имя узла: %s' % name)
    return value


def _rename_attribute(text, attribute, old, new):
    return re.sub(r'(\b' + attribute + r'\s*=\s*")' + re.escape(old) + r'(")',
                  r'\g<1>' + new + r'\2', text, count=1)


def node_rename_edits(text, view, target, new_name, new_path):
    """Literal node_refactor.py:297-377 edits; caller uses accepted patch.

    Original character spans, no reconstruction. Header count includes no-ops.
    """
    _, nodes, connections, tracks = view
    old_name, old_path = target['name'], target['path']
    start, end = target['header_span']
    edits = [((start, end), _rename_attribute(text[start:end], 'name', old_name, new_name))]
    count = 1
    if old_path != '.':
        for node in nodes:
            parent = node['parent']
            if parent is None or parent == '.':
                continue
            if parent == old_path or parent.startswith(old_path + '/'):
                replacement = new_path + parent[len(old_path):]
                start, end = node['header_span']
                header = text[start:end]
                updated = _rename_attribute(header, 'parent', parent, replacement)
                if updated != header:
                    edits.append(((start, end), updated))
                    count += 1
    for connection in connections:
        start, end = connection['span']
        original = text[start:end]
        updated = original
        for attribute in ('from', 'to'):
            value = connection[attribute]
            if value == old_path or (old_path != '.' and value.startswith(old_path + '/')):
                replacement = new_path + value[len(old_path):]
                updated = _rename_attribute(updated, attribute, value, replacement)
        if updated != original:
            edits.append(((start, end), updated))
            count += 1
    for track in tracks:
        parts = track['path'].split(':')
        node_part = parts[0]
        suffix = ':' + ':'.join(parts[1:]) if len(parts) > 1 else ''
        replacement = None
        if target['unique_name'] and node_part == '%' + old_name:
            replacement = '%' + new_name
        elif old_path != '.' and (node_part == old_path or node_part.startswith(old_path + '/')):
            replacement = new_path + node_part[len(old_path):]
        if replacement is not None:
            edits.append((track['path_span'], replacement + suffix))
            count += 1
    return edits, count


# C.7 append-only operations; accepted parser/patch and __all__ remain intact.
from . import tscn_refactor


def node_reparent_edits(text, view, target, new_parent, new_path):
    return tscn_refactor.node_reparent_edits(text, view, target, new_parent, new_path,
                                           _rename_attribute)


node_delete_edits = tscn_refactor.node_delete_edits
