# -*- coding: utf-8 -*-
"""Refactor file paths with automatic reference updates across GDScript, scenes, and project settings."""

import hashlib
import os
import re
import shutil
import tempfile
import threading

import gd_lint
import history_manager
import librarian
import project_tools
from minilich import ml_project_index
from project_tools import _resolve_safe_path, build_diff_preview, is_addon_path


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_SKIP_DIRS = {".git", ".godot", ".import", "__pycache__", ".agent_history", "addons"}
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB safety limit for text scan
_replace_file = os.replace


class FileRefactorError(ValueError):
    pass


class StaleFileRefactorError(RuntimeError):
    pass


def _project_lock(project_root):
    key = os.path.normcase(os.path.realpath(project_root or "."))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _sha256(data):
    return hashlib.sha256(data).hexdigest() if data is not None else ""


def _normalize_godot_path(path):
    p = str(path or "").strip().replace("\\", "/")
    if not p.startswith("res://"):
        raise FileRefactorError("Путь должен начинаться с res://: %s" % path)
    rel = p[6:].strip("/")
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")):
        raise FileRefactorError("Некорректный путь: %s" % path)
    return "res://" + rel


def _read_file_text(abs_path):
    with open(abs_path, "rb") as handle:
        raw = handle.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return raw, text, bom


def find_file_references(project_root, old_godot_path, allow_addons=False, skip_source_check=False):
    """Find all files in project referencing old_godot_path.
    Returns list of dicts: {"path", "absolute", "occurrences", "rel_replaced"}.
    """
    old_godot_path = _normalize_godot_path(old_godot_path)
    abs_old = _resolve_safe_path(project_root, old_godot_path)
    if not skip_source_check and not os.path.isfile(abs_old):
        raise FileNotFoundError("Исходный файл не найден: %s" % old_godot_path)

    old_rel = old_godot_path[6:]
    old_dir = os.path.dirname(old_rel)
    old_name = os.path.basename(old_rel)

    # Regex to match exact "res://path/to/file.ext" in string literals or project.godot
    exact_pattern = re.compile(
        r'(?<=["\'\*])' + re.escape(old_godot_path) + r'(?=["\'\s,\]])'
    )

    references = []
    root_path = os.path.abspath(project_root)

    for root, dirs, files in os.walk(root_path):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and (allow_addons or d != "addons")]

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc") and filename != "project.godot":
                continue

            abs_file = os.path.join(root, filename)
            rel_file = os.path.relpath(abs_file, root_path).replace("\\", "/")
            godot_file = "res://" + rel_file

            if godot_file == old_godot_path:
                continue

            try:
                size = os.path.getsize(abs_file)
                if size > _MAX_FILE_BYTES:
                    continue
                raw, text, bom = _read_file_text(abs_file)
            except Exception:
                continue

            matches = list(exact_pattern.finditer(text))
            rel_matches = []

            # Check relative preloads in .gd scripts
            if ext == ".gd":
                file_dir = os.path.dirname(rel_file)
                try:
                    rel_to_old = os.path.relpath(old_rel, file_dir).replace("\\", "/")
                except ValueError:
                    rel_to_old = None

                if rel_to_old:
                    candidates = [rel_to_old]
                    if not rel_to_old.startswith("."):
                        candidates.append("./" + rel_to_old)
                    for cand in candidates:
                        # Match only in preload/load/extends to prevent false positives
                        rel_pat = re.compile(
                            r'(\b(?:preload|load|extends)\s*\(?\s*["\'])' +
                            re.escape(cand) +
                            r'(["\'])'
                        )
                        for m in rel_pat.finditer(text):
                            rel_matches.append((m.start(0) + len(m.group(1)), m.start(0) + len(m.group(1)) + len(cand), cand))

            total_occurrences = len(matches) + len(rel_matches)
            if total_occurrences > 0:
                references.append({
                    "path": godot_file,
                    "absolute": abs_file,
                    "occurrences": total_occurrences,
                    "exact_matches": len(matches),
                    "rel_matches": rel_matches,
                    "raw": raw,
                    "text": text,
                    "bom": bom,
                })

    return references


