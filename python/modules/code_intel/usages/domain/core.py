"""modules/code_intel/usages/domain/core.py - поиск использований символа (R-11).

Перенос read-only половины эталонного `symbol_refactor_part2.find_references`:
locator объявления → места использования с координатами, типом связи и
уверенностью (`proven` / `probable` / `dynamic`), причина в `note` для
недоказанных мест. Домен не знает про диск: индекс и тексты приносит `app.py`.

`analyze_rename` (что изменится, риски, снятые места) здесь нет намеренно: это
следующий срез того же модуля (`parity.md`, строка `analyze_rename`).
"""

import re

from python.formats import gdscript
from python.formats.gdscript.method_guards import NOTE, pairs
from python.kernel.errors import AppError
from python.modules.code_intel.shared import bound_names, symbol_index

from .evidence import (owner_shadows_name, reference_in_other_scope,
                       reference_is_safe, super_method, token_neighbors, unverified_reason)

KINDS = ("class_name", "function", "signal", "variable", "const", "enum",
         "enum_member")

#: Стратегии подготовки. Присвоенная месту уверенность от них не зависит.
MODES = ("strict", "probable")

KEYWORDS = {
    "and", "as", "assert", "await", "break", "breakpoint", "class",
    "class_name", "const", "continue", "elif", "else", "enum", "extends",
    "for", "func", "if", "in", "is", "match", "not", "or", "pass",
    "preload", "return", "self", "signal", "static", "super", "var", "while",
}

#: Публичный `kind` -> вид объявления в парсере: парсер зовёт константу
#: `constant`, а инструмент — `const` (так его понимает модель).
KIND_TO_DECL = {"const": "constant", "enum": "enum"}

#: Что парсер вообще объявляет: нужно для подсказки «что есть в файле».
DECL_KINDS = {"class_name", "class", "function", "signal", "variable",
              "constant", "enum", "enum_member", "parameter"}

IDENTIFIER = re.compile(r"^[^\W\d]\w*$", re.U)
LOCATOR = re.compile(r"^(res://.+\.gd):(\d+)(?::(\d+))?$")

#: Перед какими API строка с именем символа — реальная ссылка, а не текст.
#: Вывод из сигнатур Godot, а не догадка; `print("Player")` сюда не входит.
DYNAMIC_STRING_CALLS = {
    "instantiate": "ClassDB.instantiate",
    "set": "set() по имени",
    "get": "get() по имени",
    "has_signal": "has_signal()",
    "has_method": "has_method()",
    "emit_signal": "emit_signal()",
    "is_connected": "is_connected()",
    "call": "call() по имени",
    "call_deferred": "call_deferred() по имени",
    "connect": "connect() по имени",
    "disconnect": "disconnect() по имени",
    "get_signal": "get_signal()",
    "tr": "tr() по имени",
    "translate": "translate() по имени",
    "to_upper": "to_upper()",
    "to_lower": "to_lower()",
    "capitalize": "capitalize()",
}


class Query(object):
    """Разобранный запрос: что искать и где объявление."""

    __slots__ = ("kind", "old_name", "new_name", "declaration", "path", "line",
                 "column", "mode", "allow_unverified")

    def __init__(self, kind, old_name, new_name, declaration, path, line, column,
                 mode="strict", allow_unverified=False):
        self.kind = kind
        self.old_name = old_name
        self.new_name = new_name
        self.declaration = declaration
        self.path = path
        self.line = line
        self.column = column
        self.mode = mode
        self.allow_unverified = allow_unverified


def build_query(kind, old_name, new_name, declaration):
    """Проверить запрос по правилам эталона; ошибки — `invalid_input`."""
    kind_text, name = validate_symbol(kind, old_name)
    new_text = str(new_name or "").strip()
    if new_text and (not IDENTIFIER.match(new_text) or new_text in KEYWORDS):
        raise AppError("invalid_input",
                       "new_name не является допустимым идентификатором GDScript",
                       hint="new_name нужен только analyze_rename: для поиска его можно не передавать")
    path, line, column = parse_locator(declaration)
    return Query(kind_text, name, new_text, declaration, path, line, column)


def validate_symbol(kind, old_name):
    kind_text = str(kind or "").strip()
    name = str(old_name or "").strip()
    if kind_text not in KINDS:
        raise AppError("invalid_input",
                       "kind должен быть одним из: %s" % ", ".join(sorted(KINDS)),
                       hint="Вид символа берётся из объявления")
    if not IDENTIFIER.match(name) or name in KEYWORDS:
        raise AppError("invalid_input",
                       "old_name не является допустимым идентификатором GDScript",
                       hint="Имя символа — как в объявлении, без кавычек")
    return kind_text, name


