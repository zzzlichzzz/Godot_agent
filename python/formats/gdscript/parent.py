# formats/gdscript/parent.py - `extends` файла скрипта (R-14).
#
# Перенос эталонного `symbol_refactor_part1._get_script_parent`: нужен, чтобы
# считать наследников при поиске использований. Путь отдаётся в том же виде,
# что и входной (`res://` остаётся `res://`), иначе вызывающие не сравнят пути.
# NI: ни файлов, ни `os`; относительный `extends "res://x.gd"` раскрывается
# средствами posixpath — это чистая арифметика над строками.

import posixpath

from python.formats.gdscript.tokens import tokenize


def exact_string_value(raw):
    """Значение строкового литерала без кавычек (одинарных и тройных)."""
    if len(raw) < 2:
        return ""
    width = 3 if raw[:3] in ('"""', "'''") else 1
    return raw[width:-width] if len(raw) >= width * 2 else ""


def script_parent(text, file_path):
    """(путь родителя, имя класса-родителя) или (None, None).

    Берётся первый `extends`: по правилам GDScript он стоит до любых членов,
    поэтому `extends` внутри `class Inner extends X` отсекается по флагу.
    """
    tokens = tokenize(text)
    seen_class_kw = False
    for index, token in enumerate(tokens):
        value = token.get("value")
        if value == "class":
            seen_class_kw = True
            continue
        if value != "extends" or index + 1 >= len(tokens):
            continue
        if seen_class_kw:
            # extends вложенного класса родителем файла быть не может.
            return None, None
        nxt = tokens[index + 1]
        if index + 2 < len(tokens) and tokens[index + 2]['value'] == '.':
            # Extends Outer.Inner: the outer script is not the declared parent.
            return None, None
        if nxt.get("kind") == "string":
            target = exact_string_value(nxt.get("value", ""))
            if target.startswith("res://"):
                return target, None
            if file_path.startswith("res://"):
                rest = file_path[len("res://"):]
                rel_dir = rest.rsplit("/", 1)[0] if "/" in rest else ""
                joined = posixpath.normpath(
                    (rel_dir + "/" + target) if rel_dir else target)
                return "res://" + joined, None
            return None, None
        if nxt.get("kind") == "identifier":
            return None, nxt.get("value")
    return None, None
