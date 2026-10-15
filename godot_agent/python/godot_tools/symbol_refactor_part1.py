# -*- coding: utf-8 -*-

"""symbol_refactor_part1 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor).

Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
"""

import hashlib
import os
import re
import threading
import gd_lint
import gd_semantic_parser
import scene_deps
import file_refactor
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path)

from symbol_refactor_data import _KEYWORDS

KINDS = {"class_name", "function", "signal", "variable", "const", "enum",
         "enum_member"}

# Вид, которым оперирует rename_symbol, -> вид объявления в парсере.
# Имена не совпадают исторически: парсер называет константу "constant",
# а публичный action говорит "const" (так его понимает модель).
_KIND_TO_DECL = {"const": "constant", "enum": "enum"}

# Обратное отображение для проверок вида объявления.
_DECL_TO_KIND = {value: key for key, value in _KIND_TO_DECL.items()}

def _owner_is_top_level(owner, declarations):
    """Owner принадлежит верхнему уровню скрипта.

    Критерий: по цепочке объявлений до самого скрипта не встречается ФУНКЦИЯ.
    Класс внутри функции — локальная сущность времени выполнения, её имя
    переименовать текстом нельзя. А вот класс в классе (Deep внутри Outer) —
    верхнего уровня, цепочка идёт через объявления kind == "class".
    """
    by_id = {item.get("id"): item for item in declarations}
    current = owner
    seen = set()
    while current and current not in seen and current != "script":
        seen.add(current)
        declaration = by_id.get(current)
        if not declaration:
            return False
        if declaration.get("kind") == "function":
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

_LOCKS = {}

_LOCKS_GUARD = threading.Lock()

_MAX_SOURCE_CHARS = 200000

_replace_file = os.replace

class RenameError(ValueError):
    """Отказ переименования с машинным кодом причины (Этап 4.4).

    Код нужен и человеку, и модели: по тексту нельзя однозначно понять,
    что делать дальше — исправить locator, выбрать другое имя или признать,
    что случай не поддерживается. Подклассы ничего не меняют в поведении:
    перехват RenameError работает как раньше.
    """

    code = "unsafe"

    def __init__(self, message, code=None):
        super().__init__(message)
        if code:
            self.code = code

class LocatorError(RenameError):
    """Указан неверный locator: строки/имени объявления нет. Чини locator."""
    code = "locator"

class UnsafeRenameError(RenameError):
    """Переименование опасно: конфликт имён или недоказанная ссылка."""
    code = "unsafe"

class UnsupportedRenameError(RenameError):
    """Случай честно не поддерживается (вид, имя, scope)."""
    code = "unsupported"

class StaleRenameError(RuntimeError):
    pass

def _project_lock(project_root):
    key = os.path.normcase(os.path.realpath(project_root or "."))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())

def _sha256(data):
    return hashlib.sha256(data).hexdigest()

