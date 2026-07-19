# -*- coding: utf-8 -*-
"""Лёгкая самопроверка GDScript: ловим явный синтаксический мусор
(незакрытые скобки/кавычки, битые отступы, пропущенные двоеточия)
ДО показа действия пользователю. Модель получает список проблем и чинит
код сама — пользователь видит уже проверенный вариант.

Проверки нарочно КОНСЕРВАТИВНЫЕ: лучше пропустить спорный случай, чем
заворачивать корректный код. Ложное срабатывание не блокирует работу —
после MAX_ACTION_FIX_RETRIES попыток действие всё равно показывается."""

import re

MAX_ERRORS = 8

_PAIRS = {")": "(", "]": "[", "}": "{"}
_FUNC_RE = re.compile(r"^(static\s+)?func\s+\w")
_CLASS_RE = re.compile(r"^class\s+\w")

# Точечная проверка явного несоответствия типа при объявлении переменной вида
# `var x: int = "строка"`. Это НЕ полноценная проверка типов (выражения,
# вызовы функций, переменные справа — не трогаем, слишком велик риск ложных
# срабатываний), а узкий эвристический ловец ровно того случая, когда справа
# буквальный литерал явно не того типа. Расширять список типов осторожно.
_VAR_TYPED_RE = re.compile(r"^var\s+\w+\s*:\s*(int|float|bool|String)\s*=\s*(.+)$")
_STR_LIT_RE = re.compile(r"""^('([^'\\]|\\.)*'|"([^"\\]|\\.)*")$""")
_BOOL_LIT_RE = re.compile(r"^(true|false)$")
_FLOAT_LIT_RE = re.compile(r"^-?\d+\.\d+$")
_INT_LIT_RE = re.compile(r"^-?\d+$")
_ARRAY_LIT_RE = re.compile(r"^\[.*\]$")
_DICT_LIT_RE = re.compile(r"^\{.*\}$")
# Какие виды литералов допустимы для каждого объявленного типа без явного
# приведения (int -> float допускается расширением, остальное — нет).
_TYPE_ALLOWED_LITERALS = {
    "int": {"int"},
    "float": {"int", "float"},
    "bool": {"bool"},
    "String": {"string"},
}
_TYPE_RU = {"int": "int", "float": "float", "bool": "bool", "String": "String"}
_LIT_RU = {
    "string": "строковый литерал",
    "bool": "булевый литерал (true/false)",
    "float": "вещественное число (float)",
    "int": "целое число (int)",
    "array": "литерал массива",
    "dict": "литерал словаря",
}


def _literal_kind(rhs):
    """Определяет вид буквального литерала справа от `=`. None — это не
    простой литерал (выражение/переменная/вызов функции), такие строки не
    трогаем, чтобы не давать ложных срабатываний."""
    if _STR_LIT_RE.match(rhs):
        return "string"
    if _BOOL_LIT_RE.match(rhs):
        return "bool"
    if _FLOAT_LIT_RE.match(rhs):
        return "float"
    if _INT_LIT_RE.match(rhs):
        return "int"
    if _ARRAY_LIT_RE.match(rhs):
        return "array"
    if _DICT_LIT_RE.match(rhs):
        return "dict"
    return None


def lint_gdscript(text):
    """Возвращает список проблем (строки на русском). Пустой список — код чистый."""
    if not (text or "").strip():
        return ["итоговый файл получился пустым"]
    errors = []
    if "\ufffd" in text:
        errors.append("в коде символ повреждённой кодировки (\\ufffd) — текст побился")

    lines = text.split("\n")
    stack = []   # открытые скобки: (символ, строка)
    infos = []   # по строкам: triple — строка начинается внутри тройной кавычки,
                 # ds/de — глубина скобок в начале/конце строки
    in_str = None
    triple = None
    str_line = 0
    line_no = 1
    depth_start = 0
    triple_at_start = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            if in_str:
                errors.append("строка %d: незакрытая кавычка (%s)" % (str_line, in_str))
                in_str = None
            infos.append({"triple": triple_at_start, "ds": depth_start, "de": len(stack)})
            depth_start = len(stack)
            triple_at_start = triple is not None
            line_no += 1
            i += 1
            continue
        if triple:
            if c == "\\":
                i += 2
                continue
            if text.startswith(triple * 3, i):
                triple = None
                i += 3
                continue
            i += 1
            continue
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "#":  # комментарий до конца строки (мы вне строк)
            j = text.find("\n", i)
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
        if c in "([{":
            stack.append((c, line_no))
        elif c in ")]}":
            if not stack:
                errors.append("строка %d: лишняя закрывающая скобка «%s»" % (line_no, c))
            else:
                op, ln = stack.pop()
                if _PAIRS[c] != op:
                    errors.append("строка %d: закрывающая «%s» не соответствует открытой «%s» со строки %d" % (line_no, c, op, ln))
        i += 1
    # хвост файла (текст мог не заканчиваться переводом строки)
    if in_str:
        errors.append("строка %d: незакрытая кавычка (%s)" % (str_line, in_str))
    infos.append({"triple": triple_at_start, "ds": depth_start, "de": len(stack)})
    if triple:
        errors.append("строка %d: незакрытая тройная кавычка" % str_line)
    for op, ln in stack:
        errors.append("строка %d: скобка «%s» не закрыта" % (ln, op))

    # Построчные проверки — только если каркас цел (иначе метаданные строк врут).
    if not errors:
        tab_lines, space_lines = [], []
        for idx, raw in enumerate(lines):
            info = infos[idx] if idx < len(infos) else {"triple": False, "ds": 0, "de": 0}
            if info["triple"]:
                continue
            stripped = raw.strip()
            if not stripped:
                continue
            indent = raw[:len(raw) - len(raw.lstrip(" \t"))]
            # Отступы проверяем только у «настоящих» строк кода: внутри скобок
            # (ds > 0) выравнивание свободное, Godot его не проверяет.
            if info["ds"] == 0 and indent:
                if " \t" in indent:
                    errors.append("строка %d: в отступе пробел ПЕРЕД табом — Godot такое не примет" % (idx + 1))
                elif indent[0] == "\t":
                    tab_lines.append(idx + 1)
                else:
                    space_lines.append(idx + 1)
            if info["ds"] == 0 and info["de"] == 0 and (_FUNC_RE.match(stripped) or _CLASS_RE.match(stripped)):
                code = stripped.split("#")[0].rstrip()
                if code and not code.endswith(":") and not code.endswith("\\"):
                    errors.append("строка %d: похоже, пропущено двоеточие в конце объявления" % (idx + 1))
            if info["ds"] == 0 and info["de"] == 0:
                code = stripped.split("#")[0].rstrip()
                m = _VAR_TYPED_RE.match(code)
                if m:
                    decl_type, rhs = m.group(1), m.group(2).strip()
                    if rhs.endswith(";"):
                        rhs = rhs[:-1].strip()
                    kind = _literal_kind(rhs)
                    if kind is not None and kind not in _TYPE_ALLOWED_LITERALS[decl_type]:
                        errors.append(
                            "строка %d: переменной типа %s присваивается %s — Godot выдаст ошибку типов (Type Mismatch)"
                            % (idx + 1, _TYPE_RU[decl_type], _LIT_RU[kind]))
        if tab_lines and space_lines:
            errors.append(
                "смешаны отступы: табы (например, строка %d) и пробелы (например, строка %d) — "
                "Godot выдаст ошибку «Mixed use of tabs and spaces»" % (tab_lines[0], space_lines[0]))
    return errors[:MAX_ERRORS]
