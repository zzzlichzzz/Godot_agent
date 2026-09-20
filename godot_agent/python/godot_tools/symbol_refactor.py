# -*- coding: utf-8 -*-
"""Conservative, hash-guarded GDScript symbol renames."""

import hashlib
import os
import re
import tempfile
import threading

import gd_api_check
import gd_lint
import gd_semantic_parser
import history_manager
from minilich import ml_project_index
from project_tools import _resolve_safe_path, build_diff_preview, is_addon_path


KINDS = {"class_name", "function", "signal", "variable"}
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


def _validate_action(action):
    if not isinstance(action, dict):
        raise RenameError("rename_symbol должен быть объектом")
    kind = str(action.get("kind") or "").strip()
    old_name = str(action.get("old_name") or "").strip()
    new_name = str(action.get("new_name") or "").strip()
    if kind not in KINDS:
        raise RenameError("kind должен быть class_name, function, signal или variable")
    for label, name in (("old_name", old_name), ("new_name", new_name)):
        if not _IDENTIFIER.match(name) or name in _KEYWORDS:
            raise RenameError("%s не является допустимым идентификатором GDScript" % label)
    if old_name == new_name:
        raise RenameError("Новое имя совпадает со старым")
    path, line, column = _parse_locator(action.get("declaration"))
    return kind, old_name, new_name, path, line, column


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


def _collect_scene_property_edits(project_root, affected_scripts, old_name, new_name, allow_addons=False):
    """Find all .tscn and .tres files referencing affected_scripts and update old_name property."""
    scene_edits = []
    if not affected_scripts:
        return scene_edits

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
            if not allow_addons and is_addon_path(rel_path, project_root):
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

            if not matching_ids:
                continue

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


def _reference_is_safe(kind, fact, text, tokens, target_path, path,
                       target_class, typed, declarations, target_static=False,
                       subclasses=None, all_target_classes=None):
    prev2, prev, nxt = _token_neighbors(tokens, fact.get("start"))
    prev_value = prev.get("value") if prev else None
    prev2_value = prev2.get("value") if prev2 else None
    next_value = nxt.get("value") if nxt else None

    shadowed = _owner_shadows_name(fact.get("owner"), fact.get("name"), declarations)
    in_script = _owner_belongs_to_script(fact.get("owner"), declarations)
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
        if kind == "function" and target_static and target_class and receiver == target_class:
            return True
        return False

    if kind == "function":
        return (same_script and in_script and not shadowed
                and fact.get("context") == "call")
    if kind == "signal":
        return (same_script and in_script and not shadowed
                and (next_value == "." or prev_value == "await"))
    if kind == "variable":
        return (hierarchy and in_script and not shadowed
                and fact.get("context") != "member")
    return False


def _collision(declarations, declaration, kind, new_name, subclasses=None):
    affected_paths = {declaration.get("path")}
    if subclasses:
        affected_paths.update(subclasses)
    for item in declarations:
        if item.get("name") != new_name:
            continue
        if kind == "class_name":
            return item
        if kind == "variable":
            if item.get("path") in affected_paths and item.get("owner") == declaration.get("owner"):
                return item
        elif (item.get("path") == declaration.get("path")
              and item.get("owner") == declaration.get("owner")):
            return item
    return None


