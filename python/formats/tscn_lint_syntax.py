"""Append-only candidate-text syntax, chunks, paths and neutral parse events.

Specification port from ba0535d4 tscn_lint.py: grammar/positions, not findings.
No Godot/project/cache/IO. Existing accepted tscn/refactor parsers unchanged.
"""
from .tscn_lint_tokens import closing_tag_match
from .tscn_lint_tokens import (any_section_match, attr_finditer, connection_finditer, ctor_args_match, ctor_line_match, ctor_value_match, dotted_prop_match, ext_finditer, extcall_finditer, extcall_sub, header_search, instance_ext_search, keyword_value_match, load_steps_sub, math_ctor_args_finditer, method_attr_v83_search, name_attr_v83_search, next_section_search, node_finditer, node_search, nodepath_val_finditer, num_arg_match, num_value_match, numeric_property_match, polygon_prop_match, quoted_id_search, quoted_path_search, quoted_type_search, section_start_match, sub_finditer, sub_header_start_match, sub_search, subcall_finditer, subcall_sub, uid_in_header_sub, valid_method_v83_match, valid_uid_match)
_BRACKET_CLOSE = ')]}'
_BRACKET_OPEN = '([{'
_KNOWN_SECTION_KINDS = ('gd_scene', 'gd_resource', 'ext_resource', 'sub_resource', 'node', 'resource', 'connection', 'editable')

def attrs(head):
    out = {}
    for m in attr_finditer(head):
        key = m.group(1)
        if m.group(2) is not None:
            out[key] = m.group(2)
        elif m.group(3) is not None:
            out[key] = (m.group(3), m.group(4))
        elif m.group(5) is not None:
            out[key] = m.group(5)
    return out

def is_scene_path(path):
    return (path or '').lower().endswith(('.tscn', '.scn'))

def value_looks_parseable(value):
    v = value.strip()
    if not v:
        return False
    if v[0] in '"[{(':
        return True
    if v.startswith('&"') or v.startswith('^"'):
        return True
    if num_value_match(v):
        return True
    if keyword_value_match(v):
        return True
    if ctor_value_match(v):
        return True
    return False

def property_events(text):
    events = []
    depth = 0
    in_str = False
    for i, raw_line in enumerate(text.split('\n')):
        line = raw_line.rstrip('\r')
        at_top = depth == 0 and (not in_str)
        is_header = False
        if at_top:
            stripped = line.strip()
            if not stripped or stripped.startswith(';'):
                continue
            if stripped.startswith('['):
                m = any_section_match(stripped)
                if m:
                    is_header = True
                    kind = m.group(1)
                    if kind not in _KNOWN_SECTION_KINDS:
                        events.append(('property_events_1', (i + 1, kind)))
            elif not stripped.startswith('"'):
                if '=' not in stripped:
                    events.append(('property_events_2', (i + 1, stripped[:80])))
                else:
                    key, _eq, value = stripped.partition('=')
                    if key.strip() and (not value_looks_parseable(value)):
                        events.append(('property_events_3', (i + 1, key.strip(), value.strip()[:80])))
        if is_header:
            continue
        j = 0
        n = len(line)
        while j < n:
            ch = line[j]
            if in_str:
                if ch == '\\':
                    j += 2
                    continue
                if ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in _BRACKET_OPEN:
                depth += 1
            elif ch in _BRACKET_CLOSE:
                if depth > 0:
                    depth -= 1
            j += 1
    return events

def balance_events(text):
    events = []
    depth = 0
    in_str = False
    open_line = None
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if not in_str and depth == 0 and section_start_match(line):
            continue
        if (in_str or depth > 0) and section_start_match(line):
            events.append(('balance_events_1', (open_line or i,)))
            depth = 0
            in_str = False
            continue
        j = 0
        n = len(line)
        while j < n:
            ch = line[j]
            if in_str:
                if ch == '\\':
                    j += 2
                    continue
                if ch == '"':
                    in_str = False
            elif ch == '"':
                if depth == 0 and open_line is None:
                    open_line = i + 1
                in_str = True
            elif ch in _BRACKET_OPEN:
                if depth == 0 and open_line is None:
                    open_line = i + 1
                depth += 1
            elif ch in _BRACKET_CLOSE:
                depth -= 1
                if depth < 0:
                    events.append(('balance_events_2', (i + 1, ch)))
                    depth = 0
            j += 1
        if depth == 0 and (not in_str):
            open_line = None
    if depth > 0 or in_str:
        events.append(('balance_events_3', (open_line or len(lines),)))
    return events

def scene_node_paths(src):
    if src is None:
        return (None, None)
    paths = set()
    fuzzy = set()
    root_seen = False
    for m in node_finditer(src):
        a = attrs(m.group(1))
        name = a.get('name', '?')
        parent = a.get('parent')
        if parent is None:
            if root_seen:
                continue
            root_seen = True
            full = ''
        elif parent == '.':
            full = name
        else:
            full = parent + '/' + name
        paths.add(full)
        if a.get('instance') is not None or a.get('instance_placeholder') is not None:
            fuzzy.add(full)
    if not root_seen:
        return (None, None)
    return (paths, fuzzy)


def has_scene_marker(text):
    return '[gd_scene' in text


def header_candidates(text):
    for i, raw in enumerate(text.split('\n')):
        cr = '\r' if raw.endswith('\r') else ''
        line = raw[:-1] if cr else raw
        stripped = line.rstrip()
        kind, candidate = 'pass', raw
        if closing_tag_match(line.strip()):
            kind = 'closing'
        elif section_start_match(line) and not stripped.endswith(']'):
            if stripped.endswith('>') and ']' not in stripped:
                kind, candidate = 'angle', stripped[:-1].rstrip() + ']' + cr
            elif ']' not in stripped and stripped.count('"') % 2 == 0:
                kind, candidate = 'append', stripped + ']' + cr
            else:
                kind = 'odd'
        yield i + 1, kind, raw, candidate, stripped


def split_sections(text):
    preamble, chunks = [], []
    current_type, current_lines = None, None
    for line in text.split('\n'):
        token = section_start_match(line)
        if token:
            if current_lines is not None:
                chunks.append((current_type, current_lines))
            current_type, current_lines = token.group(1), [line]
        elif current_lines is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_lines is not None:
        chunks.append((current_type, current_lines))
    return preamble, chunks


def section_prefix(text, kind=''):
    return text.startswith('[' + kind)


def attribute_spelling(text, key, leading_space=False):
    return ((' ' if leading_space else '') + key + '="') in text


def comma_atoms(text):
    return [part.strip() for part in text.split(',') if part.strip()]


def nodepath_parts(body, token):
    target = token.group(1)
    node_part = target.split(':', 1)[0]
    start = body.rfind('\n', 0, token.start()) + 1
    end = body.find('\n', token.start())
    line = (body[start:end] if end != -1 else body[start:]).strip()
    return target, node_part, line.split('=', 1)[0].strip() or '?'


def resolve_node_path(own_segs, target):
    out = list(own_segs)
    for part in target.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if not out:
                return None
            out.pop()
        else:
            out.append(part)
    return out
