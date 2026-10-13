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
import file_refactor
from minilich import ml_project_index
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path)
# --- фасад: код разнесён по модулям (split_refactor) ---
from symbol_refactor_data import _DECL_KINDS, _KEYWORDS
from symbol_refactor_part1 import (KINDS,
    LocatorError,
    MODES,
    RenameError,
    StaleRenameError,
    UnsafeRenameError,
    UnsupportedRenameError,
    _CONN_FIELD_RE,
    _CONN_HEADER_RE,
    _DECL_TO_KIND,
    _IDENTIFIER,
    _KIND_TO_DECL,
    _LOCKS,
    _LOCKS_GUARD,
    _MAX_SOURCE_CHARS,
    _class_name_for_file,
    _collect_path_reference_edits,
    _collect_scene_connection_edits,
    _collect_scene_property_edits,
    _connection_replacement,
    _decl_kind,
    _exact_string_value,
    _find_subclasses,
    _get_script_parent,
    _move_with_uid,
    _owner_belongs_to_script,
    _owner_in_script,
    _owner_is_script_scope,
    _owner_is_top_level,
    _owner_shadows_name,
    _owner_within,
    _parse_locator,
    _plan_file_rename,
    _project_lock,
    _read_source,
    _reference_in_other_scope,
    _replace_file,
    _scene_script_owners,
    _section_node_path,
    _sha256,
    _token_neighbors,
    _typed_receivers,
    _unverified_reason,
    _validate_action)
from symbol_refactor_part2 import (_CLASS_NAME_STRING_CALLS,
    _DYNAMIC_STRING_CALLS,
    _USAGE_KINDS,
    _add_allowed_addon_semantics,
    _assert_hierarchy_renamed,
    _classify_string_reference,
    _classify_string_reference_kind,
    _collision,
    _engine_class_name,
    _exclude_entry,
    _exclude_place_kind,
    _excluded_places,
    _is_real_conflict,
    _load_snapshot,
    _locate_declaration,
    _project_global_names,
    _reference_is_safe,
    _unwritable_subclass_overrides,
    _usage_excluded,
    _usage_query,
    analyze_rename,
    exclude_place,
    find_references)
from symbol_refactor_part3 import (_count_renamed,
    apply_prepared_rename,
    prepare_rename)
__all__ = ["KINDS", "LocatorError", "MODES", "RenameError", "StaleRenameError", "UnsafeRenameError", "UnsupportedRenameError", "analyze_rename", "apply_prepared_rename", "exclude_place", "find_references", "prepare_rename", "prepared_diffs", "public_prepared"]


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
        "unverified_count": int(prepared.get("unverified_count") or 0),
        "renamed_count": int(prepared.get("renamed_count") or 0),
        "skipped_usages": list(prepared.get("skipped_usages") or []),
        "mode": prepared.get("mode", "strict"),
        "allow_unverified": bool(prepared.get("allow_unverified")),
        "file_rename": prepared.get("file_rename"),
    }


def prepared_diffs(prepared):
    diffs = [item["diff"] for item in prepared.get("files", [])]
    # Перенос файла показываем в том же диффе: пользователь должен увидеть
    # итог транзакции, а не только изменённое содержимое.
    if prepared.get("file_rename_diff"):
        diffs.append(prepared["file_rename_diff"])
    return diffs