def update_internal_relative_paths(text, old_godot_path, new_godot_path, project_root, moved_files_map=None):
    """Updates internal relative imports (preload, load, extends) in a GDScript file
    when the file moves to a different directory.
    Returns: (updated_text, count_of_changes)
    """
    old_rel = old_godot_path[6:].strip("/")
    new_rel = new_godot_path[6:].strip("/")
    old_dir = os.path.dirname(old_rel)
    new_dir = os.path.dirname(new_rel)

    if old_dir == new_dir and not moved_files_map:
        return text, 0

    import_pat = re.compile(r'(\b(?:preload|load|extends)\s*\(?\s*["\'])([^"\']+)(["\'])')
    changes = 0

    def _replace(match):
        nonlocal changes
        prefix = match.group(1)
        raw_path = match.group(2)
        suffix = match.group(3)

        if raw_path.startswith("uid://"):
            return match.group(0)

        if raw_path.startswith("res://"):
            if moved_files_map and raw_path in moved_files_map:
                changes += 1
                return prefix + moved_files_map[raw_path] + suffix
            return match.group(0)

        # Relative path
        target_rel = os.path.normpath(os.path.join(old_dir, raw_path)).replace("\\", "/")
        target_godot = "res://" + target_rel

        if moved_files_map and target_godot in moved_files_map:
            new_target_godot = moved_files_map[target_godot]
            new_target_rel = new_target_godot[6:]
        else:
            new_target_godot = target_godot
            new_target_rel = target_rel

        # Verify existence
        target_abs = _resolve_safe_path(project_root, target_godot)
        if not os.path.isfile(target_abs) and not (moved_files_map and target_godot in moved_files_map):
            return match.group(0)

        # If target is in new_dir or subfolder of new_dir
        if new_target_rel.startswith(new_dir + "/") or os.path.dirname(new_target_rel) == new_dir:
            calc_rel = os.path.relpath(new_target_rel, new_dir).replace("\\", "/")
            if not calc_rel.startswith("."):
                calc_rel = "./" + calc_rel if raw_path.startswith("./") else calc_rel
            new_path_str = calc_rel
        else:
            new_path_str = new_target_godot

        if new_path_str != raw_path:
            changes += 1
            return prefix + new_path_str + suffix
        return match.group(0)

    updated_text = import_pat.sub(_replace, text)
    return updated_text, changes


