# -*- coding: utf-8 -*-
"""Conservative, hash-guarded GDScript symbol renames."""

import hashlib
import os
import re
import tempfile
import threading

import gd_api_cache
import gd_api_check
import gd_lint
import gd_semantic_parser
import history_manager
import scene_deps
from minilich import ml_project_index
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path)


KINDS = {"class_name", "function", "signal", "variable", "const", "enum",
         "enum_member"}
# Вид, которым оперирует rename_symbol, -> вид объявления в парсере.
# Имена не совпадают исторически: парсер называет константу "constant",
# а публичный action говорит "const" (так его понимает модель).
_KIND_TO_DECL = {"const": "constant", "enum": "enum"}
# Обратное отображение для проверок вида объявления.
_DECL_TO_KIND = {value: key for key, value in _KIND_TO_DECL.items()}
# Все виды объявлений, которые парсер вообще отдаёт: нужны для подсказки
# в сообщении об ошибке («что этот скрипт объявляет на самом деле»).
_DECL_KINDS = {"class_name", "class", "function", "signal", "variable",
               "constant", "enum", "enum_member", "parameter"}


def _owner_is_top_level(owner, declarations):
    """Owner принадлежит верхнему уровню скрипта.

    Цепочка поднимается до самого скрипта, поэтому вложенный класс внутри
    вложенного (class Deep внутри class Outer) тоже считается верхним
    уровнем — его имя стабильно и переименовываемо текстом.
    """
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current != "script" and current not in seen:
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration:
            return False
        if declaration.get("kind") not in ("class", "function", "enum"):
            return False
        current = declaration.get("owner")
    return current == "script"


def _owner_within(owner, root, declarations):
    """Владелец ссылки находится внутри root (сам root — это объявление класса).

    Нужно, чтобы переименование члена вложенного класса трогало только его
    собственные ссылки: одноимённый член ВНЕШНЕГО скрипта — другая
    сущность, и её переименование сломало бы внешний код.
    """
    if root is None:
        return owner == "script"
    current = owner
    for _ in range(64):
        if current == root:
            return True
        parent = next((item.get("owner") for item in declarations
                       if item.get("id") == current), None)
        if parent is None or parent == current:
            return False
        current = parent
    return False


def _owner_is_script_scope(declaration, declarations):
    """Объявление принадлежит самому скрипту, а не вложенному классу."""
    return declaration.get("owner") == "script"


def _reference_in_other_scope(fact, declaration, kind, declarations):
    """Ссылка принадлежит scope, отличному от scope нашего объявления.

    Вложенный класс в Godot НЕ наследует внешний скрипт, поэтому член с тем
    же именем во вложенном классе (или снаружи, если мы переименовываем
    член вложенного) — другая сущность, а не ссылка на наш символ.
    """
    if kind not in ("function", "signal", "variable", "const", "enum"):
        return False
    owner = declaration.get("owner")
    if owner == "script":
        return not _owner_belongs_to_script(fact.get("owner"), declarations)
    return not _owner_within(fact.get("owner"), owner, declarations)


def _decl_kind(kind):
    """Вид объявления в парсере для публичного kind (или сам kind)."""
    return _KIND_TO_DECL.get(kind, kind)
# Режимы гранулярности отказа (Этап 2.4). strict — поведение по умолчанию,
# полностью консервативное. probable сознательно снимает блокировку с
# НЕПРОВЕРЕННЫХ ссылок, но оставляет все жёсткие проверки на месте.
# Уровень dynamic — это не режим, а класс находок: ссылки, найденные
# только по строке, попадают в отчёт при любом режиме.
MODES = ("strict", "probable")
_IDENTIFIER = re.compile(r"^[^\W\d]\w*$", re.U)
_KEYWORDS = {
    "and", "as", "assert", "await", "break", "breakpoint", "class",
    "class_name", "const", "continue", "elif", "else", "enum", "extends",
    "for", "func", "if", "in", "is", "match", "not", "or", "pass",
    "preload", "return", "self", "signal", "static", "super", "var", "while",
}
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_MAX_SOURCE_CHARS = 200000
_replace_file = os.replace


class RenameError(ValueError):
    pass


class StaleRenameError(RuntimeError):
    pass


def _project_lock(project_root):
    key = os.path.normcase(os.path.realpath(project_root or "."))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read_source(project_root, path):
    absolute = _resolve_safe_path(project_root, path)
    if not os.path.isfile(absolute):
        raise RenameError("Файл объявления не найден: %s" % path)
    with open(absolute, "rb") as handle:
        raw = handle.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RenameError("Файл должен быть в UTF-8: %s" % path)
    if len(text) > _MAX_SOURCE_CHARS:
        raise RenameError("Файл слишком велик для безопасного рефакторинга: %s" % path)
    return absolute, raw, text, bom


def _parse_locator(value):
    raw = str(value or "").strip().replace("\\", "/")
    match = re.match(r"^(res://.+\.gd):(\d+)(?::(\d+))?$", raw)
    if not match:
        raise RenameError("declaration должен иметь вид res://path.gd:line[:column]")
    line = int(match.group(2))
    column = int(match.group(3)) if match.group(3) else None
    if line < 1 or (column is not None and column < 1):
        raise RenameError("Строка и колонка declaration должны быть положительными")
    return match.group(1), line, column


