"""GDScript lint, ported verbatim algorithm; pure text/bytes -> findings (R-08).

Reference: python/godot_tools/gd_lint.py:13-191 at
ba0535d4dec43c32750e601a6ca86e377abc6af3 (SHA256 in corpus manifest).
Messages are catalog data; traversal, quirks and final slice are unchanged.
MAX_ERRORS caps the final answer, not the scanner. No format reconstruction,
IO, Godot, code execution or auto-fixes. check() is the new data projection.
"""
import re
from python.modules.verification.shared.source_text import decode_source

from .findings import CATALOG, from_message

MAX_ERRORS = 8
_PAIRS = {')': '(', ']': '[', '}': '{'}
_FUNC_RE = re.compile(r'^(static\s+)?func\s+\w')
_CLASS_RE = re.compile(r'^class\s+\w')
_VAR_TYPED_RE = re.compile(r'^var\s+\w+\s*:\s*(int|float|bool|String)\s*=\s*(.+)$')
_STR_LIT_RE = re.compile(r"""^('([^'\\]|\\.)*'|"([^"\\]|\\.)*")$""")
_BOOL_LIT_RE = re.compile(r'^(true|false)$')
_FLOAT_LIT_RE = re.compile(r'^-?\d+\.\d+$')
_INT_LIT_RE = re.compile(r'^-?\d+$')
_ARRAY_LIT_RE = re.compile(r'^\[.*\]$')
_DICT_LIT_RE = re.compile(r'^\{.*\}$')
_TYPE_ALLOWED_LITERALS = {
    'int': {'int'}, 'float': {'int', 'float'}, 'bool': {'bool'}, 'String': {'string'},
}
_TYPE_RU = {'int': 'int', 'float': 'float', 'bool': 'bool', 'String': 'String'}
_LIT_RU = {
    'string': 'строковый литерал', 'bool': 'булевый литерал (true/false)',
    'float': 'вещественное число (float)', 'int': 'целое число (int)',
    'array': 'литерал массива', 'dict': 'литерал словаря',
}


def _literal_kind(rhs):
    """Reference :50-66; expressions and calls are deliberately not type-checked."""
    if _STR_LIT_RE.match(rhs):
        return 'string'
    if _BOOL_LIT_RE.match(rhs):
        return 'bool'
    if _FLOAT_LIT_RE.match(rhs):
        return 'float'
    if _INT_LIT_RE.match(rhs):
        return 'int'
    if _ARRAY_LIT_RE.match(rhs):
        return 'array'
    if _DICT_LIT_RE.match(rhs):
        return 'dict'
    return None


def lint_gdscript(text):
    """Literal reference messages, in order; metadata quirks are not corrected."""
    if not (text or '').strip():
        return [CATALOG['empty_file']]
    errors = []
    if '\ufffd' in text:
        errors.append(CATALOG['damaged_encoding'])
    lines = text.split('\n')
    stack, infos = [], []
    in_str, triple = None, None
    str_line, line_no, depth_start = 0, 1, 0
    triple_at_start = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '\n':
            if in_str:
                errors.append(CATALOG['unclosed_string'] % (str_line, in_str))
                in_str = None
            infos.append({'triple': triple_at_start, 'ds': depth_start, 'de': len(stack)})
            depth_start = len(stack)
            triple_at_start = triple is not None
            line_no += 1
            i += 1
            continue
        if triple:
            if c == '\\':
                i += 2
                continue
            if text.startswith(triple * 3, i):
                triple = None
                i += 3
                continue
            i += 1
            continue
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == '#':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '"' or c == "'":
            if text.startswith(c * 3, i):
                triple = c
                str_line = line_no
                i += 3
                continue
            in_str = c
            str_line = line_no
            i += 1
            continue
        if c in '([{':
            stack.append((c, line_no))
        elif c in ')]}':
            if not stack:
                errors.append(CATALOG['extra_closing_bracket'] % (line_no, c))
            else:
                op, ln = stack.pop()
                if _PAIRS[c] != op:
                    errors.append(CATALOG['mismatched_bracket'] % (line_no, c, op, ln))
        i += 1
    if in_str:
        errors.append(CATALOG['unclosed_string'] % (str_line, in_str))
    infos.append({'triple': triple_at_start, 'ds': depth_start, 'de': len(stack)})
    if triple:
        errors.append(CATALOG['unclosed_triple_string'] % str_line)
    for op, ln in stack:
        errors.append(CATALOG['unclosed_bracket'] % (ln, op))
    if not errors:
        tab_lines, space_lines = [], []
        for idx, raw in enumerate(lines):
            info = infos[idx] if idx < len(infos) else {'triple': False, 'ds': 0, 'de': 0}
            if info['triple']:
                continue
            stripped = raw.strip()
            if not stripped:
                continue
            indent = raw[:len(raw) - len(raw.lstrip(' \t'))]
            if info['ds'] == 0 and indent:
                if ' \t' in indent:
                    errors.append(CATALOG['space_before_tab'] % (idx + 1))
                elif indent[0] == '\t':
                    tab_lines.append(idx + 1)
                else:
                    space_lines.append(idx + 1)
            if info['ds'] == 0 and info['de'] == 0 and (_FUNC_RE.match(stripped) or _CLASS_RE.match(stripped)):
                code = stripped.split('#')[0].rstrip()
                if code and not code.endswith(':') and not code.endswith('\\'):
                    errors.append(CATALOG['missing_colon'] % (idx + 1))
            if info['ds'] == 0 and info['de'] == 0:
                code = stripped.split('#')[0].rstrip()
                m = _VAR_TYPED_RE.match(code)
                if m:
                    decl_type, rhs = m.group(1), m.group(2).strip()
                    if rhs.endswith(';'):
                        rhs = rhs[:-1].strip()
                    kind = _literal_kind(rhs)
                    if kind is not None and kind not in _TYPE_ALLOWED_LITERALS[decl_type]:
                        errors.append(CATALOG['type_mismatch'] % (idx + 1, _TYPE_RU[decl_type], _LIT_RU[kind]))
        if tab_lines and space_lines:
            errors.append(CATALOG['mixed_indentation'] % (tab_lines[0], space_lines[0]))
    return errors[:MAX_ERRORS]


def check(raw):
    """Original byte count; ADR-0008 file BOM decode, CRLF intact, output quota."""
    messages = lint_gdscript(decode_source(raw))
    return {'findings': [from_message(message) for message in messages],
            'truncated': len(messages) >= MAX_ERRORS, 'checked_bytes': len(raw)}