def prepare_directory_relocation(project_root, old_path, new_path,
                                 update_references=True, allow_addons=False):
    """Analyze and prepare an atomic directory relocation with reference updates."""
    abs_old = _resolve_safe_path(project_root, old_path)
    abs_new = _resolve_safe_path(project_root, new_path)

    if not os.path.isdir(abs_old):
        raise FileNotFoundError("Исходная папка не найдена: %s" % old_path)

    if os.path.exists(abs_new):
        raise FileExistsError("Целевая папка уже существует: %s" % new_path)

    if not allow_addons and (is_addon_path(old_path, project_root) or is_addon_path(new_path, project_root)):
        raise FileRefactorError("Изменение res://addons требует явного запроса пользователя")

    moved_files_map = {}
    import_files_map = {}
    for root, dirs, filenames in os.walk(abs_old):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and (allow_addons or d != "addons")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext == ".uid":
                continue
            f_abs = os.path.join(root, fn)
            rel_in_old = os.path.relpath(f_abs, abs_old).replace("\\", "/")
            f_old_godot = old_path.rstrip("/") + "/" + rel_in_old
            f_new_godot = new_path.rstrip("/") + "/" + rel_in_old
            if ext == ".import":
                import_files_map[f_old_godot] = f_new_godot
            else:
                moved_files_map[f_old_godot] = f_new_godot

    if not moved_files_map and not import_files_map:
        raise FileRefactorError("Папка %s не содержит подходящих файлов для перемещения" % old_path)

    files_to_modify = []
    total_refs = 0

    # 1. Process each moved file
    for f_old, f_new in sorted(moved_files_map.items()):
        f_abs_old = _resolve_safe_path(project_root, f_old)
        f_abs_new = _resolve_safe_path(project_root, f_new)
        source_raw, source_text, source_bom = _read_file_text(f_abs_old)
        source_hash = _sha256(source_raw)

        after_bytes = source_raw
        internal_changes = 0

        if f_old.lower().endswith(".gd"):
            mod_text, internal_changes = update_internal_relative_paths(
                source_text, f_old, f_new, project_root, moved_files_map=moved_files_map
            )
            if internal_changes > 0:
                lint_errors = gd_lint.lint_gdscript(mod_text)
                if lint_errors:
                    raise FileRefactorError(
                        "После обновления путей в %s обнаружена синтаксическая ошибка: %s"
                        % (f_old, lint_errors[0])
                    )
                after_bytes = (b"\xef\xbb\xbf" if source_bom else b"") + mod_text.encode("utf-8")
                move_diff = build_diff_preview(source_text, mod_text)
                move_diff["action"] = "move_file"
                move_diff["path"] = f_old
                move_diff["dest"] = f_new
                move_diff["lines"].insert(0, {"type": "info", "text": "Файл перемещён в %s (обновлено путей: %d)" % (f_new, internal_changes)})
            else:
                move_diff = {
                    "path": f_old,
                    "action": "move_file",
                    "dest": f_new,
                    "lines": [{"type": "info", "text": "Файл перемещён в %s" % f_new}],
                }
        elif f_old.lower().endswith((".tscn", ".tres")):
            mod_text = source_text
            tscn_changes = 0
            for old_target, new_target in moved_files_map.items():
                pat = re.compile(r'(?<=["\'\*])' + re.escape(old_target) + r'(?=["\'\s,\]])')
                mod_text, c = pat.subn(new_target, mod_text)
                tscn_changes += c
            if tscn_changes > 0:
                after_bytes = (b"\xef\xbb\xbf" if source_bom else b"") + mod_text.encode("utf-8")
                move_diff = build_diff_preview(source_text, mod_text)
                move_diff["action"] = "move_file"
                move_diff["path"] = f_old
                move_diff["dest"] = f_new
                move_diff["lines"].insert(0, {"type": "info", "text": "Файл перемещён в %s (обновлено ссылок: %d)" % (f_new, tscn_changes)})
                internal_changes = tscn_changes
            else:
                move_diff = {
                    "path": f_old,
                    "action": "move_file",
                    "dest": f_new,
                    "lines": [{"type": "info", "text": "Файл перемещён в %s" % f_new}],
                }
        else:
            move_diff = {
                "path": f_old,
                "action": "move_file",
                "dest": f_new,
                "lines": [{"type": "info", "text": "Файл перемещён в %s" % f_new}],
            }

        files_to_modify.append({
            "action": "move_file",
            "path": f_old,
            "dest": f_new,
            "absolute": f_abs_old,
            "dest_absolute": f_abs_new,
            "before_hash": source_hash,
            "before_bytes": source_raw,
            "after_bytes": after_bytes,
            "diff": move_diff,
            "occurrences": internal_changes,
        })
        total_refs += internal_changes

    # 2. Process companion .import files
    for imp_old, imp_new in sorted(import_files_map.items()):
        imp_abs_old = _resolve_safe_path(project_root, imp_old)
        imp_abs_new = _resolve_safe_path(project_root, imp_new)
        imp_raw, imp_text, imp_bom = _read_file_text(imp_abs_old)
        imp_hash = _sha256(imp_raw)

        # Corresponding asset paths (strip .import)
        asset_old = imp_old[:-7] if imp_old.endswith(".import") else imp_old
        asset_new = imp_new[:-7] if imp_new.endswith(".import") else imp_new

        mod_imp_text = re.sub(
            r'(\bsource_file\s*=\s*["\'])' + re.escape(asset_old) + r'(["\'])',
            r'\g<1>' + asset_new + r'\2',
            imp_text
        )
        if mod_imp_text != imp_text:
            imp_after_bytes = (b"\xef\xbb\xbf" if imp_bom else b"") + mod_imp_text.encode("utf-8")
        else:
            imp_after_bytes = imp_raw

        imp_diff = build_diff_preview(imp_text, mod_imp_text)
        imp_diff["action"] = "move_file"
        imp_diff["path"] = imp_old
        imp_diff["dest"] = imp_new
        imp_diff["lines"].insert(0, {"type": "info", "text": "Файл импорта (.import) перемещён в %s" % imp_new})

        files_to_modify.append({
            "action": "move_file",
            "path": imp_old,
            "dest": imp_new,
            "absolute": imp_abs_old,
            "dest_absolute": imp_abs_new,
            "before_hash": imp_hash,
            "before_bytes": imp_raw,
            "after_bytes": imp_after_bytes,
            "diff": imp_diff,
            "occurrences": 1 if mod_imp_text != imp_text else 0,
            "is_companion": True,
        })

    # 3. External reference updates across project
    if update_references:
        external_refs = {}
        for f_old, f_new in moved_files_map.items():
            refs = find_file_references(project_root, f_old, allow_addons=allow_addons)
            for r in refs:
                if r["path"] in moved_files_map:
                    continue
                if r["path"] not in external_refs:
                    external_refs[r["path"]] = {
                        "path": r["path"],
                        "absolute": r["absolute"],
                        "raw": r["raw"],
                        "text": r["text"],
                        "bom": r["bom"],
                        "replacements": [],
                    }
                exact_pat = re.compile(r'(?<=["\'\*])' + re.escape(f_old) + r'(?=["\'\s,\]])')
                external_refs[r["path"]]["replacements"].append(("exact", exact_pat, f_new, r["exact_matches"]))
                if r.get("rel_matches"):
                    external_refs[r["path"]]["replacements"].append(("rel", r["rel_matches"], f_new, len(r["rel_matches"])))

        for path, data in external_refs.items():
            before_text = data["text"]
            after_text = before_text
            file_occurrences = 0

            for kind, item, f_new, count in data["replacements"]:
                if kind == "rel":
                    for start, end, _cand in sorted(item, key=lambda x: x[0], reverse=True):
                        after_text = after_text[:start] + f_new + after_text[end:]
                    file_occurrences += count

            for kind, pat, f_new, count in data["replacements"]:
                if kind == "exact":
                    after_text, c = pat.subn(f_new, after_text)
                    file_occurrences += c

            if after_text != before_text:
                if path.lower().endswith(".gd"):
                    lint_errors = gd_lint.lint_gdscript(after_text)
                    if lint_errors:
                        raise FileRefactorError(
                            "После обновления ссылки в %s обнаружена синтаксическая ошибка: %s"
                            % (path, lint_errors[0])
                        )
                diff = build_diff_preview(before_text, after_text)
                diff["path"] = path
                diff["action"] = "patch_file"
                after_bytes = (b"\xef\xbb\xbf" if data["bom"] else b"") + after_text.encode("utf-8")

                files_to_modify.append({
                    "action": "patch_file",
                    "path": path,
                    "absolute": data["absolute"],
                    "before_hash": _sha256(data["raw"]),
                    "before_bytes": data["raw"],
                    "after_bytes": after_bytes,
                    "diff": diff,
                    "occurrences": file_occurrences,
                })
                total_refs += file_occurrences

    return {
        "action": "rename_file",
        "is_directory": True,
        "old_path": old_path,
        "new_path": new_path,
        "moved_files": moved_files_map,
        "files": files_to_modify,
        "reference_count": total_refs,
        "affected_paths": [item.get("dest", item["path"]) for item in files_to_modify],
    }