def build_rename_query(kind, old_name, new_name, declaration, mode=None,
                       allow_unverified=None):
    """Запрос `analyze_rename`: тот же поиск плюс обязательное новое имя (R-15).

    `allow_unverified` расширяет список затрагиваемых путей вероятными ссылками;
    строгий отказ из-за динамических строк проверяет компилятор плана.
    """
    if not str(new_name or "").strip():
        raise AppError("invalid_input",
                       "new_name обязателен: analyze_rename отвечает на вопрос "
                       "«что изменится при переименовании»",
                       hint="Укажи новое имя символа — допустимый идентификатор GDScript")
    mode_text = str(mode or "strict").strip()
    if mode_text not in MODES:
        raise AppError("invalid_input",
                       "mode должен быть одним из: %s" % ", ".join(MODES),
                       hint="strict — консервативно; probable эталон применяет "
                            "только при подготовке переименования")
    if allow_unverified is None:
        allow_unverified = False
    if not isinstance(allow_unverified, bool):
        raise AppError("invalid_input",
                       "allow_unverified должен быть true или false, получено: %r"
                       % (allow_unverified,))
    query = build_query(kind, old_name, new_name, declaration)
    query.mode = mode_text
    query.allow_unverified = allow_unverified
    return query


def parse_locator(declaration):
    """`res://path.gd:LINE[:COL]` → `(path, line, column|None)`."""
    raw = str(declaration or "").strip().replace("\\", "/")
    match = LOCATOR.match(raw)
    if not match:
        raise AppError("invalid_input",
                       "declaration должен иметь вид res://path.gd:line[:column]",
                       hint="Строка объявления — из search или functions")
    line = int(match.group(2))
    column = int(match.group(3)) if match.group(3) else None
    if line < 1 or (column is not None and column < 1):
        raise AppError("invalid_input",
                       "Строка и колонка declaration должны быть положительными")
    return match.group(1), line, column


def declaration_kind(kind):
    """Вид объявления в парсере для публичного `kind`."""
    return KIND_TO_DECL.get(kind, kind)


def locate(declarations, query):
    """Единственное объявление по locator'у или `not_found` со списком имён."""
    candidates = [item for item in declarations
                  if item.get("path") == query.path and item.get("line") == query.line
                  and item.get("kind") == declaration_kind(query.kind)
                  and item.get("name") == query.old_name
                  and (query.column is None or item.get("column") == query.column)]
    if len(candidates) == 1:
        return candidates[0]
    available = sorted({item.get("name") for item in declarations
                        if item.get("path") == query.path
                        and item.get("kind") in DECL_KINDS and item.get("name")})
    raise AppError(
        "not_found",
        "В %s:%d нет объявления вида %s с именем %s. Объявления этого скрипта: %s."
        % (query.path, query.line, query.kind, query.old_name,
           ", ".join(available[:12]) or "нет"),
        hint="Возьми точную строку объявления из search или functions")


def exact_string_value(raw):
    """Значение строкового литерала без кавычек (одинарных и тройных)."""
    if len(raw) < 2:
        return ""
    width = 3 if raw[:3] in ('"""', "'''") else 1
    return raw[width:-width] if len(raw) >= width * 2 else ""


def classify_string_reference(tokens, start):
    """Строка рядом с API, работающим по имени, — ссылка; иначе None.

    Решает БЛИЖАЙШИЙ идентификатор слева: `print("Player")` — текст,
    `Node.call("Player")` — ссылка по имени.
    """
    pos = None
    for index, token in enumerate(tokens):
        if token.get("start") == start and token.get("kind") == "string":
            pos = index
            break
    if pos is None:
        return None
    previous = tokens[pos - 1] if pos else None
    if previous is not None and previous["value"] == "(":
        previous = tokens[pos - 2] if pos >= 2 else None
    if previous is None:
        return None
    call = previous
    if previous["value"] == ".":
        # Точка непосредственно перед именем вызова — редкая, но возможная форма.
        call = tokens[pos - 2] if pos >= 2 else None
        owner = tokens[pos - 3] if pos >= 3 else None
        if owner is None or call is None:
            return None
    elif pos >= 4 and tokens[pos - 3]["value"] == ".":
        owner = tokens[pos - 4]
    else:
        owner = None
    if owner is not None and owner["value"] == "ClassDB":
        known = DYNAMIC_STRING_CALLS.get(call["value"])
        if known:
            return known
    return DYNAMIC_STRING_CALLS.get(call["value"])


