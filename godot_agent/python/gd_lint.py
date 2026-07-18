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
        if tab_lines and space_lines:
            errors.append(
                "смешаны отступы: табы (например, строка %d) и пробелы (например, строка %d) — "
                "Godot выдаст ошибку «Mixed use of tabs and spaces»" % (tab_lines[0], space_lines[0]))
    return errors[:MAX_ERRORS]
