# -*- coding: utf-8 -*-

"""symbol_refactor_part2 — часть python/godot_tools/symbol_refactor.py (вынесено split_refactor).

Фасад и точка входа — python/godot_tools/symbol_refactor.py: он реэкспортирует имена модуля.
"""

import os
import gd_api_cache
import gd_semantic_parser
from minilich import ml_project_index
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path)

from symbol_refactor_data import _DECL_KINDS, _KEYWORDS

from symbol_refactor_part1 import (LocatorError,
    RenameError,
    _IDENTIFIER,
    _MAX_SOURCE_CHARS,
    _class_name_for_file,
    _decl_kind,
    _exact_string_value,
    _find_subclasses,
    _get_script_parent,
    _owner_belongs_to_script,
    _owner_in_script,
    _owner_shadows_name,
    _owner_within,
    _parse_locator,
    _reference_in_other_scope,
    _token_neighbors,
    _unverified_reason)

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

# API, которые ПО КОНТРАКТУ Godot принимают ИМЯ КЛАССА. Здесь строка не
# «ссылка по имени вообще», а конкретно имя класса: если класс переименован,
# строка обязана меняться, иначе проект падает в рантайме
# (ClassDB.instantiate("Player") после Player -> Avatar вернёт ошибку).
# Это вывод из сигнатуры API, а не допущение, поэтому такие ссылки
# переименовываются наравне с обычными.
_CLASS_NAME_STRING_CALLS = {
    "instantiate": "ClassDB.instantiate",
    "class_exists": "ClassDB.class_exists",
    "is_class": "ClassDB.is_class",
    "is_parent_class": "ClassDB.is_parent_class",
    "can_instantiate": "ClassDB.can_instantiate",
}

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
    kind, method = _classify_string_reference_kind(text, tokens, start, end)
    return method

def _classify_string_reference_kind(text, tokens, start, end):
    """Как _classify_string_reference, но различает КЛАСС и ЧЛЕН.

    Нужно для Этапа 5: `ClassDB.instantiate("Player")` — доказуемая ссылка на
    класс, её можно переименовать вместе с ним. А `obj.call("Player")` — имя
    метода объекта, это другой символ, и трогать его нельзя. Прежний код
    отдавал только описание, и обе роли попадали в один отчёт.
    """
    pos = None
    for index, token in enumerate(tokens):
        if token.get("start") == start and token.get("kind") == "string":
            pos = index
            break
    if pos is None:
        return None, None
    # Между именем вызова и строкой стоит открывающая скобка: set("X", 5).
    # Токены идут так: `instantiate` `(` `"X"`, поэтому от строки назад нужно
    # перешагнуть скобку, а затем взять ИМЯ вызова, а не точку: без этого
    # ветка «владелец точки» не срабатывала никогда и ClassDB.instantiate
    # ошибочно читался как вызов по имени члена.
    previous = tokens[pos - 1] if pos else None
    if previous is not None and previous["value"] == "(":
        previous = tokens[pos - 2] if pos >= 2 else None
    if previous is None:
        return None, None
    call = previous
    if previous["value"] == ".":
        # Редкая форма: точка непосредственно перед именем вызова.
        call = tokens[pos - 2] if pos >= 2 else None
        owner = tokens[pos - 3] if pos >= 3 else None
        if owner is None or call is None:
            return None, None
    else:
        # Обычная форма `Владелец.имя(...)`. Токены: `Владелец` `.` `имя` `(`
        # `"X"`. Имя вызова мы уже забрали как previous (это pos-2), поэтому
        # точка стоит на pos-3, а владелец — на pos-4. Читать владельца с pos-2
        # бессмысленно: там уже имя вызова, и ClassDB не распознавался НИКОГДА.
        if pos >= 4 and tokens[pos - 3]["value"] == ".":
            owner = tokens[pos - 4]
        else:
            # Без владельца: set("X", 1) — вызов сам по себе.
            owner = None
    if owner is not None and owner["value"] == "ClassDB":
        known = _CLASS_NAME_STRING_CALLS.get(call["value"])
        if known:
            return "class", known
    # Владельца НЕ ограничиваем списком ClassDB/Node/Object: `n.set("X", 5)`
    # и `n.connect("X")` — самый частый случай в живом коде, и ресивер там
    # произвольный. Ограничение отбрасывало их, и переименование снова стало
    # бы отказывать на каждом set() по имени.
    #
    # Запасного варианта «"%s() по имени" для ЛЮБОГО вызова» здесь нет
    # намеренно: из-за него print("Player") — обычный текст для человека —
    # попадал в отчёт как ссылка на наш символ.
    method = _DYNAMIC_STRING_CALLS.get(call["value"])
    return ("member", method) if method else (None, None)

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