def _move_with_uid(project_root, file_rename, moved):
    """Переносит .gd вместе с его .uid, записывая шаг для отката.

    .uid Godot генерирует рядом со скриптом и связывает ресурс по имени файла,
    поэтому оставить старый .uid значит потерять связь сцен с переименованным
    скриптом. Переносим оба файла и только потом считаем шаг выполненным —
    так частичного переноса при сбое не остаётся.
    """
    source = _resolve_safe_path(project_root, file_rename["from"])
    dest = _resolve_safe_path(project_root, file_rename["to"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    step = {"source_absolute": source, "dest_absolute": dest}
    _replace_file(source, dest)
    # Шаг отката регистрируем СРАЗУ после переноса .gd, до переноса .uid:
    # иначе сбой на .uid оставил бы скрипт на новом месте без шанса
    # вернуть его обратно.
    moved.append(step)
    if os.path.isfile(source + ".uid"):
        _replace_file(source + ".uid", dest + ".uid")
        step["dest_uid"] = dest + ".uid"
        step["source_uid"] = source + ".uid"


def _plan_file_rename(project_root, target_path, new_name, addon_dir):
    """План переноса .gd под новое имя класса (вместе с .uid)."""
    directory = target_path.rsplit("/", 1)[0]
    new_path = "%s/%s.gd" % (directory, scene_deps.to_snake(new_name))
    if new_path == target_path:
        return None
    if not can_write_project_path(
            new_path, project_root, addon_dir=addon_dir):
        raise RenameError("Новое имя файла защищено текущей политикой доступа: %s"
                          % new_path)
    absolute = _resolve_safe_path(project_root, new_path)
    if os.path.exists(absolute):
        raise RenameError("Файл с новым именем уже существует: %s" % new_path)
    return {"from": target_path, "to": new_path}


def _validate_action(action):
    if not isinstance(action, dict):
        raise RenameError("rename_symbol должен быть объектом")
    kind = str(action.get("kind") or "").strip()
    old_name = str(action.get("old_name") or "").strip()
    new_name = str(action.get("new_name") or "").strip()
    if kind not in KINDS:
        raise RenameError("kind должен быть %s" % ", ".join(sorted(KINDS)))
    for label, name in (("old_name", old_name), ("new_name", new_name)):
        if not _IDENTIFIER.match(name) or name in _KEYWORDS:
            raise RenameError("%s не является допустимым идентификатором GDScript" % label)
    if old_name == new_name:
        raise RenameError("Новое имя совпадает со старым")
    path, line, column = _parse_locator(action.get("declaration"))
    # rename_file: переименовать ли сам .gd вместе с class_name. По умолчанию
    # НЕТ: имя файла может не совпадать с классом (hero.gd с class_name Unit),
    # и молчаливый перенос ломал бы preload() и пути в сценах.
    rename_file = bool(action.get("rename_file"))
    if rename_file and kind != "class_name":
        raise RenameError("rename_file применим только к class_name")
    # Режим отказа: strict по умолчанию. Неизвестное значение молчать не
    # должно — иначе опечатка в действии незаметно ослабит проверки.
    mode = str(action.get("mode") or "strict").strip().lower()
    if mode not in MODES:
        raise RenameError("mode должен быть %s" % " или ".join(MODES))
    return (kind, old_name, new_name, path, line, column, mode, rename_file)


def _token_neighbors(tokens, start):
    for index, token in enumerate(tokens):
        if token.get("start") == start:
            prev = tokens[index - 1] if index else None
            prev2 = tokens[index - 2] if index > 1 else None
            nxt = tokens[index + 1] if index + 1 < len(tokens) else None
            return prev2, prev, nxt
    return None, None, None


def _typed_receivers(text):
    """Return explicit local/field/parameter types without guessing inference."""
    tokens = gd_semantic_parser.tokenize(text)
    result = {}
    for index, token in enumerate(tokens):
        if token.get("value") not in ("var", "const") or index + 3 >= len(tokens):
            continue
        name, colon, type_token = tokens[index + 1:index + 4]
        if (name.get("kind") == "identifier" and colon.get("value") == ":"
                and type_token.get("kind") == "identifier"):
            result[name["value"]] = type_token["value"]

    # Parameters are accepted only inside an actual func(...) signature.
    for index, token in enumerate(tokens):
        if token.get("value") != "func":
            continue
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor].get("value") != "(":
            if tokens[cursor].get("kind") == "newline":
                break
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].get("value") != "(":
            continue
        depth = 1
        cursor += 1
        while cursor + 2 < len(tokens) and depth:
            value = tokens[cursor].get("value")
            if value == "(":
                depth += 1
            elif value == ")":
                depth -= 1
            elif depth == 1:
                name, colon, type_token = tokens[cursor:cursor + 3]
                previous = tokens[cursor - 1].get("value") if cursor else None
                if (previous in ("(", ",") and name.get("kind") == "identifier"
                        and colon.get("value") == ":"
                        and type_token.get("kind") == "identifier"):
                    result[name["value"]] = type_token["value"]
                    cursor += 2
            cursor += 1
    return result


def _owner_in_script(owner, declarations):
    """Ссылка принадлежит этому же скрипту, включая вложенные классы.

    Отличается от _owner_belongs_to_script, который намеренно обрывается на
    вложенном классе: он был нужен, когда переименование членов вложенных
    классов вообще не поддерживалось.
    """
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current != "script" and current not in seen:
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration:
            return False
        current = declaration.get("owner")
    return current == "script"


def _exact_string_value(raw):
    if len(raw) < 2:
        return ""
    width = 3 if raw[:3] in ('"""', "'''") else 1
    return raw[width:-width] if len(raw) >= width * 2 else ""


def _class_name_for_file(semantic):
    names = [item.get("name") for item in semantic.get("declarations", [])
             if item.get("kind") == "class_name"]
    return names[0] if len(names) == 1 else None


def _owner_belongs_to_script(owner, declarations):
    """Reject references whose lexical owner crosses a nested class."""
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current != "script" and current not in seen:
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration or declaration.get("kind") == "class":
            return False
        current = declaration.get("owner")
    return current == "script"


def _owner_shadows_name(owner, name, declarations):
    return any(item.get("owner") == owner and item.get("name") == name
               and item.get("kind") in ("variable", "constant", "parameter")
               for item in declarations)


def _get_script_parent(text, file_path):
    """Return (parent_path, parent_class) for a script's extends clause."""
    tokens = gd_semantic_parser.tokenize(text)
    for i, t in enumerate(tokens):
        if t.get("value") == "extends" and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.get("kind") == "string":
                val = _exact_string_value(nxt.get("value", ""))
                if val.startswith("res://"):
                    return val, None
                base_dir = os.path.dirname(file_path)
                norm = os.path.normpath(os.path.join(base_dir, val)).replace("\\", "/")
                return norm, None
            elif nxt.get("kind") == "identifier":
                return None, nxt.get("value")
    return None, None


def _find_subclasses(project_root, target_path, target_class, snapshot):
    """Find all GDScript files in the project that inherit from target_path or target_class."""
    parent_map = {}
    class_map = {}
    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        if not path.endswith(".gd"):
            continue
        cls_name = _class_name_for_file(entry["semantic"])
        if cls_name:
            class_map[path] = cls_name
        try:
            _abs, _raw, text, _bom = _read_source(project_root, path)
            p_path, p_cls = _get_script_parent(text, path)
            if p_path or p_cls:
                parent_map[path] = (p_path, p_cls)
        except Exception:
            continue

    subclasses = set()
    queue = [target_path]
    target_classes = {target_class} if target_class else set()

    while queue:
        curr = queue.pop(0)
        curr_cls = class_map.get(curr)
        if curr_cls:
            target_classes.add(curr_cls)
        for child_path, (p_path, p_cls) in parent_map.items():
            if child_path in subclasses or child_path == target_path:
                continue
            is_child = False
            if p_path and p_path == curr:
                is_child = True
            elif p_cls and p_cls in target_classes:
                is_child = True
            if is_child:
                subclasses.add(child_path)
                queue.append(child_path)

    return subclasses


def _section_node_path(header):
    """Путь узла по заголовку секции .tscn (или пустая строка)."""
    attrs = dict(re.findall(r'([\w]+)="([^"]*)"', header))
    name = attrs.get("name", "")
    parent = attrs.get("parent")
    if parent is None:
        return "."
    if parent == ".":
        return name
    return parent + "/" + name


def _scene_script_owners(project_root, scene_res, cache, seen=None):
    """Множество res://путей скриптов, узлы с которыми встречаются в сцене.

    Учитывает и ПРЯМОЕ указание script = ExtResource(...), и ИНСТАНЦИРОВАНИЕ
    (node ... instance = ExtResource("...tscn")): у инстанцированной сцены
    свой скрипт в ext_resource родителя отсутствует, но переопределения
    свойств в родителе относятся именно к нему.
    """
    seen = seen if seen is not None else set()
    if scene_res in seen:
        return set()
    seen.add(scene_res)
    if scene_res in cache:
        return cache[scene_res]
    try:
        abs_path = _resolve_safe_path(project_root, scene_res)
        with open(abs_path, "rb") as handle:
            text = handle.read().decode("utf-8-sig")
    except Exception:
        cache[scene_res] = set()
        return set()
    try:
        ext, nodes, _connections = scene_deps.parse_scene(text)
    except Exception:
        cache[scene_res] = set()
        return set()
    owners = set()
    for key, info in ext.items():
        if info.get("type") == "Script" and info.get("path"):
            owners.add(info["path"])
    for node in nodes:
        instance_id = node.get("instance_id")
        if not instance_id:
            continue
        target = ext.get(instance_id, {}).get("path")
        if target and target.lower().endswith(".tscn"):
            owners |= _scene_script_owners(project_root, target, cache, seen)
    cache[scene_res] = owners
    return owners