def prepare_rename(project_root, action, allow_addons=False, addon_dir=None):
    """Build a private all-file transaction without writing project files."""
    kind, old_name, new_name, target_path, line, column = _validate_action(action)
    if not allow_addons and is_addon_path(target_path, project_root):
        raise RenameError("Правки res://addons/ требуют явного запроса пользователя")
    _resolve_safe_path(project_root, target_path)

    snapshot = ml_project_index.semantic_snapshot(project_root, refresh=True)
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
                  and item.get("kind") == kind and item.get("name") == old_name
                  and (column is None or item.get("column") == column)]
    if len(candidates) != 1:
        raise RenameError("По declaration найдено объявлений: %d, ожидалось ровно одно" % len(candidates))
    declaration = candidates[0]
    if kind in ("function", "signal") and declaration.get("owner") != "script":
        raise RenameError("Переименование членов вложенных классов пока не поддерживается безопасно")
    if kind == "variable" and declaration.get("owner") != "script":
        raise RenameError("Переименование локальных переменных внутри функций пока не поддерживается безопасно")

    target_entry = next(entry for entry in snapshot["files"]
                        if "res://" + entry["path"] == target_path)
    target_class = _class_name_for_file(target_entry["semantic"])
    subclasses = set()
    all_target_classes = {target_class} if target_class else set()

    if kind == "variable":
        subclasses = _find_subclasses(project_root, target_path, target_class, snapshot)
        for sc in subclasses:
            sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
            if sc_entry:
                sc_cls = _class_name_for_file(sc_entry["semantic"])
                if sc_cls:
                    all_target_classes.add(sc_cls)

    collided = _collision(declarations, declaration, kind, new_name, subclasses=subclasses)
    if collided:
        raise RenameError("Новое имя уже объявлено в том же пространстве: %s:%s"
                          % (collided.get("path"), collided.get("line")))
    if kind == "class_name":
        duplicates = [item for item in declarations
                      if item.get("kind") == kind and item.get("name") == old_name]
        if len(duplicates) != 1:
            raise RenameError("class_name неоднозначен: найдено объявлений %d" % len(duplicates))
    else:
        duplicates = [item for item in declarations
                      if item.get("path") == target_path and item.get("kind") == kind
                      and item.get("name") == old_name]
        if len(duplicates) != 1:
            raise RenameError("Имя неоднозначно внутри скрипта: найдено объявлений %d" % len(duplicates))

    edits_by_path = {target_path: [(declaration["start"], declaration["end"])]}
    if kind == "variable":
        for sc in subclasses:
            sc_entry = next((e for e in snapshot["files"] if "res://" + e["path"] == sc), None)
            if sc_entry:
                for item in sc_entry["semantic"].get("declarations", []):
                    if item.get("kind") == "variable" and item.get("name") == old_name and item.get("owner") == "script":
                        edits_by_path.setdefault(sc, []).append((item["start"], item["end"]))

    ambiguities = []

    for entry in snapshot["files"]:
        path = "res://" + entry["path"]
        if not allow_addons and is_addon_path(path, project_root):
            facts = [fact for fact in entry["semantic"].get("references", [])
                     if fact.get("name") == old_name]
            if facts:
                ambiguities.append("%s:%s (ссылка внутри addons)" % (path, facts[0].get("line")))
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
                                  all_target_classes=all_target_classes):
                edits_by_path.setdefault(path, []).append((fact["start"], fact["end"]))
            elif kind == "variable" and fact.get("context") != "member" and _owner_shadows_name(
                    fact.get("owner"), fact.get("name"), entry["semantic"].get("declarations", [])):
                continue
            else:
                ambiguities.append("%s:%s:%s" % (path, fact.get("line"), fact.get("column")))
        for fact in entry["semantic"].get("strings", []):
            if _exact_string_value(str(fact.get("value") or "")) == old_name:
                ambiguities.append("%s:%s (строковая/dynamic ссылка)" % (path, fact.get("line")))
    if ambiguities:
        raise RenameError("Есть неоднозначные ссылки; переименование остановлено: %s"
                          % ", ".join(ambiguities[:8]))

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
    if kind == "variable":
        scene_edits = _collect_scene_property_edits(
            project_root, {target_path} | subclasses, old_name, new_name, allow_addons=allow_addons)
        files.extend(scene_edits)
    return {
        "kind": kind, "old_name": old_name, "new_name": new_name,
        "declaration": action.get("declaration"), "files": files,
        "reference_count": sum(item["occurrences"] for item in files) - 1,
    }


def public_prepared(prepared):
    return {
        "kind": prepared["kind"], "old_name": prepared["old_name"],
        "new_name": prepared["new_name"], "declaration": prepared["declaration"],
        "paths": [item["path"] for item in prepared["files"]],
        "file_count": len(prepared["files"]),
        "reference_count": prepared["reference_count"],
    }


def prepared_diffs(prepared):
    return [item["diff"] for item in prepared.get("files", [])]


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
        entry_id = history_manager.record_batch_change(
            project_root, "rename_symbol", [item["path"] for item in files],
            chat_id=chat_id, chat_title=chat_title)
        replaced = []
        temps = []
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
            history_manager.commit_change(project_root, entry_id)
        except Exception:
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
        ml_project_index.update_entries(project_root, changed_rels=paths)
        return {"entry_id": entry_id, "changed_paths": paths,
                "file_count": len(paths), "reference_count": prepared["reference_count"]}