_USAGE_KINDS = {"class_name", "function", "signal", "variable", "const",
                "enum", "enum_member"}

def _exclude_place_kind(entry):
    """Разбор адреса снятого места — ЕДИНСТВЕННАЯ точка разбора строки.

    Исход разбора:
      ("place", res://путь.gd, строка) — точечное место, строка обязательна;
      ("path", res://путь.gd, None)    — запись БЕЗ распознанной строки;
      ("invalid", None, None)          — запись не адрес: игнорируется.

    Разбирается только ХВОСТ адреса (после префикса res://), потому что
    двоеточие в самом префиксе — часть схемы, а не разделитель: раньше из-за
    этого id "res://src/unit.gd:7:9" путал :column с :line.

    path-only отделён от invalid намеренно: раньше такая запись МОЛЧА
    принималась за «весь файл» и снимала ВСЕ места файла. Теперь решение о
    ней принимает `_excluded_places` — один раз и явно, а не побочным
    эффектом разбора. Любой нераспознанный нецифровой хвост после пути
    ("res://src/unit.gd:", "res://src/unit.gd:void") — это тот же случай
    «нет номера строки», а не отдельная (молчаливая) семантика.
    """
    raw = str(entry or "").strip().replace("\\", "/")
    body = raw[6:] if raw.startswith("res://") else ""
    if not body.strip("/"):
        return "invalid", None, None
    head, sep, tail = body.rpartition(":")
    if not sep:
        # После префикса двоеточий нет вовсе — адрес файла без строки.
        return "path", raw, None
    if not tail.isdigit():
        # Хвост после последнего «:» — не число, значит номера строки в записи
        # нет; путь берём из уже отделённой части.
        return "path", "res://" + head, None
    # Если и перед хвостом стоит цифровая группа, хвост — это колонка, а
    # строка — перед ней. Именно здесь раньше терялся номер строки.
    head2, sep2, tail2 = head.rpartition(":")
    if sep2 and tail2.isdigit():
        head, tail = head2, tail2
    if not head.strip("/") or int(tail) < 1:
        return "invalid", None, None
    return "place", "res://" + head, int(tail)

def _exclude_entry(entry):
    """Адрес снятого места -> (res://путь.gd, строка) или None.

    Тонкая обёртка над `_exclude_place_kind` (единая точка разбора): path-only
    и мусор отдают None — точечного места в них нет.
    """
    kind, path, line = _exclude_place_kind(entry)
    if kind != "place":
        return None
    return path, line

def exclude_place(entry):
    """Адрес снятого места -> "res://путь.gd:строка" (колонка отбрасывается).

    Обёртка над единственным разбором адреса (`_exclude_place_kind`). Пустая
    строка и path-only — адрес не разобран: вызывающий отдаёт исходную
    запись дальше без подмены пути (а ядро отвергнет её явно, а не молча).
    """
    key = _exclude_entry(entry)
    if key is None:
        return ""
    return "%s:%d" % key

def _excluded_places(excluded):
    """Снятые пользователем места как множество пар (путь, строка).

    Это ЕДИНСТВЕННАЯ точка правды об исключении: объявление и ссылки
    сравниваются с ней одинаково. Раньше объявление регистрировалось в
    правках вообще без этой проверки, а приёмник принимал запись без строки
    за весь файл (ветка `path in excluded`): снятие ОДНОЙ галочки отменяло
    переименование всех использований файла, а объявление всё равно
    переименовывалось — DECL RENAMED / USAGE STALE и сломанный проект.

    Запись БЕЗ номера строки ("res://src/unit.gd") не поддержана и
    отвергается здесь явно (RenameError): семантика «весь файл» скрытая и
    неоднозначная, а единственный понятный адрес снятого места —
    res://путь.gd:строка. Отказ приходит ДО регистрации правок, поэтому
    файлы проекта остаются нетронутыми.
    """
    places = set()
    for entry in excluded or ():
        kind, path, line = _exclude_place_kind(entry)
        if kind == "place":
            places.add((path, line))
        elif kind == "path":
            raise RenameError(
                "exclude-адрес без номера строки не поддержан: %r. Место "
                "указывается точечно — res://путь.gd:строка (например "
                "%s:1). Запись без строки означала бы «весь файл», а эта "
                "семантика скрытая; снимите галочки с конкретных мест "
                "использования." % (str(entry).strip(), path))
    return places