def prepare_file_rename(project_root, old_godot_path, new_godot_path,
                        update_references=True, allow_addons=False):
    """Analyze and prepare an atomic file or directory rename/move with reference updates.
    Returns a prepared transaction dictionary with diffs.
    """
    old_path = _normalize_godot_path(old_godot_path)
    new_path = _normalize_godot_path(new_godot_path)

    if old_path == new_path:
        raise FileRefactorError("Новый путь совпадает со старым: %s" % old_path)

    abs_old = _resolve_safe_path(project_root, old_path)
    abs_new = _resolve_safe_path(project_root, new_path)

    if os.path.isdir(abs_old):
        return prepare_directory_relocation(
            project_root, old_path, new_path,
            update_references=update_references, allow_addons=allow_addons
        )

    if not os.path.isfile(abs_old):
        raise FileNotFoundError("Исходный файл не найден: %s" % old_path)

    if os.path.exists(abs_new):
        raise FileExistsError("Целевой файл уже существует: %s" % new_path)

    if not allow_addons and (is_addon_path(old_path, project_root) or is_addon_path(new_path, project_root)):
        raise FileRefactorError("Изменение res://addons требует явного запроса пользователя")

    if os.path.normcase(abs_old) == os.path.normcase(os.path.realpath(os.path.join(project_root, "project.godot"))):
        raise FileRefactorError("Нельзя переименовывать project.godot")

    if old_path.lower().endswith(".import"):
        asset_path = old_path[:-7]
        if os.path.isfile(_resolve_safe_path(project_root, asset_path)):
            raise FileRefactorError(
                "Не следует переименовывать файл .import напрямую. Переименуйте сам ассет (%s), и его .import обновится автоматически."
                % asset_path
            )

    if old_path.lower().endswith(".uid"):
        source_file = old_path[:-4]
        if os.path.isfile(_resolve_safe_path(project_root, source_file)):
            raise FileRefactorError(
                "Не следует переименовывать файл .uid напрямую. Переименуйте сам файл (%s), и его .uid обновится автоматически."
                % source_file
            )

    source_raw, source_text, source_bom = _read_file_text(abs_old)
    source_hash = _sha256(source_raw)

    after_bytes = source_raw
    internal_changes = 0
    old_dir = os.path.dirname(old_path[6:])
    new_dir = os.path.dirname(new_path[6:])
    companion_script = None
    if old_path.lower().endswith(".tscn"):
        script_match = re.search(r'\[ext_resource\s+[^\]]*type="Script"[^\]]*path="([^"]+)"', source_text)
        if script_match:
            companion_script = script_match.group(1)

    if old_dir != new_dir and old_path.lower().endswith(".gd"):
        mod_text, internal_changes = update_internal_relative_paths(
            source_text, old_path, new_path, project_root
        )
        if internal_changes > 0:
            lint_errors = gd_lint.lint_gdscript(mod_text)
            if lint_errors:
                raise FileRefactorError(
                    "После обновления внутренних путей в %s обнаружена синтаксическая ошибка: %s"
                    % (old_path, lint_errors[0])
                )
            after_bytes = (b"\xef\xbb\xbf" if source_bom else b"") + mod_text.encode("utf-8")
            move_diff = build_diff_preview(source_text, mod_text)
            move_diff["action"] = "move_file"
            move_diff["path"] = old_path
            move_diff["dest"] = new_path
            move_diff["lines"].insert(0, {"type": "info", "text": "Файл перемещён в %s (обновлено внутренних путей: %d)" % (new_path, internal_changes)})
        else:
            move_diff = {
                "path": old_path,
                "action": "move_file",
                "dest": new_path,
                "lines": [{"type": "info", "text": "Файл перемещён в %s" % new_path}],
            }
    else:
        move_diff = {
            "path": old_path,
            "action": "move_file",
            "dest": new_path,
            "lines": [{"type": "info", "text": "Файл перемещён в %s" % new_path}],
        }

    files_to_modify = [{
        "action": "move_file",
        "path": old_path,
        "dest": new_path,
        "absolute": abs_old,
        "dest_absolute": abs_new,
        "before_hash": source_hash,
        "before_bytes": source_raw,
        "after_bytes": after_bytes,
        "diff": move_diff,
        "occurrences": internal_changes,
    }]

    total_refs = internal_changes

    # Companion .import file support
    abs_old_import = abs_old + ".import"
    abs_new_import = abs_new + ".import"
    old_import_path = old_path + ".import"
    new_import_path = new_path + ".import"

    if os.path.isfile(abs_old_import):
        if os.path.exists(abs_new_import):
            raise FileExistsError("Целевой файл .import уже существует: %s" % new_import_path)

        imp_raw, imp_text, imp_bom = _read_file_text(abs_old_import)
        imp_hash = _sha256(imp_raw)
        mod_imp_text = re.sub(
            r'(\bsource_file\s*=\s*["\'])' + re.escape(old_path) + r'(["\'])',
            r'\g<1>' + new_path + r'\2',
            imp_text
        )
        if mod_imp_text != imp_text:
            imp_after_bytes = (b"\xef\xbb\xbf" if imp_bom else b"") + mod_imp_text.encode("utf-8")
        else:
            imp_after_bytes = imp_raw

        imp_diff = build_diff_preview(imp_text, mod_imp_text)
        imp_diff["action"] = "move_file"
        imp_diff["path"] = old_import_path
        imp_diff["dest"] = new_import_path
        imp_diff["lines"].insert(0, {"type": "info", "text": "Файл импорта (.import) перемещён в %s" % new_import_path})

        files_to_modify.append({
            "action": "move_file",
            "path": old_import_path,
            "dest": new_import_path,
            "absolute": abs_old_import,
            "dest_absolute": abs_new_import,
            "before_hash": imp_hash,
            "before_bytes": imp_raw,
            "after_bytes": imp_after_bytes,
            "diff": imp_diff,
            "occurrences": 1 if mod_imp_text != imp_text else 0,
            "is_companion": True,
        })

    abs_old_uid = abs_old + ".uid"
    abs_new_uid = abs_new + ".uid"
    new_uid_path = new_path + ".uid"
    if os.path.isfile(abs_old_uid) and os.path.exists(abs_new_uid):
        raise FileExistsError("Целевой файл .uid уже существует: %s" % new_uid_path)

    if update_references:
        references = find_file_references(project_root, old_path, allow_addons=allow_addons)
        exact_pattern = re.compile(
            r'(?<=["\'\*])' + re.escape(old_path) + r'(?=["\'\s,\]])'
        )

        for ref in references:
            before_text = ref["text"]
            after_text = before_text

            if ref.get("rel_matches"):
                for start, end, _cand in sorted(ref["rel_matches"], key=lambda x: x[0], reverse=True):
                    after_text = after_text[:start] + new_path + after_text[end:]

            after_text = exact_pattern.sub(new_path, after_text)

            if ref["path"].lower().endswith(".gd"):
                lint_errors = gd_lint.lint_gdscript(after_text)
                if lint_errors:
                    raise FileRefactorError(
                        "После обновления ссылки в %s обнаружена синтаксическая ошибка: %s"
                        % (ref["path"], lint_errors[0])
                    )

            diff = build_diff_preview(before_text, after_text)
            diff["path"] = ref["path"]
            diff["action"] = "patch_file"
            after_bytes_ref = (b"\xef\xbb\xbf" if ref["bom"] else b"") + after_text.encode("utf-8")

            files_to_modify.append({
                "action": "patch_file",
                "path": ref["path"],
                "absolute": ref["absolute"],
                "before_hash": _sha256(ref["raw"]),
                "before_bytes": ref["raw"],
                "after_bytes": after_bytes_ref,
                "diff": diff,
                "occurrences": ref["occurrences"],
            })
            total_refs += ref["occurrences"]

    return {
        "action": "rename_file",
        "old_path": old_path,
        "new_path": new_path,
        "companion_script": companion_script,
        "update_references": update_references,
        "files": files_to_modify,
        "reference_count": total_refs,
        "affected_paths": [item.get("dest", item["path"]) for item in files_to_modify],
    }