def _collect_scene_property_edits(project_root, affected_scripts, old_name, new_name,
                                  allow_addons=False, allow_self_edit=False,
                                  addon_dir=None):
    """Find all .tscn and .tres files referencing affected_scripts and update old_name property."""
    scene_edits = []
    if not affected_scripts:
        return scene_edits
    # Кэш «сцена -> скрипты её узлов» на весь проход: одна и та же сцена
    # инстанцируется из многих мест, перечитывать её каждый раз незачем.
    scene_owner_cache = {}

    for root, dirs, files in os.walk(project_root):
        if not allow_addons and ("addons" in dirs):
            dirs.remove("addons")
        for d in list(dirs):
            if d in {".git", ".godot", ".import", ".agent_history", "__pycache__", "build", "dist"}:
                dirs.remove(d)
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".tscn", ".tres"):
                continue
            abs_path = os.path.join(root, name)
            rel_path = "res://" + os.path.relpath(abs_path, project_root).replace("\\", "/")
            if not can_write_project_path(
                    rel_path, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            try:
                with open(abs_path, "rb") as handle:
                    raw = handle.read()
                bom = raw.startswith(b"\xef\xbb\xbf")
                text = raw.decode("utf-8-sig")
            except Exception:
                continue

            matching_ids = set()
            for script_path in affected_scripts:
                pattern1 = re.compile(
                    r'\[ext_resource\s+[^\]]*path=["\']' + re.escape(script_path) + r'["\'][^\]]*id=["\']?([^"\'\]\s]+)["\']?[^\]]*\]'
                )
                for m in pattern1.finditer(text):
                    matching_ids.add(m.group(1))

                pattern2 = re.compile(
                    r'\[ext_resource\s+[^\]]*id=["\']?([^"\'\]\s]+)["\']?[^\]]*path=["\']' + re.escape(script_path) + r'["\'][^\]]*\]'
                )
                for m in pattern2.finditer(text):
                    matching_ids.add(m.group(1))

            # Раньше здесь стоял ранний выход «нет matching_ids — пропускаем
            # файл». Он и был причиной потери: у инстанцирующей сцены в
            # ext_resource нет нашего скрипта, и файл уходил целиком,
            # вместе с переопределениями свойств.
            # Секции с нашим скриптом и секции, которые ИНСТАНЦИРУЮТ сцену с
            # нашим скриптом: у инстанцированной сцены в ext_resource родителя
            # скрипта нет, поэтому раньше такие переопределения терялись молча.
            instanced_paths = set()
            scene_nodes = []
            if rel_path.lower().endswith(".tscn"):
                try:
                    scene_ext, scene_nodes, _c = scene_deps.parse_scene(text)
                except Exception:
                    scene_ext, scene_nodes = {}, []
                wanted_instance_ids = {
                    key for key, info in scene_ext.items()
                    if (info.get("type") == "PackedScene" and info.get("path")
                        and _scene_script_owners(
                            project_root, info["path"], scene_owner_cache)
                        & affected_scripts)}
                instanced_paths = {node.get("path") for node in scene_nodes
                                   if node.get("instance_id") in wanted_instance_ids}

            section_re = re.compile(r'(^\[(?:node|sub_resource|resource)[^\]]*\])(.*?)(?=(?:^\[|\Z))', re.M | re.S)
            file_changed = False
            total_occurrences = 0

            new_text_parts = []
            last_end = 0
            for sec_match in section_re.finditer(text):
                header = sec_match.group(1)
                body = sec_match.group(2)
                sec_start = sec_match.start()
                sec_end = sec_match.end()

                has_script = False
                for mid in matching_ids:
                    if re.search(r'script\s*=\s*ExtResource\(["\']?' + re.escape(mid) + r'["\']?\)', body):
                        has_script = True
                        break
                if not has_script and _section_node_path(header) in instanced_paths:
                    # Переопределение свойства внутри инстанцированного узла:
                    # ключ свойства принадлежит скрипту ИНСТАНЦИРУЕМОЙ сцены.
                    has_script = True

                if not has_script:
                    continue

                prop_re = re.compile(r'^([ \t]*)' + re.escape(old_name) + r'([ \t]*=.*)$', re.M)
                new_body, count = prop_re.subn(r'\g<1>' + new_name + r'\g<2>', body)
                if count > 0:
                    file_changed = True
                    total_occurrences += count
                    new_text_parts.append(text[last_end:sec_start])
                    new_text_parts.append(header + new_body)
                    last_end = sec_end

            if file_changed:
                new_text_parts.append(text[last_end:])
                after = "".join(new_text_parts)
                encoded = ((b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8"))
                diff = build_diff_preview(text, after)
                diff["path"] = rel_path
                diff["action"] = "rename_symbol"
                scene_edits.append({
                    "path": rel_path,
                    "absolute": abs_path,
                    "before_hash": _sha256(raw),
                    "before_bytes": raw,
                    "after_bytes": encoded,
                    "diff": diff,
                    "occurrences": total_occurrences,
                })

    return scene_edits


_CONN_HEADER_RE = re.compile(r'^\[connection\s+([^\]]*)\]$')
_CONN_FIELD_RE = re.compile(r'(\w+)="([^"]*)"')


def _connection_replacement(text, script_ids, node_paths, kind, old_name, new_name):
    """Переименовывает signal= и method= в [connection], где оба конца известны.

    Отвечаем ТОЛЬКО за те связи, у которых и источник, и приёмник — узлы с
    нужным нам скриптом (script_ids из ext_resource, node_paths — пути этих
    узлов). Если method указывает на метод другого узла — этот узел не несёт
    наш скрипт, и такой текст не трогаем: иначе мы бы сломали чужой обработчик.
    """
    if not script_ids:
        return text, 0
    changes = 0
    # Разбиваем по сохраняемым переводам строк: .tscn в Windows-проектах
    # часто лежит в CRLF, и нормализация в LF переписывала бы весь файл
    # целиком (Godot такой diff не покажет, а линтер и git увидят).
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    for index, line in enumerate(lines):
        match = _CONN_HEADER_RE.match(line.strip())
        if not match:
            continue
        attrs = dict(_CONN_FIELD_RE.findall(match.group(1)))
        source = attrs.get("from", "")
        target = attrs.get("to", "")
        if source not in node_paths or target not in node_paths:
            continue
        field = "signal" if kind == "signal" else "method"
        if attrs.get(field) != old_name:
            continue
        new_header = _CONN_HEADER_RE.sub(
            lambda m: m.group(0).replace('%s="%s"' % (field, old_name),
                                       '%s="%s"' % (field, new_name)),
            line.strip(), count=1)
        lines[index] = line.replace(line.strip(), new_header)
        changes += 1
    return eol.join(lines), changes


def _collect_scene_connection_edits(project_root, affected_scripts, kind,
                                    old_name, new_name, allow_addons=False,
                                    allow_self_edit=False, addon_dir=None):
    """Собирает правки [connection] для сцен, чьи узлы несут нужный скрипт."""
    edits = []
    if kind not in ("signal", "function") or not affected_scripts:
        return edits
    wanted = set(affected_scripts)
    for root, dirs, files in os.walk(project_root):
        if not allow_addons and ("addons" in dirs):
            dirs.remove("addons")
        for d in list(dirs):
            if d in {".git", ".godot", ".import", ".agent_history",
                     "__pycache__", "build", "dist"}:
                dirs.remove(d)
        for name in files:
            if not name.lower().endswith(".tscn"):
                continue
            abs_path = os.path.join(root, name)
            rel_path = "res://" + os.path.relpath(
                abs_path, project_root).replace("\\", "/")
            if not can_write_project_path(
                    rel_path, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            try:
                with open(abs_path, "rb") as handle:
                    raw = handle.read()
                text = raw.decode("utf-8-sig")
            except Exception:
                continue
            bom = raw.startswith(b"\xef\xbb\xbf")
            try:
                ext, nodes, _connections = scene_deps.parse_scene(text)
            except Exception:
                continue
            # parse_scene отдаёт ext как {id: {type, path}}: идентификатор лежит
            # в КЛЮЧЕ, а не в значении — иначе script_id узлов не совпадёт.
            script_ids = {key for key, info in ext.items()
                          if info.get("path") in wanted}
            if not script_ids:
                continue
            node_paths = {node.get("path") for node in nodes
                          if node.get("script_id") in script_ids}
            if not node_paths:
                continue
            after, count = _connection_replacement(
                text, script_ids, node_paths, kind, old_name, new_name)
            if not count:
                continue
            encoded = (b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8")
            diff = build_diff_preview(text, after)
            diff["path"] = rel_path
            diff["action"] = "rename_symbol"
            edits.append({"path": rel_path, "absolute": abs_path,
                          "before_hash": _sha256(raw), "before_bytes": raw,
                          "after_bytes": encoded, "diff": diff,
                          "occurrences": count})
    return edits


def _reference_is_safe(kind, fact, text, tokens, target_path, path,
                       target_class, typed, declarations, target_static=False,
                       subclasses=None, all_target_classes=None,
                       target_enum_name=None, root_owner=None,
                       root_declarations=None):
    prev2, prev, nxt = _token_neighbors(tokens, fact.get("start"))
    prev_value = prev.get("value") if prev else None
    prev2_value = prev2.get("value") if prev2 else None
    next_value = nxt.get("value") if nxt else None

    shadowed = _owner_shadows_name(fact.get("owner"), fact.get("name"), declarations)
    if kind == "variable" and root_owner not in (None, "script"):
        # У локальной переменной объявление и все ссылки принадлежат ОДНОМУ
        # scope — функции, поэтому проверка тени нашла бы само объявление.
        # Область и так ограничена функцией, а дубль имени в ней мы уже
        # отсекли проверкой уникальности объявления.
        shadowed = False
    # Принадлежность скрипту считаем с учётом вложенных классов: их члены
    # переименовываются (Этап 3.3), значит и ссылки внутри них — наши.
    in_script = _owner_in_script(fact.get("owner"), declarations)
    # Переименование члена вложенного класса затрагивает ТОЛЬКО ссылки,
    # принадлежащие этому классу: одноимённый член внешнего скрипта — другая
    # сущность, и трогать его нельзя.
    in_root = _owner_within(fact.get("owner"), root_owner, root_declarations or [])
    if root_owner is not None and kind in ("function", "signal", "variable",
                                           "const", "enum"):
        # Член САМОГО скрипта: ссылка должна быть в scope скрипта, а не внутри
        # вложенного класса — вложенный класс не наследует внешний скрипт.
        # Член вложенного класса или локальная переменная функции: наоборот,
        # только ссылки ВНУТРИ своего scope.
        if root_owner == "script":
            if not _owner_belongs_to_script(fact.get("owner"), declarations):
                return False
        elif not in_root:
            return False
    if kind == "class_name":
        return fact.get("context") == "type" or (next_value == "." and not shadowed)

    same_script = path == target_path
    is_subclass = bool(subclasses and path in subclasses)
    hierarchy = same_script or is_subclass

    if prev_value == ".":
        receiver = prev2_value
        if hierarchy and receiver == "self" and in_script:
            return True
        if all_target_classes and typed.get(receiver) in all_target_classes:
            return True
        if target_class and typed.get(receiver) == target_class:
            return True
        # Обращение через ИМЯ КЛАССА: Unit.MAX_HP. Здесь receiver — не
        # переменная, поэтому typed его не содержит, но имя класса мы знаем
        # точно, и ссылка однозначна.
        if target_class and receiver == target_class and not shadowed:
            return True
        # Обращение к member через имя САМОГО ENUM: State.IDLE. Receiver —
        # не класс и не переменная, поэтому проверки выше его не видели.
        if kind == "enum_member" and target_enum_name and receiver == target_enum_name:
            return True
        if kind == "function" and target_static and target_class and receiver == target_class:
            return True
        return False

    if kind == "function":
        # Иерархия, а не только сам скрипт: override в подклассе и его
        # self-вызовы — те же носители имени. Локальная тень (параметр,
        # локальная переменная) по-прежнему отсекается проверкой shadowed.
        return (hierarchy and in_script and not shadowed
                and fact.get("context") == "call")
    if kind == "signal":
        # То же для сигнала: emit/await в подклассе относятся к сигналу
        # базового класса, если подкласс не перекрыл его своим объявлением
        # (такое перекрытие отсекается проверкой выше).
        return (hierarchy and in_script and not shadowed
                and (next_value == "." or prev_value == "await"))
    if kind == "variable":
        return (hierarchy and in_script and not shadowed
                and fact.get("context") != "member")
    if kind in ("const", "enum", "enum_member"):
        # Константа адресуется либо через класс (Unit.MAX_HP), либо прямо
        # внутри своего скрипта. Через точку мы уже дошли сюда только если
        # ресивер — наш класс; локальная тень отсекается проверкой shadowed.
        return (hierarchy and in_script and not shadowed
                and fact.get("context") != "member")
    return False


def _collision(declarations, declaration, kind, new_name, subclasses=None):
    """Ищем объявление, которое РЕАЛЬНО конфликтует с новым именем.

    Для class_name важно различать два разных случая, которые раньше
    отваливались в один:
      * затенение — новым именем занят сам скрипт объявления или его подкласс;
        такое переименование сломало бы пространство имён, и это отказ;
      * простое совпадение — такое же имя живёт в ПОСТОРОННЕМ файле
        (чужой локальный var/const). Это не конфликт: имя локально, и наш
        переименованный символ оно не задевает. Такие случаи возвращаются
        отдельно, как предупреждения, а не как отказ.
    """
    affected_paths = {declaration.get("path")}
    if subclasses:
        affected_paths.update(subclasses)
    clashed = None
    for item in declarations:
        if item.get("name") != new_name:
            continue
        if kind == "class_name":
            # Глобальное имя класса: конфликт — только второй class_name
            # проекта либо затенение членами самого скрипта.
            if item.get("kind") == "class_name":
                return item
            if item.get("path") in affected_paths:
                return item
            clashed = clashed or item
            continue
        if kind in ("variable", "const", "enum"):
            if item.get("path") in affected_paths and item.get("owner") == declaration.get("owner"):
                return item
        elif (item.get("path") == declaration.get("path")
              and item.get("owner") == declaration.get("owner")):
            return item
    return clashed


def _is_real_conflict(collided, declaration, kind, subclasses=None):
    """Отличаем затенение нашего символа от простого совпадения имени.

    Затенение — это когда новое имя займёт пространство, в котором уже
    что-то объявлено: наш скрипт, его подклассы (там перекрывается и
    глобальное имя класса) либо тот же файл для членов. Всё остальное —
    простое совпадение в постороннем файле.
    """
    if collided.get("kind") == "class_name":
        return True
    if kind in ("variable", "const", "class_name"):
        affected = {declaration.get("path")} | set(subclasses or ())
        return collided.get("path") in affected
    return collided.get("path") == declaration.get("path")


def _project_global_names(project_root):
    """Имена, занятые на уровне проекта: autoload и действия ввода.

    Autoload — это глобальный синглтон, доступный из любого скрипта по имени,
    а действие ввода — ключ секции [input]. Переименование class_name/члена в
    такое имя перекрывает глобальное значение, и проект падает в движке.
    """
    autoloads, actions = set(), set()
    try:
        absolute = _resolve_safe_path(project_root, "res://project.godot")
        with open(absolute, "rb") as handle:
            text = handle.read().decode("utf-8-sig", errors="replace")
    except Exception:
        return autoloads, actions
    section = ""
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        if "=" not in stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        key, _sep, _value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        if section == "autoload":
            autoloads.add(key)
        elif section == "input":
            actions.add(key)
    return autoloads, actions


def _engine_class_name(project_root, name, addon_dir=None):
    """True, если имя занято классом движка в кэше ClassDB этого проекта."""
    try:
        return gd_api_cache.get_class(project_root, name, addon_dir=addon_dir) is not None
    except Exception:
        return False


def _unwritable_subclass_overrides(project_root, target_path, target_class, snapshot,
                                  kind, old_name, allow_addons=False,
                                  allow_self_edit=False, addon_dir=None):
    """Ищет override старого имени в .gd, которые мы НЕ имеем права переписать.

    Семантический индекс по умолчанию не заходит в addons (см. SKIP_DIRS), а
    политика доступа может запрещать запись в отдельные файлы. Такой подкласс
    для нас невидим: базовый метод переименуется, а override останется со
    старым именем — Godot получит вызов несуществующего метода. Молчать об
    этом нельзя, поэтому такой случай честно блокирует переименование.
    """
    known = {"res://" + entry.get("path") for entry in snapshot.get("files", [])}
    found = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in (".git", ".godot", ".import",
                                               "__pycache__", ".agent_history")]
        for name in files:
            if not name.endswith(".gd"):
                continue
            absolute = os.path.join(root, name)
            rel = "res://" + os.path.relpath(absolute, project_root).replace("\\", "/")
            if rel in known:
                continue
            if can_write_project_path(
                    rel, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            try:
                with open(absolute, "rb") as handle:
                    text = handle.read().decode("utf-8-sig")
            except Exception:
                continue
            if len(text) > _MAX_SOURCE_CHARS:
                continue
            parent_path, parent_class = _get_script_parent(text, rel)
            if parent_path != target_path and (not target_class
                                               or parent_class != target_class):
                continue
            semantic = gd_semantic_parser.parse(text, rel)
            for item in semantic.get("declarations", []):
                if (item.get("kind") == kind and item.get("name") == old_name
                        and item.get("owner") == "script"):
                    found.append((rel, item.get("line")))
    return found


_DYNAMIC_STRING_CALLS = {
    # Ключ — имя метода Godot, который работает со строковым именем члена.
    # Строка рядом с таким вызовом означает реальную ссылку, которую мы не
    # можем доказать статически, — молчать о ней нельзя.
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


def _classify_string_reference(text, tokens, start, end):
    """Определяет, является ли строковый литерал ссылкой на символ.

    Возвращает описание dynamic-ссылки или None, если это обычный текст
    (лог, сообщение об ошибке, подпись). Ключевой факт: БЛИЖАЙШИЙ ИДЕНТИФИКАТОР
    СЛЕВА от строки. У print("Player") слева print, у ClassDB.instantiate(
    "Player") — instantiate, и только второе означает обращение к API по имени.
    """
    pos = None
    for index, token in enumerate(tokens):
        if token.get("start") == start and token.get("kind") == "string":
            pos = index
            break
    if pos is None:
        return None
    # Между именем вызова и строкой стоит открывающая скобка: set("X", 5),
    # поэтому смотрим на токен через одну позицию назад.
    previous = tokens[pos - 1] if pos else None
    if previous is not None and previous["value"] == "(":
        previous = tokens[pos - 2] if pos >= 2 else None
    if previous is None:
        return None
    if previous["value"] == ".":
        owner = tokens[pos - 2] if pos >= 2 else None
        if owner is None or owner["value"] not in ("ClassDB", "Node", "Object"):
            return None
        method = _DYNAMIC_STRING_CALLS.get(previous["value"])
        return method or "%s() по имени" % previous["value"]
    method = _DYNAMIC_STRING_CALLS.get(previous["value"])
    if method:
        return method
    return None


def _assert_hierarchy_renamed(kind, old_name, new_name, hierarchy_paths,
                             covered, declarations, owner=None):
    """Страховка от молчаливой потери полиморфизма.

    Если в иерархии осталось объявление старого имени, наши правки его не
    покрывают (значит, мы его потеряли или не заметили) — операция обязана
    быть отклонена, а не рапортовать успех с битым проектом.
    covered — множество троек (путь, start, end) уже запланированных правок.
    owner — владелец переименовываемого объявления: у members разных enum
    одного скрипта имена совпадают, но это разные сущности, и нетронутый
    одноимённый member чужого enum — не потеря полиморфизма.
    """
    for item in declarations:
        if item.get("kind") != kind or item.get("name") != old_name:
            continue
        if item.get("path") not in hierarchy_paths:
            continue
        # Локальная переменная (owner — функция, не скрипт) и members enum:
        # одноимённые сущности в других scope — другая история.
        if owner is not None and owner != "script" and item.get("owner") != owner:
            if kind in ("variable", "enum_member"):
                continue
        # Член вложенного класса (owner передан и это не "script"):
        # одноимённый член внешнего скрипта — другая сущность, и его
        # нетронутость не означает потерю полиморфизма.
        if (kind in ("function", "signal") and owner is not None
                and owner != "script" and item.get("owner") == "script"):
            continue
        key = (item.get("path"), item.get("start"), item.get("end"))
        if key not in covered:
            raise RenameError(
                "После переименования в иерархии осталось объявление %s: %s:%s; "
                "переименование остановлено"
                % (old_name, item.get("path"), item.get("line")))


def _add_allowed_addon_semantics(snapshot, project_root, allow_addons,
                                 allow_self_edit, addon_dir):
    """Extend the base index with only add-on files writable by this policy."""
    known = {entry.get("path") for entry in snapshot.get("files", [])}
    addons_root = os.path.join(os.path.realpath(project_root), "addons")
    if not os.path.isdir(addons_root):
        return snapshot
    for current, dirs, files in os.walk(addons_root):
        rel_dir = os.path.relpath(current, project_root).replace(os.sep, "/")
        kept_dirs = []
        for name in dirs:
            if name in (".git", ".godot", ".import", "__pycache__", ".agent_history"):
                continue
            candidate = "res://" + name if rel_dir == "addons" else "res://" + rel_dir + "/" + name
            if can_write_project_path(
                    candidate.rstrip("/"), project_root,
                    allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in files:
            if not name.endswith(".gd"):
                continue
            rel = os.path.relpath(os.path.join(current, name), project_root).replace(os.sep, "/")
            if rel in known or not can_write_project_path(
                    "res://" + rel, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                continue
            entry = ml_project_index._build_semantic_entry(
                os.path.realpath(project_root), rel)
            if entry is not None:
                snapshot["files"].append(entry)
                known.add(rel)
    return snapshot


def prepare_rename(project_root, action, allow_addons=False, addon_dir=None,
                   allow_self_edit=False):
    """Build a private all-file transaction without writing project files."""
    kind, old_name, new_name, target_path, line, column, mode, rename_file = _validate_action(action)
    if not can_write_project_path(
            target_path, project_root, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir):
        raise RenameError("Путь защищён текущей политикой доступа")
    _resolve_safe_path(project_root, target_path)

    snapshot = _add_allowed_addon_semantics(
        ml_project_index.semantic_snapshot(project_root, refresh=True),
        project_root, allow_addons, allow_self_edit, addon_dir)
    if not snapshot.get("complete"):
        raise RenameError("Семантический индекс неполон; безопасное переименование невозможно")
    partial = ["res://" + entry["path"] for entry in snapshot["files"]
               if entry["semantic"].get("parse_status") != "ok"]
    if partial:
        raise RenameError("Не удалось полностью разобрать GDScript: %s" % ", ".join(partial[:4]))

    declarations = []
    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        for item in entry["semantic"].get("declarations", []):
            declarations.append(dict(item, path=path, sha256=entry.get("sha256")))
    candidates = [item for item in declarations
                  if item.get("path") == target_path and item.get("line") == line
                  and item.get("kind") == _decl_kind(kind)
                  and item.get("name") == old_name
                  and (column is None or item.get("column") == column)]
    if len(candidates) != 1:
        # Сообщение должно быть пригодно для модели: что просили, что нашли
        # и что можно попробовать. Раньше тут было «найдено объявлений: 0»,
        # из чего нельзя было понять, в чём дело.
        available = sorted({item.get("name") for item in declarations
                            if item.get("path") == target_path
                            and item.get("kind") in _DECL_KINDS
                            and item.get("name")})
        raise RenameError(
            "В %s:%d нет объявления вида %s с именем %s. Объявления этого "
            "скрипта: %s. Возьми точную строку объявления из gather_context "
            "или read_function."
            % (target_path, line, kind, old_name,
               ", ".join(available[:12]) or "нет"))
    declaration = candidates[0]
    if kind in ("function", "signal") and declaration.get("owner") != "script":
        # Член вложенного класса допустим, но только если сам класс вложен
        # на верхнем уровне скрипта. Класс, объявленный внутри функции, —
        # локальная сущность времени выполнения, её имя нельзя переименовать
        # безопасным текстовым способом.
        if not _owner_is_top_level(declaration.get("owner"), declarations):
            raise RenameError(
                "Члены вложенных классов переименовываются только для классов "
                "верхнего уровня скрипта")
    if kind == "variable" and declaration.get("owner") != "script":
        # Локальная переменная живёт ровно в своей функции: её объявление и
        # все обращения принадлежат одному scope. Переименование затрагивает
        # только этот scope — одноимённые локальные переменные в других
        # функциях и одноимённые члены скрипта остаются нетронутыми.
        if not _owner_belongs_to_script(declaration.get("owner"), declarations):
            raise RenameError(
                "Локальные переменные переименовываются только внутри функций "
                "верхнего уровня скрипта")
    if kind in ("const", "enum") and declaration.get("owner") != "script":
        # Константа и enum живут на верхнем уровне скрипта. Объявление внутри
        # функции или вложенного класса — это уже другая сущность, и
        # переименование «наружу» сломало бы её использование.
        raise RenameError("Константы и enum переименовываются только на верхнем уровне скрипта")
    if kind == "enum_member" and not _owner_is_top_level(
            declaration.get("owner"), declarations):
        # Member анонимного enum принадлежит скрипту, а member именованного —
        # самому enum. В обоих случаях enum должен быть верхнего уровня.
        raise RenameError("Members enum переименовываются только в enum верхнего уровня")
    # Имя enum, которому принадлежит member: через него идёт обращение
    # State.IDLE, и без него такая ссылка выглядела бы неоднозначной.
    target_enum_name = None
    if kind == "enum_member" and declaration.get("owner") != "script":
        target_enum_name = next(
            (item.get("name") for item in declarations
             if item.get("id") == declaration.get("owner")), None)

    target_entry = next(entry for entry in snapshot["files"]
                        if "res://" + entry["path"] == target_path)
    target_class = _class_name_for_file(target_entry["semantic"])
    subclasses = set()
    all_target_classes = {target_class} if target_class else set()

    # Иерархия нужна для ЛЮБОГО вида членов, а не только для переменных.
    # Раньше subclasses строились только при kind == "variable": вызовы в
    # подклассах обновлялись, а сами объявления-override оставались со старым
    # именем — проект получал вызов несуществующего метода при рапорте «успешно».
    # Для class_name иерархия нужна по другой причине: объявление с тем же
    # именем в наследнике перекрывает ГЛОБАЛЬНОЕ имя класса, и это затенение
    # ломает код наследника — такой случай обязан быть отказом, а не «просто
    # совпадением имени в чужом файле».
    subclasses = _find_subclasses(project_root, target_path, target_class, snapshot)
    if kind in ("function", "signal", "variable", "class_name", "const", "enum"):
        for sc in subclasses:
            sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
            if sc_entry:
                sc_cls = _class_name_for_file(sc_entry["semantic"])
                if sc_cls:
                    all_target_classes.add(sc_cls)

    # Собственное одноимённое объявление ДРУГОГО вида в подклассе перекрывает
    # метод/сигнал базового класса: self.take_damage в таком подклассе — уже не
    # метод. Молча переименовывать ссылку здесь нельзя — это разные сущности.
    for sc in sorted(subclasses):
        sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
        if not sc_entry:
            continue
        for item in sc_entry["semantic"].get("declarations", []):
            if (item.get("owner") == "script" and item.get("name") == old_name
                    and item.get("kind") != kind):
                raise RenameError(
                    "В подклассе %s есть собственное объявление %s (%s), перекрывающее "
                    "переименовываемое; переименование остановлено"
                    % (sc, old_name, item.get("kind")))

    # Коллизии уровня проекта и движка. _collision смотрит только объявления
    # в .gd, поэтому Hero -> Sprite2D (класс движка) и Hero -> GameState
    # (autoload) проходили, а проект падал в редакторе.
    if _engine_class_name(project_root, new_name, addon_dir=addon_dir):
        raise RenameError("Новое имя %s занято классом движка Godot" % new_name)
    autoloads, input_actions = _project_global_names(project_root)
    if new_name in autoloads:
        raise RenameError("Новое имя %s совпадает с autoload этого проекта"
                          % new_name)
    if new_name in input_actions:
        raise RenameError("Новое имя %s совпадает с действием ввода InputMap"
                          % new_name)

    collided = _collision(declarations, declaration, kind, new_name, subclasses=subclasses)
    warnings = []
    if collided and _is_real_conflict(collided, declaration, kind, subclasses):
        raise RenameError("Новое имя уже объявлено в том же пространстве: %s:%s"
                          % (collided.get("path"), collided.get("line")))
    if collided:
        # Простое совпадение имени в постороннем файле: локальная переменная
        # или константа чужого скрипта наш символ не задевает. Молчать было бы
        # плохо, отказывать — тем более, поэтому это видимое предупреждение.
        warnings.append(
            "В %s:%s уже есть объявление %s (%s) — имена совпадают, но это "
            "локальное имя чужого скрипта, переименование его не ломает"
            % (collided.get("path"), collided.get("line"), new_name,
               collided.get("kind")))
    if kind == "class_name":
        duplicates = [item for item in declarations
                      if item.get("kind") == kind and item.get("name") == old_name]
        if len(duplicates) != 1:
            raise RenameError("class_name неоднозначен: найдено объявлений %d" % len(duplicates))
    else:
        # Проверяем вид объявления в терминах парсера: публичный "const"
        # разбирается как "constant" (иначе поиск не нашёл бы ничего).
        duplicates = [item for item in declarations
                      if item.get("path") == target_path
                      and item.get("kind") == _decl_kind(kind)
                      and item.get("name") == old_name
                      # Members разных enum одного скрипта — разные
                      # пространства имён: IDLE в State и IDLE в Mode
                      # не должны считаться одним и тем же объявлением.
                      and (kind != "enum_member"
                           or item.get("owner") == declaration.get("owner"))
                      # Член вложенного класса ищется ТОЛЬКО внутри него:
                      # одноимённый метод внешнего скрипта — другая
                      # сущность, и её переименование было бы поломкой.
                      and (declaration.get("owner") == "script"
                           or item.get("owner") == declaration.get("owner"))]
        if len(duplicates) != 1:
            raise RenameError("Имя неоднозначно внутри скрипта: найдено объявлений %d" % len(duplicates))

    edits_by_path = {target_path: [(declaration["start"], declaration["end"])]}
    # Объявления-override в подклассах — такие же носители имени, как и сам
    # скрипт: пока они не переименованы, полиморфизм теряется (вызов уходит
    # в несуществующий метод базового класса), поэтому берём их всеми видами,
    # а не только для переменных.
    for sc in sorted(subclasses):
        sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
        if not sc_entry:
            continue
        for item in sc_entry["semantic"].get("declarations", []):
            if (item.get("kind") == _decl_kind(kind) and item.get("name") == old_name
                    and item.get("owner") == "script"):
                edits_by_path.setdefault(sc, []).append((item["start"], item["end"]))

    ambiguities = []
    dynamic_references = []
    unverified_references = []

    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        if not can_write_project_path(
                path, project_root, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir):
            continue
        _absolute, raw, text, _bom = _read_source(project_root, path)
        if entry.get("sha256") != _sha256(raw):
            raise StaleRenameError("Семантический индекс устарел для %s" % path)
        tokens = gd_semantic_parser.tokenize(text)
        typed = _typed_receivers(text)
        for fact in entry["semantic"].get("references", []):
            if fact.get("name") != old_name:
                continue
            if _reference_is_safe(kind, fact, text, tokens, target_path, path,
                                  target_class, typed,
                                  entry["semantic"].get("declarations", []),
                                  bool(declaration.get("static")),
                                  subclasses=subclasses,
                                  all_target_classes=all_target_classes,
                                  target_enum_name=target_enum_name,
                                  root_owner=declaration.get("owner"),
                                  root_declarations=declarations):
                edits_by_path.setdefault(path, []).append((fact["start"], fact["end"]))
            elif (declaration.get("owner") != "script" and kind in ("function", "signal")
                  and not _owner_within(fact.get("owner"), declaration.get("owner"),
                                         declarations)):
                # Ссылка доказанно принадлежит НЕ нашему вложенному классу
                # (например, одноимённый метод внешнего скрипта). Это не
                # неоднозначность, а другая сущность — молча пропускаем.
                continue
            elif _reference_in_other_scope(fact, declaration, kind, declarations):
                # Ссылка живёт в scope, который НЕ является scope нашего
                # объявления: вложенный класс не наследует внешний скрипт,
                # поэтому одноимённый член снаружи — другая сущность.
                continue
            elif kind in ("variable", "const", "enum", "enum_member") and fact.get("context") != "member" and _owner_shadows_name(
                    fact.get("owner"), fact.get("name"), entry["semantic"].get("declarations", [])):
                # Локальная тень: локальная переменная/константа с тем же
                # именем перекрывает нашу ссылку. Это НЕ неоднозначность,
                # а доказанно другая сущность — молча её пропускаем.
                continue
            else:
                ambiguities.append("%s:%s:%s" % (path, fact.get("line"), fact.get("column")))
        for fact in entry["semantic"].get("strings", []):
            if _exact_string_value(str(fact.get("value") or "")) != old_name:
                continue
            # Строка с именем символа — не всегда ссылка. print("Player") —
            # это текст, а ClassDB.instantiate("Player") — обращение к API по
            # имени, которое мы не можем доказать статически. Раньше оба случая
            # давали одинаковый отказ, хотя свойства в .tscn переписываются
            # без вопросов. Теперь обычный текст не мешает, а настоящая
            # dynamic-ссылка попадает в отчёт для ручной проверки.
            reason = _classify_string_reference(
                text, tokens, fact.get("start"), fact.get("end"))
            if reason:
                dynamic_references.append(
                    "%s:%s — %s(\"%s\"); проверьте вручную"
                    % (path, fact.get("line"), reason, old_name))
    if ambiguities and mode == "strict":
        raise RenameError("Есть неоднозначные ссылки; переименование остановлено: %s"
                          % ", ".join(ambiguities[:8]))
    if ambiguities:
        # probable: пользователь осознанно принял риск. Ссылки не трогаем —
        # мы их не доказали, — но каждую показываем до записи, иначе риск
        # останется незамеченным и «успешное» переименование уедет молча.
        unverified_references = [
            "%s — ссылка не доказана, переименование её не выполнено" % item
            for item in ambiguities]
    # Ссылочная правка могла пройти, а объявление-override — нет; проверяем
    # итог по всему плану, а не по одному пути.
    _assert_hierarchy_renamed(
        kind, old_name, new_name, {target_path} | subclasses,
        {(path, start, end) for path, spans in edits_by_path.items()
         for start, end in spans}, declarations,
        owner=declaration.get("owner"))
    # Подклассы вне зоны нашей записи (addons и прочие защищённые .gd) в
    # семантический индекс не попадают — их override мы не обновим, а базу
    # переименуем. Это ровно тот случай, где «успех» ломает проект.
    blocked = _unwritable_subclass_overrides(
        project_root, target_path, target_class, snapshot, kind, old_name,
        allow_addons=allow_addons, allow_self_edit=allow_self_edit,
        addon_dir=addon_dir)
    if blocked:
        raise RenameError(
            "Вне зоны записи есть подкласс с переопределением %s: %s:%s; "
            "переименование остановлено"
            % (old_name, blocked[0][0], blocked[0][1]))

    files = []
    for path in sorted(edits_by_path):
        absolute, raw, before, bom = _read_source(project_root, path)
        ranges = sorted(set(edits_by_path[path]), reverse=True)
        after = before
        for start, end in ranges:
            if after[start:end] != old_name:
                raise StaleRenameError("Диапазон символа устарел для %s" % path)
            after = after[:start] + new_name + after[end:]
        problems = gd_lint.lint_gdscript(after)
        if problems:
            raise RenameError("После переименования %s не проходит gd_lint: %s"
                              % (path, problems[0]))
        before_api = set(gd_api_check.check_api_usage(project_root, before, path, addon_dir))
        after_api = set(gd_api_check.check_api_usage(project_root, after, path, addon_dir))
        introduced = sorted(after_api - before_api)
        if introduced:
            raise RenameError("После переименования %s появилась ошибка API: %s"
                              % (path, introduced[0]))
        encoded = ((b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8"))
        diff = build_diff_preview(before, after)
        diff["path"] = path
        diff["action"] = "rename_symbol"
        files.append({"path": path, "absolute": absolute,
                      "before_hash": _sha256(raw), "before_bytes": raw,
                      "after_bytes": encoded, "diff": diff,
                      "occurrences": len(ranges)})
    if kind == "variable" and declaration.get("owner") == "script":
        # Только ЧЛЕНЫ скрипта бывают свойствами сцены. Локальная переменная
        # функции в .tscn не записывается, и её имя там может совпадать с
        # совершенно чужым свойством другого скрипта.
        scene_edits = _collect_scene_property_edits(
            project_root, {target_path} | subclasses, old_name, new_name,
            allow_addons=allow_addons, allow_self_edit=allow_self_edit,
            addon_dir=addon_dir)
        files.extend(scene_edits)
    # Связи сцен — такой же носитель имени, как и код: без их обновления
    # Godot теряет подключение молча, а операция рапортует «успешно».
    # Члены вложенных классов сюда не попадают: Inner недоступен узлам сцены,
    # поэтому method такой связи к нашему символу отношения не имеет.
    if not _owner_is_script_scope(declaration, declarations):
        connection_edits = []
    else:
        connection_edits = _collect_scene_connection_edits(
            project_root, {target_path} | subclasses, kind, old_name, new_name,
            allow_addons=allow_addons, allow_self_edit=allow_self_edit,
            addon_dir=addon_dir)
    files.extend(connection_edits)
    # Содержимое, имя файла и .uid едут ОДНОЙ транзакцией: пока класс
    # переименован, а файл нет, проект находится в промежуточном состоянии.
    file_rename = None
    if rename_file:
        file_rename = _plan_file_rename(
            project_root, target_path, new_name, addon_dir)
        if file_rename:
            # Diff строим вручную: build_diff_preview возвращает None на
            # одинаковых текстах, а здесь изменение — это сам перенос пути.
            diff = {"path": file_rename["from"], "action": "rename_symbol",
                    "dest": file_rename["to"],
                    "lines": [{"type": "info",
                               "text": "Файл переименован в %s (вместе с .uid)"
                                       % file_rename["to"]}]}
    return {
        "kind": kind, "old_name": old_name, "new_name": new_name,
        "declaration": action.get("declaration"), "files": files,
        "file_rename": file_rename,
        "file_rename_diff": diff if file_rename else None,
        # Динамические ссылки не блокируют переименование, но обязаны быть
        # видны пользователю ДО записи — иначе риск остаётся незамеченным.
        "dynamic_references": dynamic_references,
        "warnings": warnings,
        "unverified_references": unverified_references,
        "mode": mode,
        "reference_count": sum(item["occurrences"] for item in files) - 1,
    }


def public_prepared(prepared):
    return {
        "kind": prepared["kind"], "old_name": prepared["old_name"],
        "new_name": prepared["new_name"], "declaration": prepared["declaration"],
        "paths": [item["path"] for item in prepared["files"]],
        "file_count": len(prepared["files"]),
        "reference_count": prepared["reference_count"],
        "dynamic_references": list(prepared.get("dynamic_references") or []),
        "warnings": list(prepared.get("warnings") or []),
        "unverified_references": list(prepared.get("unverified_references") or []),
        "mode": prepared.get("mode", "strict"),
        "file_rename": prepared.get("file_rename"),
    }


def prepared_diffs(prepared):
    diffs = [item["diff"] for item in prepared.get("files", [])]
    # Перенос файла показываем в том же диффе: пользователь должен увидеть
    # итог транзакции, а не только изменённое содержимое.
    if prepared.get("file_rename_diff"):
        diffs.append(prepared["file_rename_diff"])
    return diffs


def apply_prepared_rename(project_root, prepared, chat_id=None, chat_title=None):
    """Apply all files or restore every replaced file on a caught failure."""
    files = prepared.get("files") or []
    if not files:
        raise RenameError("Подготовленная транзакция не содержит файлов")
    with _project_lock(project_root):
        for item in files:
            with open(item["absolute"], "rb") as handle:
                if _sha256(handle.read()) != item["before_hash"]:
                    raise StaleRenameError("Файл изменился после предпросмотра: %s" % item["path"])
        # Новый путь файла тоже попадает в журнал: на момент записи его ещё
        # нет, поэтому откат удалит его, а старый путь восстановит из
        # снапшота. Вместе это даёт возврат и содержимого, и имени файла.
        file_rename = prepared.get("file_rename")
        history_paths = [item["path"] for item in files]
        states = None
        if file_rename:
            # Новый путь и новый .uid в журнале НЕ существуют на момент
            # записи (before_present = False) — откат их удалит. Старые пути
            # восстановятся из снапшотов. Вместе это возвращает и содержимое,
            # и имя файла, и .uid одной кнопкой отката.
            history_paths.append(file_rename["to"])
            states = [{"path": file_rename["to"], "before_bytes": None,
                       "after_bytes": b""}]
            source_uid = _resolve_safe_path(project_root, file_rename["from"]) + ".uid"
            if os.path.isfile(source_uid):
                with open(source_uid, "rb") as handle:
                    uid_bytes = handle.read()
                history_paths.append(file_rename["from"] + ".uid")
                history_paths.append(file_rename["to"] + ".uid")
                states.append({"path": file_rename["from"] + ".uid",
                               "before_bytes": uid_bytes,
                               "after_bytes": uid_bytes})
                states.append({"path": file_rename["to"] + ".uid",
                               "before_bytes": None, "after_bytes": b""})
        entry_id = history_manager.record_batch_change(
            project_root, "rename_symbol", history_paths,
            chat_id=chat_id, chat_title=chat_title, states=states)
        replaced = []
        temps = []
        moved = []
        try:
            for item in files:
                directory = os.path.dirname(item["absolute"])
                descriptor, temp_path = tempfile.mkstemp(prefix=".agent_rename_", dir=directory)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(item["after_bytes"])
                    handle.flush()
                    os.fsync(handle.fileno())
                temps.append(temp_path)
                item["temp_path"] = temp_path
            for item in files:
                _replace_file(item["temp_path"], item["absolute"])
                replaced.append(item)
            if file_rename:
                _move_with_uid(project_root, file_rename, moved)
            history_manager.commit_change(project_root, entry_id)
        except Exception:
            # Откат в обратном порядке: сначала возвращаем перенесённые файлы
            # на старые места, затем — прежнее содержимое.
            for entry in reversed(moved):
                try:
                    _replace_file(entry["dest_absolute"], entry["source_absolute"])
                    if entry.get("dest_uid") and os.path.isfile(entry["dest_uid"]):
                        _replace_file(entry["dest_uid"], entry["source_uid"])
                except OSError:
                    pass
            for item in reversed(replaced):
                with open(item["absolute"], "wb") as handle:
                    handle.write(item["before_bytes"])
            history_manager.abort_change(project_root, entry_id)
            raise
        finally:
            for temp_path in temps:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
        paths = [item["path"] for item in files]
        if file_rename:
            # Старый путь исчез, новый появился: индекс обновляем по обоим.
            paths = [file_rename["to"] if path == file_rename["from"] else path
                     for path in paths]
        ml_project_index.update_entries(project_root, changed_rels=paths)
        return {"entry_id": entry_id, "changed_paths": paths,
                "file_count": len(paths), "reference_count": prepared["reference_count"]}
