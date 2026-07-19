# -*- coding: utf-8 -*-
"""Проверка кода .gd против реального API Godot (кэш ClassDB из gd_api_cache),
а НЕ по памяти обучения модели. Ловит:
  - self.<xxx>() / self.<xxx> — такого метода/свойства нет ни у базового класса,
    ни в самом скрипте (опечатка или несуществующий в этой версии Godot API);
  - self.<xxx>(...) вызван с числом аргументов, которое не поддерживается методом;
  - connect("signal_name", ...) на self, где такого сигнала нет.

КОНСЕРВАтивно: если кэш пуст или базовый класс неизвестен (например,
скрипт наследует другой скрипт проекта, а не класс движка) — просто ничего
не говорится. Мы предпоцитаем пропустить редкий случай, а не создать ложные
срабатывания."""
import re

import gd_api_cache

MAX_PROBLEMS = 6

_EXTENDS_RE = re.compile(r'(?m)^\s*extends\s+([A-Za-z_]\w*)\b')
_FUNC_DEF_RE = re.compile(r'(?m)^\s*(?:static\s+)?func\s+(\w+)\s*\(')
_FIELD_DEF_RE = re.compile(r'(?m)^\s*(?:@\w+(?:\([^)\n]*\))?\s*)*(?:static\s+)?(?:var|const)\s+(\w+)')
_SIGNAL_DEF_RE = re.compile(r'(?m)^\s*signal\s+(\w+)')
_ENUM_BLOCK_RE = re.compile(r'(?ms)^\s*enum\s+\w*\s*\{([^}]*)\}')
_SELF_CALL_RE = re.compile(r'\b(self|super)\.(\w+)\s*(\()?')
_CONNECT_SELF_RE = re.compile(r'\bself\.connect\(\s*["\'](\w+)["\']')
_CONNECT_BARE_RE = re.compile(r'(?<![.\w])connect\(\s*["\'](\w+)["\']')


def _mask(text, mask_strings, mask_comments):
    """Возвращает копию text той же длины (совпадают символьные позиции
    и номера строк), где строковые литералы и/или комментарии затёрты
    пробелами — чтобы регулярки никогда не цеплялись за текст внутри них."""
    out = list(text)
    i, n = 0, len(text)
    in_str = None
    triple = None
    while i < n:
        c = text[i]
        if triple:
            if mask_strings and c != "\n":
                out[i] = " "
            if c == "\\" and i + 1 < n:
                if mask_strings and text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if text.startswith(triple * 3, i):
                if mask_strings:
                    out[i] = out[i + 1] = out[i + 2] = " "
                triple = None
                i += 3
                continue
            i += 1
            continue
        if in_str:
            if mask_strings and c != "\n":
                out[i] = " "
            if c == "\\" and i + 1 < n:
                if mask_strings and text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "#":
            j = text.find("\n", i)
            end = n if j < 0 else j
            if mask_comments:
                for k in range(i, end):
                    out[k] = " "
            i = end
            continue
        if c == '"' or c == "'":
            if text.startswith(c * 3, i):
                triple = c
                if mask_strings:
                    out[i] = out[i + 1] = out[i + 2] = " "
                i += 3
                continue
            in_str = c
            if mask_strings:
                out[i] = " "
            i += 1
            continue
        i += 1
    return "".join(out)


def _local_symbols(masked_full):
    funcs = set(_FUNC_DEF_RE.findall(masked_full))
    fields = set(_FIELD_DEF_RE.findall(masked_full))
    signals = set(_SIGNAL_DEF_RE.findall(masked_full))
    for block in _ENUM_BLOCK_RE.findall(masked_full):
        for part in block.split(","):
            name = part.split("=")[0].strip()
            if name:
                fields.add(name)
    return funcs, fields, signals


def _find_matching_paren(text, open_idx):
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


def _count_top_level_args(masked_text, open_idx, close_idx):
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


def check_api_usage(project_root, text, path="", addon_dir=None):
    """Возвращает список строк-проблем (может быть пустым — это норма:
    значит, либо код чист, либо мы ничего не смогли проверить)."""
    m = _EXTENDS_RE.search(text)
    if not m:
        return []
    base_class = m.group(1)
    if not gd_api_cache.has_cache(project_root, addon_dir):
        return []
    methods, props, signals = gd_api_cache.collect_members(project_root, base_class, addon_dir)
    if not methods and not props and not signals:
        return []  # extends указывает на класс, которого нет в кэше (например, свой базовый скрипт)

    masked_full = _mask(text, True, True)
    masked_comments = _mask(text, False, True)
    local_funcs, local_fields, local_signals = _local_symbols(masked_full)
    known_members = set(methods) | props | local_funcs | local_fields
    known_signals = signals | local_signals | local_fields

    problems = []
    seen = set()

    def _add(msg):
        if msg not in seen:
            seen.add(msg)
            problems.append(msg)

    for mm in _SELF_CALL_RE.finditer(masked_full):
        scope, name, paren = mm.group(1), mm.group(2), mm.group(3)
        line_no = masked_full.count("\n", 0, mm.start()) + 1
        if name in known_members:
            if paren and name in methods:
                open_idx = mm.end() - 1
                close_idx = _find_matching_paren(masked_full, open_idx)
                if close_idx != -1:
                    argc = _count_top_level_args(masked_full, open_idx, close_idx)
                    min_a, max_a = methods[name]
                    if argc < min_a or argc > max_a:
                        rng = str(min_a) if min_a == max_a else "%d-%d" % (min_a, max_a)
                        _add("строка %d: %s.%s(...) вызван с %d аргумент(ами), а у %s.%s их должно быть %s"
                             % (line_no, scope, name, argc, base_class, name, rng))
            continue
        kind = "метода" if paren else "свойства"
        _add("строка %d: %s.%s — такого %s нет у %s и он не объявлен в этом скрипте "
             "(возможно, опечатка или несуществующий в этой версии Godot API)"
             % (line_no, scope, name, kind, base_class))

    for rx in (_CONNECT_SELF_RE, _CONNECT_BARE_RE):
        for mm in rx.finditer(masked_comments):
            sig_name = mm.group(1)
            if sig_name in known_signals:
                continue
            line_no = masked_comments.count("\n", 0, mm.start()) + 1
            _add("строка %d: connect(\"%s\", ...) — сигнала «%s» нет у %s и он не объявлен в этом скрипте"
                 % (line_no, sig_name, sig_name, base_class))

    return problems[:MAX_PROBLEMS]
