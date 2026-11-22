"""C.8 fix decisions, stable order and reconstruction; no syntax parser/IO.

Specification port: ba0535d4, tscn_lint.py:85-438; CRLF and blanks are data.
"""
from python.formats import tscn_lint_syntax as fmt
from .constants import (_CHUNK_TYPE_RANK, _NODE_CLASSES, _VARIANT_TYPES)

def _reorder_resource_sections(text):
    preamble, chunks = fmt.split_sections(text)
    if not chunks:
        return text
    ranked = sorted(enumerate(chunks), key=lambda pair: (_CHUNK_TYPE_RANK.get(pair[1][0], 99), pair[0]))
    new_lines = list(preamble)
    for _, (_type, chunk_lines) in ranked:
        new_lines.extend(chunk_lines)
    return '\n'.join(new_lines)

def _strip_invalid_uids(text):

    def repl(m):
        if fmt.valid_uid_match(m.group(2)):
            return m.group(0)
        return m.group(1) + m.group(3)
    return fmt.uid_in_header_sub(repl, text)

def _reorder_nodes_for_parent_order(text):
    preamble, chunks = fmt.split_sections(text)
    node_idxs = [i for i, (t, _) in enumerate(chunks) if t == 'node']
    if len(node_idxs) < 2:
        return text
    infos = []
    for idx in node_idxs:
        head = chunks[idx][1][0]
        m = fmt.node_search(head)
        a = fmt.attrs(m.group(1)) if m else {}
        infos.append((idx, a.get('name', '?'), a.get('parent')))
    root_idx = None
    full_paths = {}
    for idx, name, parent in infos:
        if parent is None:
            full_paths[idx] = name
            if root_idx is None:
                root_idx = idx
        elif parent == '.':
            full_paths[idx] = name
        else:
            full_paths[idx] = parent + '/' + name
    path_to_idx = {}
    for idx, name, parent in infos:
        path_to_idx.setdefault(full_paths[idx], idx)
    parent_of = {}
    for idx, name, parent in infos:
        if parent is None:
            parent_of[idx] = None
        elif parent == '.':
            parent_of[idx] = root_idx if root_idx is not None and root_idx != idx else None
        else:
            parent_of[idx] = path_to_idx.get(parent)
    order = []
    emitted = set()
    remaining = list(node_idxs)
    progress = True
    while remaining and progress:
        progress = False
        next_remaining = []
        for idx in remaining:
            p = parent_of.get(idx)
            if p is None or p in emitted:
                order.append(idx)
                emitted.add(idx)
                progress = True
            else:
                next_remaining.append(idx)
        remaining = next_remaining
    order.extend(remaining)
    if order == node_idxs:
        return text
    order_iter = iter(order)
    new_lines = list(preamble)
    for t, cl in chunks:
        if t == 'node':
            new_lines.extend(chunks[next(order_iter)][1])
        else:
            new_lines.extend(cl)
    return '\n'.join(new_lines)

def _fix_single_candidate_refs(text, ext_ids, sub_ids):
    fixed = text
    if len(ext_ids) == 1:
        only_id = next(iter(ext_ids))

        def _fix_ext(m):
            return m.group(0) if m.group(1) == only_id else 'ExtResource("%s")' % only_id
        fixed = fmt.extcall_sub(_fix_ext, fixed)
    if len(sub_ids) == 1:
        only_id = next(iter(sub_ids))

        def _fix_sub(m):
            return m.group(0) if m.group(1) == only_id else 'SubResource("%s")' % only_id
        fixed = fmt.subcall_sub(_fix_sub, fixed)
    return fixed

def _convert_ctor_values(text, problems):
    existing_ids = set()
    for m in fmt.sub_finditer(text):
        a = fmt.attrs(m.group(1))
        rid = a.get('id')
        if isinstance(rid, str):
            existing_ids.add(rid)
    lines = text.split('\n')
    new_headers = []
    counter = 0
    for i, raw_line in enumerate(lines):
        cr = '\r' if raw_line.endswith('\r') else ''
        line = raw_line[:-1] if cr else raw_line
        am = fmt.ctor_args_match(line)
        if am:
            problems.append('строка «%s»: %s.new(...) с аргументами — это синтаксис GDScript, в .tscn он невалиден. Объяви [sub_resource type="%s" id="..."] с нужными свойствами отдельными строками и подставь SubResource("...").' % (line.strip(), am.group(1), am.group(1)))
            continue
        m = fmt.ctor_line_match(line)
        if not m:
            continue
        rtype = m.group(2)
        if rtype in _NODE_CLASSES or rtype in _VARIANT_TYPES:
            problems.append('строка «%s»: %s.new() — %s не ресурс (это узел или Variant-значение), в .tscn его нельзя объявить как [sub_resource]. Убери это свойство или используй дочерний узел / прямое значение.' % (line.strip(), rtype, rtype))
            continue
        counter += 1
        rid = 'auto_%s_%d' % (rtype.lower(), counter)
        while rid in existing_ids:
            counter += 1
            rid = 'auto_%s_%d' % (rtype.lower(), counter)
        existing_ids.add(rid)
        lines[i] = m.group(1) + 'SubResource("%s")' % rid + cr
        new_headers.append('[sub_resource type="%s" id="%s"]' % (rtype, rid))
    if not new_headers:
        return '\n'.join(lines)
    insert_at = None
    for i, line in enumerate(lines):
        sm = fmt.section_start_match(line)
        if sm and sm.group(1) in ('node', 'connection'):
            insert_at = i
            break
    block = []
    for header in new_headers:
        block.append(header)
        block.append('')
    if insert_at is None:
        if lines and lines[-1].strip():
            lines.append('')
        lines.extend(block)
    else:
        if insert_at > 0 and lines[insert_at - 1].strip():
            block.insert(0, '')
        lines[insert_at:insert_at] = block
    return '\n'.join(lines)

def _toposort_sub_resources(text):
    preamble, chunks = fmt.split_sections(text)
    sub_idxs = [i for i, (t, _) in enumerate(chunks) if t == 'sub_resource']
    if len(sub_idxs) < 2:
        return text
    id_to_idx = {}
    for idx in sub_idxs:
        m = fmt.sub_search(chunks[idx][1][0])
        a = fmt.attrs(m.group(1)) if m else {}
        rid = a.get('id')
        if isinstance(rid, str):
            id_to_idx.setdefault(rid, idx)
    deps = {}
    for idx in sub_idxs:
        body = '\n'.join(chunks[idx][1][1:])
        found = set()
        for m in fmt.subcall_finditer(body):
            target = id_to_idx.get(m.group(1))
            if target is not None and target != idx:
                found.add(target)
        deps[idx] = found
    order = []
    emitted = set()
    remaining = list(sub_idxs)
    progress = True
    while remaining and progress:
        progress = False
        next_remaining = []
        for idx in remaining:
            if deps[idx] <= emitted:
                order.append(idx)
                emitted.add(idx)
                progress = True
            else:
                next_remaining.append(idx)
        remaining = next_remaining
    order.extend(remaining)
    if order == sub_idxs:
        return text
    order_iter = iter(order)
    new_lines = list(preamble)
    for t, cl in chunks:
        if t == 'sub_resource':
            new_lines.extend(chunks[next(order_iter)][1])
        else:
            new_lines.extend(cl)
    return '\n'.join(new_lines)
