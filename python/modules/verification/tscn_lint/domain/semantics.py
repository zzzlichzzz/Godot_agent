"""C.8 semantic findings and cycle decisions; syntax supplied by formats.

Specification port: ba0535d4, tscn_lint.py:718-855, literal full messages.
"""
from python.formats import tscn_lint_syntax as fmt
from .constants import (_BAD_NAME_CHARS_V83, _RESOURCE_PROPS, _SCENE_EXTS)

def _scan_scene_semantics(text):
    problems = []
    ext_types = {}
    seen_ids = {}
    for ln, line in enumerate(text.split('\n'), 1):
        stripped = line.strip()
        if fmt.section_prefix(stripped, 'node'):
            if not fmt.attribute_spelling(stripped, 'name', leading_space=True):
                problems.append('строка %d: у узла нет обязательного атрибута name — Godot не загрузит сцену: «%s»' % (ln, stripped[:80]))
            m_i = fmt.instance_ext_search(stripped)
            if m_i and m_i.group(1) in ext_types:
                rtype, rpath = ext_types[m_i.group(1)]
                if rtype and rtype != 'PackedScene' or (rpath and (not rpath.lower().endswith(_SCENE_EXTS))):
                    problems.append('строка %d: instance= ссылается на ext_resource id="%s" типа %s (%s) — инстансить можно только сцену (.tscn/.scn, type="PackedScene")' % (ln, m_i.group(1), rtype or '?', rpath or '?'))
            continue
        if fmt.section_prefix(stripped, 'ext_resource') or fmt.section_prefix(stripped, 'sub_resource'):
            kind = 'ext_resource' if fmt.section_prefix(stripped, 'ext') else 'sub_resource'
            m_id = fmt.quoted_id_search(stripped)
            if m_id:
                rid = m_id.group(1)
                key = (kind, rid)
                if key in seen_ids:
                    problems.append('строка %d: id="%s" у %s уже используется на строке %d — id должны быть уникальны' % (ln, rid, kind, seen_ids[key]))
                else:
                    seen_ids[key] = ln
                if kind == 'ext_resource':
                    m_t = fmt.quoted_type_search(stripped)
                    m_p = fmt.quoted_path_search(stripped)
                    ext_types[rid] = (m_t.group(1) if m_t else '', m_p.group(1) if m_p else '')
            continue
        if fmt.section_prefix(stripped):
            continue
        for m_c in fmt.math_ctor_args_finditer(line):
            bad = None
            for arg in fmt.comma_atoms(m_c.group(2)):
                if arg.startswith('"') or not fmt.num_arg_match(arg):
                    bad = arg
                    break
            if bad is not None:
                problems.append('строка %d: в конструкторе %s(...) аргумент %s — не число' % (ln, m_c.group(1), bad[:40]))
        m_pv = fmt.numeric_property_match(stripped)
        if m_pv and m_pv.group(1) in _RESOURCE_PROPS:
            problems.append('строка %d: свойство %s ожидает ресурс (SubResource(...)/ExtResource(...)), а не число %s' % (ln, m_pv.group(1), m_pv.group(2)))
    return problems

def _scan_scene_semantics_v83(text):
    problems = []
    for ln, line in enumerate(text.split('\n'), 1):
        stripped = line.strip()
        if fmt.section_prefix(stripped, 'node'):
            m_name = fmt.name_attr_v83_search(stripped)
            if m_name:
                name_val = m_name.group(1)
                if name_val == '':
                    problems.append('строка %d: у узла пустое имя (name="") — Godot не примет пустое имя узла' % ln)
                else:
                    bad = sorted(set((ch for ch in name_val if ch in _BAD_NAME_CHARS_V83)))
                    if bad:
                        problems.append('строка %d: имя узла "%s" содержит недопустимые символы (%s) — имена узлов в Godot не могут содержать . / : @ %% и кавычки' % (ln, name_val, ' '.join(bad)))
            continue
        if fmt.section_prefix(stripped, 'sub_resource'):
            if not fmt.attribute_spelling(stripped, 'type'):
                m_id = fmt.quoted_id_search(stripped)
                problems.append('строка %d: [sub_resource id="%s"] объявлен без type= — Godot не поймёт, какой ресурс создавать' % (ln, m_id.group(1) if m_id else '?'))
            continue
        if fmt.section_prefix(stripped, 'connection'):
            m_method = fmt.method_attr_v83_search(stripped)
            if m_method and (not fmt.valid_method_v83_match(m_method.group(1))):
                problems.append('строка %d: [connection method="%s"]: недопустимое имя метода — оно должно начинаться с буквы или "_", GDScript не примет такой идентификатор' % (ln, m_method.group(1)))
            continue
    return problems

def _find_resource_cycles(text):
    edges = {}
    cur_id = None
    for line in text.split('\n'):
        stripped = line.strip()
        if fmt.section_prefix(stripped):
            m_sub = fmt.sub_header_start_match(stripped)
            if m_sub:
                m_id = fmt.quoted_id_search(stripped)
                cur_id = m_id.group(1) if m_id else None
                if cur_id is not None:
                    edges.setdefault(cur_id, [])
            else:
                cur_id = None
            continue
        if cur_id is not None:
            for m_ref in fmt.subcall_finditer(line):
                edges[cur_id].append(m_ref.group(1))
    problems = []
    color = {}

    def _dfs(node, path):
        color[node] = 1
        path.append(node)
        for nxt in edges.get(node, []):
            if nxt not in edges:
                continue
            if color.get(nxt) == 1:
                idx = path.index(nxt)
                cycle = path[idx:] + [nxt]
                chain = ' -> '.join(('SubResource("%s")' % x for x in cycle))
                problems.append('циклическая зависимость ресурсов: %s — Godot не сможет построить такой ресурс' % chain)
            elif color.get(nxt, 0) == 0:
                _dfs(nxt, path)
        path.pop()
        color[node] = 2
    for node in list(edges.keys()):
        if color.get(node, 0) == 0:
            _dfs(node, [])
    return problems
