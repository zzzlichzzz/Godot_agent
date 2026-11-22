# -*- coding: utf-8 -*-
"""Conservative GDScript lexical facts with exact source ranges."""

import re


_IDENT_START_RE = re.compile(r"[^\W\d]", re.U)
_IDENT_CONT_RE = re.compile(r"\w", re.U)
_DECL_KEYWORDS = {"class_name", "class", "func", "signal", "var", "const", "enum"}
_MODIFIERS = {"static"}


def _is_ident_start(char):
    return bool(char == "_" or _IDENT_START_RE.match(char))


def _is_ident_continue(char):
    return bool(char == "_" or _IDENT_CONT_RE.match(char))


def tokenize(text):
    """Return non-comment tokens while retaining strings and exact offsets."""
    tokens = []
    i, line, column, size = 0, 1, 1, len(text)
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
        if _is_ident_start(char):
            start, start_column = i, column
            i += 1
            column += 1
            while i < size and _is_ident_continue(text[i]):
                i += 1
                column += 1
            tokens.append({"kind": "identifier", "value": text[start:i],
                           "start": start, "end": i, "line": line,
                           "column": start_column})
            continue
        start_column = column
        two = text[i:i + 2]
        if two in ("->", "==", "!=", "<=", ">=", ":=", "&&", "||"):
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


def _line_indents(text):
    result = {}
    for number, raw in enumerate(text.splitlines(), 1):
        prefix = raw[:len(raw) - len(raw.lstrip(" \t"))]
        result[number] = sum(4 if char == "\t" else 1 for char in prefix)
    return result


def _next_identifier(tokens, index, stop_values=()):
    for pos in range(index, len(tokens)):
        token = tokens[pos]
        if token["kind"] == "newline" or token["value"] in stop_values:
            return None, pos
        if token["kind"] == "identifier":
            return token, pos
    return None, len(tokens)


def _declaration(kind, token, owner, path, extra=None):
    item = {
        "id": "gd:%s#%s:%s@%d" % (path, owner, kind, token["start"]),
        "kind": kind,
        "name": token["value"],
        "owner": owner,
        "start": token["start"],
        "end": token["end"],
        "line": token["line"],
        "column": token["column"],
    }
    if extra:
        item.update(extra)
    return item


def _check_export_annotation(tokens, pos):
    idx = pos - 1
    while idx >= 0 and tokens[idx]["kind"] == "newline":
        idx -= 1
    if idx >= 0 and tokens[idx]["value"] == ")":
        depth = 1
        idx -= 1
        while idx >= 0 and depth > 0:
            if tokens[idx]["value"] == ")":
                depth += 1
            elif tokens[idx]["value"] == "(":
                depth -= 1
            idx -= 1
    if idx >= 1:
        ident = tokens[idx]
        at = tokens[idx - 1]
        if at["value"] == "@" and ident["kind"] == "identifier":
            if ident["value"].startswith("export"):
                return True, ident["value"]
    return False, None

def _inside_brackets(tokens, pos):
    """Находится ли токен pos внутри незакрытой пары квадратных скобок.

    Отделяет Dictionary[String, Player] (где запятая разделяет ТИПЫ) от
    обычного списка аргументов: у вызова f(a, b) скобки круглые, поэтому
    проверка возвращает False и контекст остаётся прежним.
    """
    depth = 0
    for token in reversed(tokens[:pos]):
        if token["value"] == "]":
            depth += 1
        elif token["value"] == "[":
            if depth == 0:
                return True
            depth -= 1
    return False




def _parse_enum(tokens, pos, path, owner, declarations,
               declaration_positions, token_owners):
    """Разбирает `enum Имя { A, B = 1 }` и анонимный `enum { A, B }`.

    Возвращает True, если токен pos действительно начинал объявление enum.
    Members получают owner = id объявления enum: два разных enum в одном
    скрипте не должны считаться одним пространством имён, иначе
    переименование IDLE в одном enum задело бы одноимённый member другого.
    """
    scan = pos + 1
    name_token = None
    while scan < len(tokens):
        value = tokens[scan]["value"]
        if value == "{" or tokens[scan]["kind"] == "newline":
            break
        if tokens[scan]["kind"] == "identifier" and name_token is None:
            name_token = tokens[scan]
        scan += 1
    enum_owner = owner
    if name_token is not None:
        declaration = _declaration("enum", name_token, owner, path)
        declarations.append(declaration)
        declaration_positions.add(scan)
        token_owners[scan] = owner
        enum_owner = declaration["id"]
    # Тело: имя member — идентификатор сразу после "{" или ",", но не после
    # "=" (там уже значение, а не имя).
    expect_name = False
    depth = 0
    for p in range(scan, len(tokens)):
        token = tokens[p]
        if token["kind"] == "newline":
            continue
        value = token["value"]
        if value == "{":
            depth += 1
            expect_name = True
            continue
        if value == "}":
            depth -= 1
            if depth <= 0:
                break
            continue
        if value == "=":
            expect_name = False
            continue
        if value == ",":
            expect_name = True
            continue
        if token["kind"] == "identifier" and expect_name and depth == 1:
            member = _declaration("enum_member", token, enum_owner, path)
            declarations.append(member)
            declaration_positions.add(p)
            token_owners[p] = enum_owner
            expect_name = False
    return True


