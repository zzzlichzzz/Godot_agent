"""Literal scanner; cache/chain collection is supplied as data by app."""
import re

from .mask import mask

MAX_PROBLEMS = 6
_EXTENDS_RE = re.compile(r'(?m)^[^\S\n]*extends[^\S\n]+([A-Za-z_]\w*)\b')
_FUNC_DEF_RE = re.compile(r'(?m)^[^\S\n]*(?:static[^\S\n]+)?func[^\S\n]+(\w+)[^\S\n]*\(')
_FIELD_DEF_RE = re.compile(r'(?m)^[^\S\n]*(?:@\w+(?:\([^)\n]*\))?[^\S\n]*)*'
                           r'(?:static[^\S\n]+)?(?:var|const)[^\S\n]+(\w+)')
_SIGNAL_DEF_RE = re.compile(r'(?m)^[^\S\n]*signal[^\S\n]+(\w+)')
_ENUM_BLOCK_RE = re.compile(r'(?ms)^[^\S\n]*enum\s+\w*\s*\{([^}]*)\}')
_SELF_CALL_RE = re.compile(r'\b(self|super)\.(\w+)\s*(\()?')
_CONNECT_SELF_RE = re.compile(r'\bself\.connect\(\s*["\'](\w+)["\']')
_CONNECT_BARE_RE = re.compile(r'(?<![.\w])connect\(\s*["\'](\w+)["\']')


def base_class(text):
    match = _EXTENDS_RE.search(text)
    return match.group(1) if match else ''


def local_symbols(masked_full):
    funcs = set(_FUNC_DEF_RE.findall(masked_full))
    fields = set(_FIELD_DEF_RE.findall(masked_full))
    signals = set(_SIGNAL_DEF_RE.findall(masked_full))
    for block in _ENUM_BLOCK_RE.findall(masked_full):
        for part in block.split(","):
            name = part.split("=")[0].strip()
            if name:
                fields.add(name)
    return funcs, fields, signals


def find_matching_paren(text, open_idx):
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def count_top_level_args(masked_text, open_idx, close_idx):
    inner = masked_text[open_idx + 1:close_idx]
    if not inner.strip():
        return 0
    depth = 0
    count = 1
    for c in inner:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            count += 1
    return count


def check(text, classes, members):
    base = base_class(text)
    if not base:
        return [], '', False, 'no_extends'
    if not classes:
        return [], base, False, 'no_cache'
    methods, props, signals = members
    if not methods and not props and not signals:
        return [], base, False, 'base_not_in_cache'

    masked_full = mask(text, True, True)
    masked_comments = mask(text, False, True)
    local_funcs, local_fields, local_signals = local_symbols(masked_full)
    known_members = set(methods) | props | local_funcs | local_fields
    known_signals = signals | local_signals | local_fields
    problems = []
    seen = set()

    def add(msg):
        if msg not in seen:
            seen.add(msg)
            problems.append(msg)

    for mm in _SELF_CALL_RE.finditer(masked_full):
        scope, name, paren = mm.group(1), mm.group(2), mm.group(3)
        line_no = masked_full.count("\n", 0, mm.start()) + 1
        if name in known_members:
            if paren and name in methods:
                open_idx = mm.end() - 1
                close_idx = find_matching_paren(masked_full, open_idx)
                if close_idx != -1:
                    argc = count_top_level_args(masked_full, open_idx, close_idx)
                    min_a, max_a = methods[name]
                    if argc < min_a or argc > max_a:
                        rng = str(min_a) if min_a == max_a else "%d-%d" % (min_a, max_a)
                        add("строка %d: %s.%s(...) вызван с %d аргумент(ами), а у %s.%s их должно быть %s"
                            % (line_no, scope, name, argc, base, name, rng))
            continue
        kind = "метода" if paren else "свойства"
        add("строка %d: %s.%s — такого %s нет у %s и он не объявлен в этом скрипте "
            "(возможно, опечатка или несуществующий в этой версии Godot API)"
            % (line_no, scope, name, kind, base))

    for rx in (_CONNECT_SELF_RE, _CONNECT_BARE_RE):
        for mm in rx.finditer(masked_comments):
            sig_name = mm.group(1)
            if sig_name in known_signals:
                continue
            line_no = masked_comments.count("\n", 0, mm.start()) + 1
            add("строка %d: connect(\"%s\", ...) — сигнала «%s» нет у %s и он не объявлен в этом скрипте"
                % (line_no, sig_name, sig_name, base))
    return problems[:MAX_PROBLEMS], base, True, ''