def _usage_excluded(excluded, path, line):
    """Место снято пользователем? Сравнение точечное: (путь, строка)."""
    if not excluded:
        return False
    try:
        number = int(line)
    except (TypeError, ValueError):
        return False
    return (str(path), number) in excluded

def _usage_query(action):
    """Разбор запроса поиска: нового имени может не быть (нужен только поиск)."""
    if not isinstance(action, dict):
        raise RenameError("find_symbol_usages должен быть объектом")
    kind = str(action.get("kind") or "").strip()
    old_name = str(action.get("old_name") or "").strip()
    if kind not in _USAGE_KINDS:
        raise RenameError("kind должен быть %s" % ", ".join(sorted(_USAGE_KINDS)))
    if not _IDENTIFIER.match(old_name) or old_name in _KEYWORDS:
        raise RenameError("old_name не является допустимым идентификатором GDScript")
    new_name = str(action.get("new_name") or "").strip()
    if new_name and (not _IDENTIFIER.match(new_name) or new_name in _KEYWORDS):
        raise RenameError("new_name не является допустимым идентификатором GDScript")
    path, line, column = _parse_locator(action.get("declaration"))
    return kind, old_name, new_name, path, line, column

def _locate_declaration(declarations, kind, old_name, path, line, column):
    """Единственное объявление по locator'у или внятная ошибка со списком имён."""
    candidates = [item for item in declarations
                  if item.get("path") == path and item.get("line") == line
                  and item.get("kind") == _decl_kind(kind)
                  and item.get("name") == old_name
                  and (column is None or item.get("column") == column)]
    if len(candidates) == 1:
        return candidates[0]
    available = sorted({item.get("name") for item in declarations
                        if item.get("path") == path
                        and item.get("kind") in _DECL_KINDS
                        and item.get("name")})
    raise LocatorError(
        "В %s:%d нет объявления вида %s с именем %s. Объявления этого "
        "скрипта: %s. Возьми точную строку объявления из gather_context "
        "или read_function."
        % (path, line, kind, old_name, ", ".join(available[:12]) or "нет"))

def _load_snapshot(project_root, allow_addons, allow_self_edit, addon_dir):
    snapshot = _add_allowed_addon_semantics(
        ml_project_index.semantic_snapshot(project_root, refresh=True),
        project_root, allow_addons, allow_self_edit, addon_dir)
    declarations = []
    for entry in snapshot.get("files", []):
        path = "res://" + entry["path"]
        for item in entry["semantic"].get("declarations", []):
            declarations.append(dict(item, path=path, sha256=entry.get("sha256")))
    return snapshot, declarations