def apply_prepared_file_rename(project_root, prepared, chat_id=None, chat_title=None):
    """Atomically applies prepared file rename/relocation and reference updates.
    Records change in history_manager and supports single-click rollback.
    """
    files = prepared.get("files") or []
    if not files:
        raise FileRefactorError("Подготовленная транзакция не содержит операций")

    old_path = prepared["old_path"]
    new_path = prepared["new_path"]
    is_directory = bool(prepared.get("is_directory", False))

    with _project_lock(project_root):
        # 1. Freshness check
        for item in files:
            if item.get("action") == "move_file":
                if not os.path.isfile(item["absolute"]):
                    raise StaleFileRefactorError("Исходный файл больше не существует: %s" % item["path"])
                with open(item["absolute"], "rb") as h:
                    if _sha256(h.read()) != item["before_hash"]:
                        raise StaleFileRefactorError("Исходный файл изменился: %s" % item["path"])
                if os.path.exists(item["dest_absolute"]):
                    raise FileExistsError("Целевой файл уже появился: %s" % item["dest"])
            elif item.get("action") == "patch_file":
                if not os.path.isfile(item["absolute"]):
                    raise StaleFileRefactorError("Файл со ссылками удалён: %s" % item["path"])
                with open(item["absolute"], "rb") as h:
                    if _sha256(h.read()) != item["before_hash"]:
                        raise StaleFileRefactorError("Файл изменился после предпросмотра: %s" % item["path"])

        # 2. Prepare states for history_manager
        states = []
        batch_paths = []

        for item in files:
            if item.get("action") == "move_file":
                src_path = item["path"]
                dst_path = item["dest"]
                src_abs = item["absolute"]
                has_uid = os.path.isfile(src_abs + ".uid")

                states.append({"path": src_path, "before_bytes": b"", "after_bytes": None})
                states.append({"path": dst_path, "before_bytes": None, "after_bytes": b""})
                batch_paths.extend([src_path, dst_path])

                if has_uid:
                    states.append({"path": src_path + ".uid", "before_bytes": b"", "after_bytes": None})
                    states.append({"path": dst_path + ".uid", "before_bytes": None, "after_bytes": b""})
                    batch_paths.extend([src_path + ".uid", dst_path + ".uid"])

            elif item.get("action") == "patch_file":
                states.append({
                    "path": item["path"],
                    "before_bytes": item["before_bytes"],
                    "after_bytes": item["after_bytes"],
                })
                batch_paths.append(item["path"])

        batch_paths = list(dict.fromkeys(batch_paths))

        entry_id = history_manager.record_batch_change(
            project_root, "rename_file", batch_paths,
            chat_id=chat_id, chat_title=chat_title, states=states
        )

        temps = []
        replaced = []
        moved_items = []

        try:
            # 3. Write patch files using safe temp replacement
            for item in files:
                if item.get("action") == "patch_file":
                    parent = os.path.dirname(item["absolute"])
                    os.makedirs(parent, exist_ok=True)
                    fd, temp_path = tempfile.mkstemp(prefix=".agent_refactor_", dir=parent)
                    with os.fdopen(fd, "wb") as h:
                        h.write(item["after_bytes"])
                        h.flush()
                        os.fsync(h.fileno())
                    temps.append((temp_path, item["absolute"]))

            for temp_path, target_path in temps:
                _replace_file(temp_path, target_path)
                replaced.append((target_path, temp_path))

            # 4. Move target files + uid, and write updated content if after_bytes differs
            for item in files:
                if item.get("action") == "move_file":
                    project_tools.move_project_file(project_root, item["path"], item["dest"])
                    moved_items.append((item["dest"], item["path"]))
                    if item.get("after_bytes") is not None and item.get("after_bytes") != item.get("before_bytes"):
                        with open(item["dest_absolute"], "wb") as h:
                            h.write(item["after_bytes"])
                            h.flush()
                            os.fsync(h.fileno())

            # If directory move, clean up empty old directory
            if is_directory:
                abs_old_dir = _resolve_safe_path(project_root, old_path)
                try:
                    shutil.rmtree(abs_old_dir)
                except OSError:
                    pass

            # 5. Commit change to history
            history_manager.commit_change(project_root, entry_id)

        except Exception as exc:
            # Abort and roll back
            for dst, src in reversed(moved_items):
                try:
                    project_tools.move_project_file(project_root, dst, src)
                except Exception:
                    pass

            for item in files:
                if item.get("action") == "patch_file" and item.get("before_bytes") is not None:
                    try:
                        with open(item["absolute"], "wb") as h:
                            h.write(item["before_bytes"])
                    except Exception:
                        pass

            history_manager.abort_change(project_root, entry_id)
            raise

        finally:
            for temp_path, _ in temps:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass

        # Update index
        changed_paths = [item["dest"] for item in files if item.get("action") == "move_file"] + [
            item["path"] for item in files if item.get("action") == "patch_file"
        ]
        deleted_paths = [item["path"] for item in files if item.get("action") == "move_file"]
        try:
            librarian.note_files_changed(project_root, changed_paths, deleted=deleted_paths)
        except Exception:
            pass
        try:
            ml_project_index.update_entries(project_root, changed_rels=changed_paths)
        except Exception:
            pass

        return {
            "entry_id": entry_id,
            "old_path": old_path,
            "new_path": new_path,
            "is_directory": is_directory,
            "changed_paths": changed_paths,
            "reference_count": prepared.get("reference_count", 0),
            "file_count": len(files),
        }