def _collect_path_reference_edits(project_root, file_rename, allow_addons=False,
                                  allow_self_edit=False, addon_dir=None):
    """Правки ссылок на переносимый путь (.tscn/.tres/preload и т.п.).

    Перенос .gd без переписывания ссылок оставляет сцены на несуществующем
    пути, и узел молча теряет скрипт. Пользуемся готовым поиском
    file_refactor.find_file_references — он уже знает про относительные
    preload(), про фильтр расширений и про политику чтения.
    """
    old_path = file_rename["from"]
    new_path = file_rename["to"]
    references = file_refactor.find_file_references(
        project_root, old_path, allow_addons=allow_addons,
        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    exact_pattern = re.compile(
        r'(?<=["\'\*])' + re.escape(old_path) + r'(?=["\'\s,\]])')
    edits = []
    for ref in references:
        if not can_write_project_path(
                ref["path"], project_root, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir):
            # Ссылка есть, а права её переписать нет. Продолжать нельзя:
            # файл уедет, а ссылка останется висеть — ровно тот случай, ради
            # которого это переименование и затевалось.
            raise UnsafeRenameError(
                "На переименовываемый скрипт ссылается %s, но его нельзя "
                "переписать по текущей политике доступа: перенос разорвал бы "
                "эту ссылку. Переименование остановлено."
                % ref["path"])
        before_text = ref["text"]
        after_text = before_text
        for start, end, _cand in sorted(ref.get("rel_matches") or [],
                                        key=lambda item: item[0], reverse=True):
            after_text = after_text[:start] + new_path + after_text[end:]
        after_text = exact_pattern.sub(new_path, after_text)
        if ref["path"].lower().endswith(".gd"):
            lint_errors = gd_lint.lint_gdscript(after_text)
            if lint_errors:
                raise UnsafeRenameError(
                    "После обновления ссылки в %s обнаружена синтаксическая "
                    "ошибка: %s" % (ref["path"], lint_errors[0]))
        diff = build_diff_preview(before_text, after_text)
        diff["path"] = ref["path"]
        diff["action"] = "rename_symbol"
        edits.append({
            "path": ref["path"], "absolute": ref["absolute"],
            "before_hash": _sha256(ref["raw"]), "before_bytes": ref["raw"],
            "after_bytes": (b"\xef\xbb\xbf" if ref["bom"] else b"")
                          + after_text.encode("utf-8"),
            "diff": diff, "occurrences": ref["occurrences"]})
    return edits

def _read_source(project_root, path):
    absolute = _resolve_safe_path(project_root, path)
    if not os.path.isfile(absolute):
        raise LocatorError("Файл объявления не найден: %s" % path)
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
        raise LocatorError("declaration должен иметь вид res://path.gd:line[:column]")
    line = int(match.group(2))
    column = int(match.group(3)) if match.group(3) else None
    if line < 1 or (column is not None and column < 1):
        raise LocatorError("Строка и колонка declaration должны быть положительными")
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
        raise UnsafeRenameError("Файл с новым именем уже существует: %s" % new_path)
    return {"from": target_path, "to": new_path}

def _unverified_reason(kind, fact, text, tokens, target_path, path,
                       target_class, typed, declarations, subclasses,
                       all_target_classes, root_owner):
    """Почему ссылка НЕ доказана. Только для отчёта, решение не принимает.

    Тот же обход условий, что в _reference_is_safe, но вместо True/False мы
    возвращаем причину. Она нужна пользователю не для красоты: по причине
    видно, ЧТО исправить, чтобы в следующий раз ссылка доказалась сама.
    Например «тип ресивера card неизвестен» лечится аннотацией в коде.
    """
    prev2, prev, nxt = _token_neighbors(tokens, fact.get("start"))
    prev_value = prev.get("value") if prev else None
    prev2_value = prev2.get("value") if prev2 else None
    next_value = nxt.get("value") if nxt else None
    shadowed = _owner_shadows_name(fact.get("owner"), fact.get("name"), declarations)
    if kind == "variable" and root_owner not in (None, "script"):
        shadowed = False
    in_script = _owner_in_script(fact.get("owner"), declarations)
    in_root = _owner_within(fact.get("owner"), root_owner, declarations or [])
    if root_owner is not None and kind in ("function", "signal", "variable",
                                           "const", "enum"):
        if root_owner == "script" and not _owner_belongs_to_script(
                fact.get("owner"), declarations):
            return "вложенный класс не наследует внешний скрипт"
        if root_owner != "script" and not in_root:
            return "ссылка вне вложенного класса, чей член переименовывается"
    if kind == "class_name":
        if fact.get("context") != "type" and next_value != ".":
            return ("использование имени класса не как типа и не как префикса "
                    "(%s)" % (fact.get("context"),))
    hierarchy = (path == target_path
                 or bool(subclasses and path in subclasses))
    if prev_value == ".":
        if hierarchy and prev2_value == "self" and in_script:
            return None
        if all_target_classes and typed.get(prev2_value) in all_target_classes:
            return None
        if target_class and typed.get(prev2_value) == target_class:
            return None
        if target_class and prev2_value == target_class and not shadowed:
            return None
        if shadowed:
            return "имя перекрыто одноимённым объявлением"
        return ("не удалось доказать тип ресивера «%s»: добавь аннотацию типа, "
                "и ссылка переименуется сама" % (prev2_value,))
    if kind in ("function", "signal", "variable", "const", "enum",
                "enum_member"):
        if not hierarchy:
            return "файл не входит в иерархию символа"
        if shadowed:
            return "имя перекрыто одноимённым объявлением"
        if kind == "function" and fact.get("context") != "call":
            return ("упоминание функции не как вызова (%s); такой вызов по "
                    "имени мы переписать не можем" % (fact.get("context"),))
        if fact.get("context") == "member":
            return "член по ссылке на неизвестный объект"
    return "причина не установлена"

def _validate_action(action):
    if not isinstance(action, dict):
        raise RenameError("rename_symbol должен быть объектом")
    kind = str(action.get("kind") or "").strip()
    old_name = str(action.get("old_name") or "").strip()
    new_name = str(action.get("new_name") or "").strip()
    if kind not in KINDS:
        raise UnsupportedRenameError(
            "kind должен быть %s" % ", ".join(sorted(KINDS)))
    for label, name in (("old_name", old_name), ("new_name", new_name)):
        if not _IDENTIFIER.match(name) or name in _KEYWORDS:
            raise UnsupportedRenameError(
                "%s не является допустимым идентификатором GDScript" % label)
    if old_name == new_name:
        raise UnsupportedRenameError("Новое имя совпадает со старым")
    path, line, column = _parse_locator(action.get("declaration"))
    # rename_file: переименовать ли сам .gd вместе с class_name. По умолчанию
    # НЕТ: имя файла может не совпадать с классом (hero.gd с class_name Unit),
    # и молчаливый перенос ломал бы preload() и пути в сценах.
    rename_file = bool(action.get("rename_file"))
    if rename_file and kind != "class_name":
        raise UnsupportedRenameError("rename_file применим только к class_name")
    # Режим отказа: strict по умолчанию. Неизвестное значение молчать не
    # должно — иначе опечатка в действии незаметно ослабит проверки.
    mode = str(action.get("mode") or "strict").strip().lower()
    if mode not in MODES:
        raise UnsupportedRenameError("mode должен быть %s" % " или ".join(MODES))
    # allow_unverified: переименовывать ли ссылки, которые мы НЕ смогли доказать.
    # Дефолт — strict: флаг приходит из настройки панели, а любой другой
    # клиент (MCP, сторонний скрипт) флага не шлёт и не должен молча получить
    # небезопасное переименование.
    #
    # Тип проверяем СТРОГО. Значение приходит из JSON, который пишет модель,
    # и в Python bool("false") is True: наивное приведение превратило бы
    # просьбу «строго» в тихое разрешение недоказанных ссылок. Поэтому любой
    # не-bool — явный отказ с упоминанием имени поля.
    allow_unverified = False
    if "allow_unverified" in action and action.get("allow_unverified") is not None:
        if not isinstance(action["allow_unverified"], bool):
            raise UnsupportedRenameError(
                "allow_unverified должен быть true или false, получено: %r"
                % (action["allow_unverified"],))
        allow_unverified = action["allow_unverified"]
    return (kind, old_name, new_name, path, line, column, mode, rename_file,
            allow_unverified)

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

    # Параметры признаём только внутри настоящей сигнатуры func(...):
    # одиночное «имя:» может встретиться в Dictionary-типе или в коде,
    # и принять его за параметр значило бы привязать не туда.
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