def find_references(project_root, action, allow_addons=False, addon_dir=None,
                   allow_self_edit=False):
    """Read-only: список мест использования символа. Ничего не пишет.

    Отдельный шаг нужен модели, чтобы не угадывать locator для rename_symbol:
    один проход отдаёт места с координатами, типом связи и уровнем
    уверенности (proven — доказано, probable — вероятно, dynamic — по строке).
    """
    kind, old_name, new_name, target_path, line, column = _usage_query(action)
    _resolve_safe_path(project_root, target_path)
    snapshot, declarations = _load_snapshot(
        project_root, allow_addons, allow_self_edit, addon_dir)
    declaration = _locate_declaration(
        declarations, kind, old_name, target_path, line, column)
    target_entry = next(entry for entry in snapshot["files"]
                        if "res://" + entry["path"] == target_path)
    target_class = _class_name_for_file(target_entry["semantic"])
    subclasses = _find_subclasses(project_root, target_path, target_class, snapshot)
    all_target_classes = {target_class} if target_class else set()
    for sub in subclasses:
        sub_entry = next((e for e in snapshot["files"]
                          if "res://" + e["path"] == sub), None)
        if sub_entry:
            sub_class = _class_name_for_file(sub_entry["semantic"])
            if sub_class:
                all_target_classes.add(sub_class)
    usages = [{"path": declaration["path"], "line": declaration.get("line"),
               "column": declaration.get("column") or 1,
               "link": "declaration", "confidence": "proven"}]
    for entry in snapshot.get("files", []):
        path = "res://" + entry["path"]
        try:
            with open(_resolve_safe_path(project_root, path), "rb") as handle:
                text = handle.read().decode("utf-8-sig")
        except Exception:
            continue
        tokens = gd_semantic_parser.tokenize(text)
        typed = {item.get("name"): item.get("type")
                 for item in entry["semantic"].get("declarations", [])
                 if item.get("type")}
        for fact in entry["semantic"].get("references", []):
            if fact.get("name") != old_name:
                continue
            if _reference_in_other_scope(fact, declaration, kind, declarations):
                continue
            # Локальная тень — доказанно ДРУГАЯ сущность: одноимённая
            # локальная переменная перекрывает нашу ссылку. prepare_rename
            # молча пропускает такие места (ветка 1618), и find_references
            # обязан вести себя так же, иначе в отчёте они выглядят как
            # недоказанные ссылки на наш символ — а это ложь: переименовывать
            # их нельзя, и в балансировке они мешают зря.
            if (kind in ("variable", "const", "enum", "enum_member",
                         "class_name")
                    and fact.get("context") != "member"
                    and _owner_shadows_name(
                        fact.get("owner"), fact.get("name"),
                        entry["semantic"].get("declarations", []))):
                continue
            safe = _reference_is_safe(
                kind, fact, text, tokens, target_path, path, target_class,
                typed, declarations, subclasses=subclasses,
                all_target_classes=all_target_classes,
                root_owner=declaration.get("owner"),
                root_declarations=declarations)
            usages.append({
                "path": path, "line": fact.get("line"),
                "column": fact.get("column") or 1,
                "link": fact.get("context") or "identifier",
                "confidence": "proven" if safe else "probable",
                # Причина обязательна для недоказанного места. Модель видит
                # это первым шагом и решает здесь, можно ли доверять месту:
                # слово «probable» без объяснения заставляет её гадать, а
                # гадание — это ровно та неопределённость, которую этап
                # гранулярности отказа и устраняет.
                "note": None if safe else (
                    _unverified_reason(
                        kind, fact, text, tokens, target_path, path,
                        target_class, typed, declarations, subclasses,
                        all_target_classes, declaration.get("owner"))
                    or "не доказано: связь с символом не установлена")})
        for fact in entry["semantic"].get("strings", []):
            if _exact_string_value(str(fact.get("value") or "")) != old_name:
                continue
            reason = _classify_string_reference(
                text, tokens, fact.get("start"), fact.get("end"))
            if reason:
                usages.append({
                    "path": path, "line": fact.get("line"),
                    "column": fact.get("column") or 1, "link": "string",
                    "confidence": "dynamic", "note": reason})
    usages.sort(key=lambda item: (item["path"], item["line"], item["column"]))
    by_link = {}
    for place in usages:
        by_link[place["link"]] = by_link.get(place["link"], 0) + 1
    return {"action": "find_symbol_usages", "kind": kind,
            "old_name": old_name, "new_name": new_name,
            "declaration": action.get("declaration"),
            "usages": usages, "by_link": by_link,
            "proven_count": sum(1 for i in usages if i["confidence"] == "proven"),
            "probable_count": sum(1 for i in usages if i["confidence"] == "probable"),
            "dynamic_count": sum(1 for i in usages if i["confidence"] == "dynamic")}

def analyze_rename(project_root, action, allow_addons=False, addon_dir=None,
                   allow_self_edit=False):
    """Read-only предпросмотр переименования: что и где изменится.

    Анализ отделён от записи, поэтому пользователь может сначала посмотреть
    места и риски (Этап 4.2), снять галочки с мест (exclude) и только потом
    применить. Ничего не пишет.
    """
    result = find_references(project_root, action, allow_addons=allow_addons,
                             addon_dir=addon_dir, allow_self_edit=allow_self_edit)
    target_path, line, _column = _parse_locator(action.get("declaration"))
    affected_paths = sorted({place["path"] for place in result["usages"]
                             if place["confidence"] == "proven"})
    risks = []
    for place in result["usages"]:
        if place["confidence"] == "proven":
            continue
        risks.append("%s:%s [%s, %s]%s"
                     % (place["path"], place["line"], place["link"],
                        place["confidence"],
                        (" — %s" % place["note"]) if place.get("note") else ""))
    return {"action": "analyze_rename", "kind": result["kind"],
            "old_name": result["old_name"], "new_name": result["new_name"],
            "declaration": action.get("declaration"),
            # Флаг проходит в отчёт: чеклист мест должен знать, переименуются
            # ли недоказанные ссылки, иначе он обещает несуществующее.
            "allow_unverified": action.get("allow_unverified") is True,
            "mode": str(action.get("mode") or "strict"),
            "usages": result["usages"], "affected_paths": affected_paths,
            "risks": risks, "by_link": result["by_link"],
            "proven_count": result["proven_count"],
            "probable_count": result["probable_count"],
            "dynamic_count": result["dynamic_count"],
            "declaration_path": target_path, "declaration_line": line}