def sync_references_after_external_move(project_root, old_path, new_path,
                                        is_directory=False, allow_addons=False,
                                        chat_id=None, chat_title=None):
    """Synchronizes references across project after a file or directory was moved externally (e.g. by FileSystemDock).
    Atomically updates string references in .gd, .tscn, .tres, project.godot,
    checks companion .import/.uid, and records changes in history_manager.
    """
    old_path = _normalize_godot_path(old_path)
    new_path = _normalize_godot_path(new_path)
    if old_path == new_path:
        return {
            "ok": True,
            "entry_id": None,
            "old_path": old_path,
            "new_path": new_path,
            "is_directory": is_directory,
            "reference_count": 0,
            "file_count": 0,
            "changed_paths": [],
        }

    files_to_modify = []
    total_refs = 0
    abs_old = _resolve_safe_path(project_root, old_path)
    abs_new = _resolve_safe_path(project_root, new_path)

    # 1. If directory
    if is_directory or (not os.path.isfile(abs_new) and os.path.isdir(abs_new)):
        old_prefix = old_path.rstrip("/") + "/"
        new_prefix = new_path.rstrip("/") + "/"
        dir_pat = re.compile(r'(?<=["\'\*])' + re.escape(old_prefix) + r'([^"\'\s,\]]+)(?=["\'\s,\]])')

        root_path = os.path.abspath(project_root)
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and (allow_addons or d != "addons")]
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc") and filename != "project.godot":
                    continue
                abs_file = os.path.join(root, filename)
                rel_file = os.path.relpath(abs_file, root_path).replace("\\", "/")
                godot_file = "res://" + rel_file
                if godot_file.startswith(old_prefix) or godot_file.startswith(new_prefix):
                    continue
                try:
                    raw, text, bom = _read_file_text(abs_file)
                except Exception:
                    continue

                mod_text, count = dir_pat.subn(new_prefix + r'\1', text)
                if count > 0:
                    after_bytes = (b"\xef\xbb\xbf" if bom else b"") + mod_text.encode("utf-8")
                    files_to_modify.append({
                        "action": "patch_file",
                        "path": godot_file,
                        "absolute": abs_file,
                        "before_hash": _sha256(raw),
                        "before_bytes": raw,
                        "after_bytes": after_bytes,
                        "occurrences": count,
                    })
                    total_refs += count
    else:
        # 2. Single file
        references = find_file_references(project_root, old_path, allow_addons=allow_addons, skip_source_check=True)
        exact_pattern = re.compile(
            r'(?<=["\'\*])' + re.escape(old_path) + r'(?=["\'\s,\]])'
        )
        for ref in references:
            before_text = ref["text"]
            after_text = before_text

            if ref.get("rel_matches"):
                for start, end, _cand in sorted(ref["rel_matches"], key=lambda x: x[0], reverse=True):
                    after_text = after_text[:start] + new_path + after_text[end:]

            after_text = exact_pattern.sub(new_path, after_text)

            if after_text != before_text:
                if ref["path"].lower().endswith(".gd"):
                    lint_errors = gd_lint.lint_gdscript(after_text)
                    if lint_errors:
                        continue
                after_bytes = (b"\xef\xbb\xbf" if ref["bom"] else b"") + after_text.encode("utf-8")
                files_to_modify.append({
                    "action": "patch_file",
                    "path": ref["path"],
                    "absolute": ref["absolute"],
                    "before_hash": _sha256(ref["raw"]),
                    "before_bytes": ref["raw"],
                    "after_bytes": after_bytes,
                    "occurrences": ref["occurrences"],
                })
                total_refs += ref["occurrences"]

        # Check companion .import
        abs_old_import = abs_old + ".import"
        abs_new_import = abs_new + ".import"
        if os.path.isfile(abs_old_import) and not os.path.exists(abs_new_import):
            imp_raw, imp_text, imp_bom = _read_file_text(abs_old_import)
            mod_imp_text = re.sub(
                r'(\bsource_file\s*=\s*["\'])' + re.escape(old_path) + r'(["\'])',
                r'\g<1>' + new_path + r'\2',
                imp_text
            )
            files_to_modify.append({
                "action": "move_file",
                "path": old_path + ".import",
                "dest": new_path + ".import",
                "absolute": abs_old_import,
                "dest_absolute": abs_new_import,
                "before_hash": _sha256(imp_raw),
                "before_bytes": imp_raw,
                "after_bytes": (b"\xef\xbb\xbf" if imp_bom else b"") + mod_imp_text.encode("utf-8") if mod_imp_text != imp_text else imp_raw,
                "occurrences": 1 if mod_imp_text != imp_text else 0,
            })
        elif os.path.isfile(abs_new_import):
            imp_raw, imp_text, imp_bom = _read_file_text(abs_new_import)
            mod_imp_text = re.sub(
                r'(\bsource_file\s*=\s*["\'])' + re.escape(old_path) + r'(["\'])',
                r'\g<1>' + new_path + r'\2',
                imp_text
            )
            if mod_imp_text != imp_text:
                files_to_modify.append({
                    "action": "patch_file",
                    "path": new_path + ".import",
                    "absolute": abs_new_import,
                    "before_hash": _sha256(imp_raw),
                    "before_bytes": imp_raw,
                    "after_bytes": (b"\xef\xbb\xbf" if imp_bom else b"") + mod_imp_text.encode("utf-8"),
                    "occurrences": 1,
                })

        # Check companion .uid
        abs_old_uid = abs_old + ".uid"
        abs_new_uid = abs_new + ".uid"
        if os.path.isfile(abs_old_uid) and not os.path.exists(abs_new_uid):
            uid_raw, _, _ = _read_file_text(abs_old_uid)
            files_to_modify.append({
                "action": "move_file",
                "path": old_path + ".uid",
                "dest": new_path + ".uid",
                "absolute": abs_old_uid,
                "dest_absolute": abs_new_uid,
                "before_hash": _sha256(uid_raw),
                "before_bytes": uid_raw,
                "after_bytes": uid_raw,
                "occurrences": 0,
            })

    if not files_to_modify:
        return {
            "ok": True,
            "entry_id": None,
            "old_path": old_path,
            "new_path": new_path,
            "is_directory": is_directory,
            "reference_count": 0,
            "file_count": 0,
            "changed_paths": [],
        }

    prepared = {
        "files": files_to_modify,
        "old_path": old_path,
        "new_path": new_path,
        "is_directory": is_directory,
        "reference_count": total_refs,
    }
    result = apply_prepared_file_rename(project_root, prepared, chat_id=chat_id, chat_title=chat_title)
    result["ok"] = True
    return result