def find(index, query):
    """Места использования символа: список, счётчики и эхо запроса."""
    declarations = [item for entry in index["files"] for item in entry["declarations"]]
    declaration = locate(declarations, query)
    target_entry = next((entry for entry in index["files"]
                         if entry["path"] == query.path), None)
    if target_entry is None:
        raise AppError("not_found", "файл объявления не попал в индекс: %s"
                       % query.path)
    target_class = symbol_index.class_name_for(target_entry)
    subclass_paths = symbol_index.subclasses(index, query.path, target_class)
    all_target_classes = {target_class} if target_class else set()
    for sub_path in subclass_paths:
        sub_entry = symbol_index.entry_for(index, sub_path)
        if sub_entry:
            sub_class = symbol_index.class_name_for(sub_entry)
            if sub_class:
                all_target_classes.add(sub_class)
    usages = [{"path": declaration["path"], "line": declaration.get("line"),
               "column": declaration.get("column") or 1, "link": "declaration",
               "confidence": "proven", "note": None}]
    resolve_super = (super_method(index, query.old_name) if query.kind == "function"
                     and declaration["owner"] == "script" else None)
    for entry in index["files"]:
        tokens = gdscript.tokenize(entry["text"])
        typed = _typed(entry)
        for fact in entry["references"]:
            if fact.get("name") != query.old_name:
                continue
            if reference_in_other_scope(fact, declaration, query.kind, declarations):
                continue
            # Локальная тень — доказанно ДРУГАЯ сущность: место исключается.
            if (query.kind in ("variable", "const", "enum", "enum_member",
                               "class_name")
                    and fact.get("context") != "member"
                    and owner_shadows_name(fact.get("owner"), fact.get("name"),
                                           entry["declarations"])):
                continue
            parent_method = resolve_super(entry, fact, tokens) if resolve_super else None
            if parent_method is not None and parent_method != declaration:
                continue
            safe = parent_method is not None or reference_is_safe(
                query.kind, fact, tokens, query.path, entry["path"], target_class,
                declarations, subclass_paths, all_target_classes,
                declaration.get("owner"), typed)
            usages.append({
                "path": entry["path"], "line": fact.get("line"),
                "column": fact.get("column") or 1,
                "link": fact.get("context") or "identifier",
                "confidence": "proven" if safe else "probable",
                "note": None if safe else (
                    unverified_reason(
                        query.kind, fact, tokens, query.path, entry["path"],
                        target_class, declarations, subclass_paths,
                        all_target_classes, declaration.get("owner"), typed)
                    or "не доказано: связь с символом не установлена")})
        guards = {t['start'] for t,_ in pairs(tokens,query.old_name)} if query.kind == 'function' else set()
        for fact in entry["strings"]:
            if exact_string_value(str(fact.get("value") or "")) != query.old_name:
                continue
            reason = classify_string_reference(tokens, fact.get("start"))
            if reason:
                usages.append({
                    "path": entry["path"], "line": fact.get("line"),
                    "column": fact.get("column") or 1, "link": "string",
                    "confidence": "dynamic", "note": NOTE if fact['start'] in guards else reason})
    if query.kind in ('function','signal') and declaration['owner'] == 'script':
        owners = bound_names.script_owners(index,declaration)
        for path,text in bound_names.sources(index,owners):
            usages.extend(dict(path=path,line=l,column=c,link=link,confidence='proven',note=None)
                          for l,c,link in bound_names.places(path,text,query.kind,query.old_name,owners))
    usages.sort(key=lambda item: (item["path"], item["line"], item["column"]))
    by_link = {}
    for place in usages:
        by_link[place["link"]] = by_link.get(place["link"], 0) + 1
    return {"kind": query.kind, "old_name": query.old_name,
            "new_name": query.new_name, "declaration": query.declaration,
            "usages": usages, "by_link": by_link,
            "proven_count": sum(1 for item in usages if item["confidence"] == "proven"),
            "probable_count": sum(1 for item in usages if item["confidence"] == "probable"),
            "dynamic_count": sum(1 for item in usages if item["confidence"] == "dynamic")}


def analyze(index, query):
    """Предпросмотр переименования: тот же поиск, другой отчёт (part2:685-718).

    Второго обхода файлов нет: `find` уже дал места с доказательствами, здесь
    только группировка — затронутые файлы с учётом allow_unverified
    и риски строками. Формат строки эталонный: его
    читают человек и модель, поэтому в объекты он не превращается.
    """
    result = find(index, query)
    usages = result["usages"]
    return {
        "kind": query.kind, "old_name": query.old_name,
        "new_name": query.new_name, "declaration": query.declaration,
        "allow_unverified": bool(query.allow_unverified),
        "mode": query.mode or "strict",
        "usages": usages,
        "affected_paths": sorted({item["path"] for item in usages
                                   if item["confidence"] == "proven" or
                                   (item["confidence"] == "probable" and query.allow_unverified)}),
        "risks": [risk_line(item) for item in usages
                  if item["confidence"] != "proven"],
        "by_link": result["by_link"],
        "proven_count": result["proven_count"],
        "probable_count": result["probable_count"],
        "dynamic_count": result["dynamic_count"],
        "declaration_path": query.path,
        "declaration_line": query.line,
    }


def risk_line(place):
    """Строка риска в формате эталона: `path:line [link, confidence] — note`."""
    note = place.get("note")
    return "%s:%s [%s, %s]%s" % (place["path"], place["line"], place["link"],
                                 place["confidence"],
                                 (" — " + note) if note else "")


def _typed(entry):
    """Явные типы ресиверов из объявлений файла (инференс не угадывается).

    Парсер не заполняет `type`, поэтому словарь пуст — ровно как у эталона:
    доказательства через аннотации ресивера здесь не срабатывают, и это не
    регресс переноса, а перенос поведения как есть.
    """
    return {item.get("name"): item.get("type") for item in entry["declarations"]
            if item.get("type")}

