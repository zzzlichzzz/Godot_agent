# formats/gdscript/tokens.py - лексер GDScript с точными смещениями (R-14).
#
# Перенос эталонного `gd_tools/gd_semantic_parser.py::tokenize`: комментарии
# выбрасываются, строки сохраняются вместе с кавычками и флагом `closed`,
# переводы строк остаются токенами (на них держится разбор объявлений).
# NI: ни файлов, ни путей, ни Godot — только текст и числа.

import re

_IDENT_START_RE = re.compile(r"[^\W\d]", re.U)
_IDENT_CONT_RE = re.compile(r"\w", re.U)

#: Двухсимвольные операторы: разбираются одним токеном, иначе `->` распадается
#: и тип возврата функции перестаёт быть «именем после стрелки».
TWO_CHAR = ("->", "==", "!=", "<=", ">=", ":=", "&&", "||")


def is_ident_start(char):
    """Символ может начинать идентификатор (буква или `_`)."""
    return bool(char == "_" or _IDENT_START_RE.match(char))


def is_ident_continue(char):
    """Символ может продолжать идентификатор (буква, цифра, `_`)."""
    return bool(char == "_" or _IDENT_CONT_RE.match(char))


def tokenize(text):
    """Токены без комментариев; у каждого — `start`, `end`, `line`, `column`."""
    tokens = []
    i, line, column, size = 0, 1, 1, len(text or "")
    while i < size:
        char = text[i]
        if char in " \t\r":
            i += 1
            column += 1
            continue
        if char == "\n":
            tokens.append({"kind": "newline", "value": "\n", "start": i,
                           "end": i + 1, "line": line, "column": column})
            i += 1
            line += 1
            column = 1
            continue
        if char == "#":
            end = text.find("\n", i)
            if end < 0:
                break
            column += end - i
            i = end
            continue
        if char in "\"'":
            quote = char
            triple = text.startswith(char * 3, i)
            width = 3 if triple else 1
            start, start_line, start_column = i, line, column
            i += width
            column += width
            closed = False
            while i < size:
                if text[i] == "\\":
                    step = min(2, size - i)
                    i += step
                    column += step
                    continue
                if text.startswith(quote * width, i):
                    i += width
                    column += width
                    closed = True
                    break
                if text[i] == "\n":
                    if not triple:
                        break
                    i += 1
                    line += 1
                    column = 1
                    continue
                i += 1
                column += 1
            tokens.append({"kind": "string", "value": text[start:i],
                           "start": start, "end": i, "line": start_line,
                           "column": start_column, "closed": closed})
            continue
        if is_ident_start(char):
            start, start_column = i, column
            i += 1
            column += 1
            while i < size and is_ident_continue(text[i]):
                i += 1
                column += 1
            tokens.append({"kind": "identifier", "value": text[start:i],
                           "start": start, "end": i, "line": line,
                           "column": start_column})
            continue
        start_column = column
        two = text[i:i + 2]
        if two in TWO_CHAR:
            value = two
            i += 2
            column += 2
        else:
            value = char
            i += 1
            column += 1
        tokens.append({"kind": "symbol", "value": value, "start": i - len(value),
                       "end": i, "line": line, "column": start_column})
    return tokens