def parse(text, path=""):
    """Parse bounded semantic facts; unsupported syntax remains token facts."""
    tokens = tokenize(text)
    indents = _line_indents(text)
    declarations, declaration_positions = [], set()
    scopes = [{"owner": "script", "indent": -1, "kind": "script"}]
    token_owners = {}
    errors = []

    line_first = {}
    for pos, token in enumerate(tokens):
        if token["kind"] != "newline":
            line_first.setdefault(token["line"], pos)

    for pos, token in enumerate(tokens):
        if token["kind"] == "newline":
            continue
        indent = indents.get(token["line"], 0)
        if line_first.get(token["line"]) == pos:
            while len(scopes) > 1 and indent <= scopes[-1]["indent"]:
                scopes.pop()
        owner = scopes[-1]["owner"]
        token_owners[pos] = owner
        if token["kind"] != "identifier":
            continue
        value = token["value"]
        decl_kind = None
        if value == "class_name":
            decl_kind = "class_name"
        elif value == "class":
            decl_kind = "class"
        elif value == "func":
            decl_kind = "function"
        elif value == "signal":
            decl_kind = "signal"
        elif value == "var":
            decl_kind = "variable"
        elif value == "const":
            decl_kind = "constant"
        elif value == "enum":
            # enum разбираем целиком здесь: у него своё тело в скобках,
            # и обычная логика «объявление = одно имя» к нему не подходит.
            _parse_enum(tokens, pos, path, owner, declarations,
                        declaration_positions, token_owners)
            continue
        if decl_kind is None:
            continue
        name_token, name_pos = _next_identifier(tokens, pos + 1, (":", "=", "("))
        if name_token is None:
            if value in _DECL_KEYWORDS:
                errors.append("line %d: declaration without a name" % token["line"])
            continue
        extra = {}
        if decl_kind == "function" and pos > 0:
            prev = tokens[pos - 1]
            if prev["kind"] == "identifier" and prev["value"] in _MODIFIERS:
                extra["static"] = True
        elif decl_kind == "variable":
            is_export, export_type = _check_export_annotation(tokens, pos)
            if is_export:
                extra["is_export"] = True
                extra["export_annotation"] = export_type
        declaration = _declaration(decl_kind, name_token, owner, path, extra)
        declarations.append(declaration)
        declaration_positions.add(name_pos)
        token_owners[name_pos] = owner
        if decl_kind in ("class", "function"):
            scopes.append({"owner": declaration["id"], "indent": indent,
                           "kind": decl_kind})
        if decl_kind == "function":
            paren_start = None
            for p in range(name_pos + 1, len(tokens)):
                if tokens[p]["value"] == "(":
                    paren_start = p
                    break
                if tokens[p]["kind"] == "newline":
                    break
            if paren_start is not None:
                depth = 1
                p = paren_start + 1
                while p < len(tokens) and depth > 0:
                    tok = tokens[p]
                    if tok["value"] == "(":
                        depth += 1
                    elif tok["value"] == ")":
                        depth -= 1
                    elif depth == 1 and tok["kind"] == "identifier":
                        prev_tok = tokens[p - 1] if p > 0 else None
                        # Запятая внутри квадратных скобок — это граница ТИПА
                        # (Dictionary[String, Player]), а не новый параметр.
                        # Без проверки Player из такого словаря становился
                        # «объявлением параметра» и переименование его пропускало.
                        if (prev_tok and prev_tok["value"] in ("(", ",")
                                and not _inside_brackets(tokens, p)):
                            param_decl = _declaration("parameter", tok, declaration["id"], path)
                            declarations.append(param_decl)
                            declaration_positions.add(p)
                            token_owners[p] = declaration["id"]
                    p += 1

    references = []
    for pos, token in enumerate(tokens):
        if token["kind"] != "identifier" or pos in declaration_positions:
            continue
        value = token["value"]
        if value in _DECL_KEYWORDS or value in _MODIFIERS:
            continue
        prev = tokens[pos - 1] if pos else None
        nxt = tokens[pos + 1] if pos + 1 < len(tokens) else None
        context = "identifier"
        if prev and prev["value"] == ".":
            context = "member"
        elif nxt and nxt["value"] == "(":
            context = "call"
        elif prev and (prev["value"] in (":", "->", "extends", "as", "is")
                       or prev["value"] == "["):
            # "[" добавлен ради типизированных коллекций Godot 4:
            # Array[Player], Dictionary[String, Player]. Без этого имя класса
            # в квадратных скобках считалось обычным идентификатором, и любая
            # типизированная коллекция блокировала переименование.
            context = "type"
        elif nxt and nxt["value"] == "]":
            # закрывающая скобка: Dictionary[String, Player] -> имя типа перед
            # ней; вложенные Array[Array[Player]] разбираются тем же правилом.
            context = "type"
        elif prev and prev["value"] == "," and _inside_brackets(tokens, pos):
            # Dictionary[String, Player]: второй тип отделён запятой, а не
            # открывающей скобкой. Без этой ветки параметр функции вида
            # build(roster: Dictionary[String, Player]) не переименовывался.
            context = "type"
        elif prev and prev["value"] == "is" and nxt and nxt["value"] == "not":
            # "x is not Player": между "is" и именем стоит "not", поэтому
            # предыдущий токен для имени — не "is" и правило выше не срабатывает.
            context = "type"
        references.append({
            "name": value,
            "owner": token_owners.get(pos, "script"),
            "context": context,
            "start": token["start"], "end": token["end"],
            "line": token["line"], "column": token["column"],
        })

    strings = []
    for token in tokens:
        if token["kind"] == "string":
            strings.append({"value": token["value"], "start": token["start"],
                            "end": token["end"], "line": token["line"],
                            "column": token["column"]})
            if not token.get("closed"):
                errors.append("line %d: unclosed string" % token["line"])
    return {
        "parse_status": "ok" if not errors else "partial",
        "errors": errors[:8],
        "declarations": declarations,
        "references": references,
        "strings": strings,
    }
