"""C.8 tree/connection/NodePath findings; neutral source tokens only.

Specification port: ba0535d4, tscn_lint.py:582-630,877-952.
"""
from python.formats import tscn_lint_syntax as fmt

def _check_connections_and_parents(text):
    problems = []
    paths = set()
    root_seen = False
    for m in fmt.node_finditer(text):
        a = fmt.attrs(m.group(1))
        if a.get('instance') is not None or a.get('instance_placeholder') is not None:
            return problems
        name = a.get('name', '?')
        parent = a.get('parent')
        if parent is None:
            if root_seen:
                continue
            root_seen = True
        elif parent == '.':
            paths.add(name)
        else:
            paths.add(parent + '/' + name)
    if not root_seen:
        return problems

    def _known(p):
        return p in ('.', '') or p in paths
    for m in fmt.node_finditer(text):
        a = fmt.attrs(m.group(1))
        parent = a.get('parent')
        if parent is None or parent == '.':
            continue
        if not _known(parent):
            problems.append('[node name="%s"]: parent="%s" — такого узла в сцене нет, Godot не сможет построить дерево. Родителя объявляй ВЫШЕ по файлу и указывай его ПУТЬ от корня (parent="." для детей корня, parent="A/B" для вложенных).' % (a.get('name', '?'), parent))
    for m in fmt.connection_finditer(text):
        a = fmt.attrs(m.group(1))
        for key in ('from', 'to'):
            tgt = a.get(key)
            if tgt is None or _known(tgt):
                continue
            problems.append('[connection signal="%s"]: %s="%s" — такого узла в сцене нет, Godot не сможет подключить сигнал. Укажи путь существующего узла (например "." для корня).' % (a.get('signal', '?'), key, tgt))
    return problems

def _scan_node_path_refs(text):
    problems = []
    paths = set()
    infos = []
    root_seen = False
    for m in fmt.node_finditer(text):
        a = fmt.attrs(m.group(1))
        if a.get('instance') is not None or a.get('instance_placeholder') is not None:
            return []
        name = a.get('name', '?')
        parent = a.get('parent')
        if parent is None:
            if root_seen:
                continue
            root_seen = True
            segs = []
        elif parent == '.':
            segs = [name]
            paths.add(name)
        else:
            segs = [pp for pp in parent.split('/') if pp] + [name]
            paths.add(parent + '/' + name)
        infos.append((name, a.get('type') or '?', segs, m.end()))
    if not root_seen:
        return []
    for name, ntype, segs, body_start in infos:
        m_next = fmt.next_section_search(text, body_start)
        body = text[body_start:m_next.start()] if m_next else text[body_start:]
        for m_np in fmt.nodepath_val_finditer(body):
            target, node_part, prop = fmt.nodepath_parts(body, m_np)
            if not node_part or node_part == '.':
                continue
            if node_part.startswith('/') or '%' in node_part:
                continue
            resolved = fmt.resolve_node_path(segs, node_part)
            if resolved is None:
                problems.append(u'узел "%s" (%s): %s = NodePath("%s") — путь поднимается выше корня сцены (лишние «..»); такого узла внутри этой сцены быть не может. Пути NodePath отсчитываются от самого узла: "../Имя" — сосед, "Имя" — ребёнок.' % (name, ntype, prop, target))
            elif resolved and '/'.join(resolved) not in paths:
                problems.append(u'узел "%s" (%s): %s = NodePath("%s") указывает на узел «%s», которого в сцене НЕТ. Godot откроет сцену, но повесит на узел жёлтое предупреждение, и свойство работать не будет. Укажи путь существующего узла (пути отсчитываются от самого узла: "../Имя" — сосед, "Имя" — ребёнок) либо добавь недостающий узел в сцену.' % (name, ntype, prop, target, '/'.join(resolved)))
        if ntype in ('Polygon2D', 'CollisionPolygon2D'):
            for raw_line in body.split('\n'):
                m_poly = fmt.polygon_prop_match(raw_line.strip())
                if not m_poly:
                    continue
                coords = fmt.comma_atoms(m_poly.group(1))
                pts = len(coords) // 2
                if pts < 3:
                    problems.append(u'узел "%s" (%s): polygon содержит только %d точк(и) — полигону нужно минимум 3 точки, иначе Godot повесит предупреждение, а рисовать/сталкивать будет нечего. Добавь недостающие вершины или убери свойство polygon.' % (name, ntype, pts))
    return problems
