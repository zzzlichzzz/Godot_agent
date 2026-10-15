# -*- coding: utf-8 -*-
"""Глубокая карточка функции (docs/function_card_plan.md, S2–S3).

Продолжение карточки символа L7 (librarian.py::_symbol_card): обычная карточка
даёт объявление и все ссылки; глубокая карточка отвечает на запрос модели вида
«func:take_damage» ОДНИМ вызовом: тело функции дословно + ВСЕ символы тела с
адресами (свой член / конст файла / автолоад / чужой class_name / встроенное)
и три связи функции — кто вызывает, кто наследует, кто переопределяет.

Границы v1 (план §2/§5, часть решений):
- один хоп: тела внешних функций НЕ раскрываются — только имена и адреса;
- статика без вывода типов: вызов по значению переменной помечается dynamic;
  «proven» — объявление найдено точно (свой файл / единственное в проекте);
- тело в бюджет не входит и не режется; секции режутся честными хвостами
  «…(+N more)», счётчик важнее списка (§2.3).

Источники данных — только существующие слои: семантический индекс
(ml_project_index.semantic_snapshot), извлечение тел gd_functions,
иерархия наследников из движка переименований (symbol_refactor_part1).
Пересборки индекса нет: карточка join-ит «иерархия × упоминания».
"""
import hashlib
import os
import re

import gd_functions
from minilich import ml_project_index

# v1 (план §2.3): стартовые пределы секций. Честный хвост обязателен,
# когда список обрезан; сам счётчик важнее списка.
CARD_MAX_PARAMS = 12
CARD_MAX_LOCALS = 16
CARD_MAX_MEMBERS = 24
CARD_MAX_CONSTS = 16
CARD_MAX_SIGNALS = 8
CARD_MAX_AUTOLOADS = 12
CARD_MAX_EXTERNAL = 12
CARD_MAX_PROVEN_FUNCS = 16
CARD_MAX_DYNAMIC = 16
CARD_MAX_CALL_FILES = 12
CARD_MAX_CALL_LINES_PER_FILE = 3
CARD_MAX_STRING_HITS = 8
CARD_MAX_SUBCLASSES = 12
CARD_MAX_OVERRIDES = 8

# Идентификаторы, которые парсер может занести в references, но которые не
# являются символами проекта (та же идея, что _CARD_SKIP_USES в librarian).
_SKIP_NAMES = {
    "self", "super", "true", "false", "null", "PI", "TAU", "INF", "NAN",
    "if", "elif", "else", "for", "while", "return", "break", "continue",
    "pass", "match", "and", "or", "not", "in", "is", "as", "await", "yield",
}

# Встроенные типы GDScript: в карточке не символы проекта и не builtins —
# шум аннотаций сигнатуры/приведений (контекст type). Молча пропускаются.
_BUILTIN_TYPES = {
    "int", "float", "bool", "String", "StringName", "NodePath", "RID",
    "Array", "Dictionary", "Vector2", "Vector2i", "Vector3", "Vector3i",
    "Vector4", "Vector4i", "Rect2", "Rect2i", "Transform2D", "Transform3D",
    "Plane", "Quaternion", "AABB", "Basis", "Projection", "Color", "Callable",
    "Signal", "Object", "Variant", "void",
    "PackedByteArray", "PackedInt32Array", "PackedInt64Array",
    "PackedFloat32Array", "PackedFloat64Array", "PackedStringArray",
    "PackedVector2Array", "PackedVector3Array", "PackedVector4Array",
    "PackedColorArray",
}

# project.godot: строка автолоада `Name="*res://x.gd"` или `Name="*uid://..."`.
_AUTOLOAD_RE = re.compile(r'^([A-Za-z_]\w*)\s*=\s*"(\*?)([^"]+)"')


# Глобальные утилиты GDScript. В кэше ClassDB их НЕТ (виртуальные классы
# @GDScript/@GlobalScope экспортёр не отдаёт — проверено на реальном кэше:
# Object отдает 62 метода, @GDScript — 0), поэтому список статичный.
# Это знание о языке, а не о проекте; не найденное здесь честно уходит в dynamic.
_GD_BUILTINS = {
    "print", "printerr", "printraw", "prints", "printt", "push_error",
    "push_warning", "randf", "randf_range", "randi", "randi_range", "randomize",
    "seed", "rand_from_seed", "clamp", "clampf", "clampi", "min", "max",
    "mini", "maxi", "abs", "absf", "absi", "sign", "signf", "signi", "floor",
    "floorf", "floori", "ceil", "ceilf", "ceili", "round", "roundf", "roundi",
    "lerp", "lerpf", "lerp_angle", "lerp_color", "pow", "sqrt", "sin", "cos",
    "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh", "tanh", "exp",
    "log", "log2", "fmod", "fposmod", "posmod", "deg_to_rad", "rad_to_deg",
    "linear_to_db", "db_to_linear", "ease", "step_decimals", "snap",
    "snapped", "wrapf", "wrapi", "move_toward", "smoothstep", "remap",
    "is_nan", "is_inf", "is_equal_approx", "is_zero_approx", "str", "int",
    "float", "bool", "len", "range", "typeof", "type_string", "type_convert",
    "str_to_var", "var_to_str", "bytes_to_var", "var_to_bytes",
    "hash", "weakref", "instance_from_id", "is_instance_valid",
    "is_instance_of", "load", "preload", "resource_path", "assert",
    "instance_has_signal", "dict_to_inst", "inst_to_dict", "rid_allocate_id",
}


def _cap(items, limit):
    """Список строк с честным хвостом «(+N more)» — как в L7-карточке."""
    items = list(items)
    if len(items) <= limit:
        return items, 0
    return items[:limit], len(items) - limit


def _uid_map(project_root):
    """uid://... -> res://путь (по спутникам *.gd.uid, один проход os.walk)."""
    uid_to_path = {}
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".godot")]
        for fname in filenames:
            if not fname.endswith(".gd.uid"):
                continue
            try:
                with open(os.path.join(dirpath, fname),
                          encoding="utf-8", errors="replace") as fh:
                    uid = (fh.read(128).strip() or "")
            except OSError:
                continue
            if uid.startswith("uid://"):
                res = os.path.join(dirpath, fname[:-len(".uid")])
                rel = os.path.relpath(res, project_root).replace("\\", "/")
                uid_to_path[uid] = "res://" + rel
    return uid_to_path


def _autoload_map(project_root):
    """Имя автолоада -> res://путь скрипта. Путь может быть uid:// —
    разрешаем по спутникам .uid (полигон хранит автолоады именно так)."""
    from project_tools import read_project_file
    try:
        text, _trunc = read_project_file(
            project_root, "res://project.godot", max_chars=262144)
    except Exception:
        return {}
    uids = _uid_map(project_root)
    out = {}
    in_autoload = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_autoload = stripped == "[autoload]"
            continue
        if not in_autoload:
            continue
        m = _AUTOLOAD_RE.match(stripped)
        if not m:
            continue
        name, _star, value = m.group(1), m.group(2), m.group(3)
        if value.startswith("uid://"):
            value = uids.get(value, value + " (uid не разрешён)")
        out[name] = value
    return out

# === ЧАСТЬ 2: сбор данных (S2) — вставляется ниже ===

def _own_decl_kinds():
    return ("variable", "constant", "enum", "enum_member", "signal", "function")


def _class_of(entries, rel):
    from symbol_refactor_part1 import _class_name_for_file
    entry = entries.get(rel)
    if not entry:
        return None
    return _class_name_for_file(entry["semantic"]) or None


def _collect(project_root, res_path, func_name, content, addon_dir=None):
    """Сбор фактов карточки. Возвращает dict с «сырыми» группами; форматирование —
    в _format(). Ошибки данных не роняют карточку: недостающее честно помечается."""
    rel = res_path[len("res://"):] if res_path.startswith("res://") else res_path
    rel = rel.replace("\\", "/")
    found, missing = gd_functions.extract_functions(content, [func_name])
    if not found:
        return {"error": "func-not-found: %s в %s" % (func_name, res_path),
                "missing": missing}
    body = found[0]
    try:
        snapshot = ml_project_index.semantic_snapshot(project_root)
    except Exception as exc:
        return {"error": "index-unavailable: %s" % exc}
    files = snapshot.get("files") or []
    entries = {str(e.get("path") or ""): e for e in files
               if isinstance(e.get("semantic"), dict)}
    entry = entries.get(rel)
    warnings = []
    if entry is None:
        warnings.append("файл вне семантического индекса — связи не собраны")

    decls = (entry.get("semantic") or {}).get("declarations", []) if entry else []
    refs = (entry.get("semantic") or {}).get("references", []) if entry else []
    func_decl = None
    for d in decls:
        if d.get("kind") == "function" and d.get("name") == func_name:
            if func_decl is None or int(d.get("start") or 0) < int(
                    func_decl.get("start") or 0):
                func_decl = d
    fid = (func_decl or {}).get("id")

    params = sorted((d for d in decls if fid is not None and
                     d.get("owner") == fid and d.get("kind") == "parameter"),
                    key=lambda d: int(d.get("start") or 0))
    locals_ = sorted((d for d in decls if fid is not None and
                      d.get("owner") == fid and d.get("kind") == "variable"),
                     key=lambda d: int(d.get("start") or 0))
    own_names = {d.get("name") for d in params} | {d.get("name") for d in locals_}

    # Упоминания тела: references с owner == id функции.
    body_names = {}
    for r in refs:
        if r.get("owner") != fid:
            continue
        name = r.get("name")
        if not name or name in _SKIP_NAMES or name == func_name:
            continue
        rec = body_names.setdefault(
            name, {"count": 0, "contexts": set(), "line": None})
        rec["count"] += 1
        rec["contexts"].add(str(r.get("context") or "identifier"))
        if rec["line"] is None or int(r.get("line") or 0) < rec["line"]:
            rec["line"] = int(r.get("line") or 0)

# === ЧАСТЬ 2b: классификация имён — вставляется ниже ===

    same_file = {}
    for d in decls:
        name = d.get("name")
        if name and name not in same_file and d.get("kind") in _own_decl_kinds():
            same_file[name] = d
        if name and d.get("kind") == "class_name":
            same_file.setdefault("class:" + name, d)

    autoloads = _autoload_map(project_root)
    class_names = {}   # class_name -> (res://путь, строка)
    global_funcs = {}  # имя топ-уровневой func -> список файлов
    for e in files:
        semantic = e.get("semantic") or {}
        epath = "res://" + str(e.get("path") or "")
        for d in semantic.get("declarations", []):
            name = d.get("name")
            if not name:
                continue
            if d.get("kind") == "class_name":
                class_names.setdefault(name, (epath, int(d.get("line") or 0)))
            elif d.get("kind") == "function" and d.get("owner") == "script":
                global_funcs.setdefault(name, []).append(epath)

    builtin_names = set(_GD_BUILTINS)
    try:
        import gd_api_cache
        for cls_name in ("@GDScript", "@GlobalScope"):
            methods, _props, _signals = gd_api_cache.collect_members(
                project_root, cls_name, addon_dir=addon_dir)
            builtin_names.update(methods or {})
    except Exception:
        pass  # кэша нет — статичного списка достаточно

    groups = {"members": [], "consts": [], "signals": [], "autoloads": [],
              "external_classes": [], "proven_funcs": [], "dynamic": [],
              "builtins": []}
    local_func_names = []
    for name, rec in body_names.items():
        if name in own_names:
            continue
        if "type" in rec["contexts"] and name in _BUILTIN_TYPES:
            continue  # аннотация встроенного типа — не символ проекта
        d = same_file.get(name)
        if d is not None:
            kind = d.get("kind")
            if kind == "variable":
                groups["members"].append("%s (L%d%s)" % (
                    name, int(d.get("line") or 0),
                    ", ×%d" % rec["count"] if rec["count"] > 1 else ""))
            elif kind in ("constant", "enum", "enum_member"):
                groups["consts"].append("%s (L%d%s)" % (
                    name, int(d.get("line") or 0),
                    ", ×%d" % rec["count"] if rec["count"] > 1 else ""))
            elif kind == "signal":
                groups["signals"].append(
                    "%s (L%d)" % (name, int(d.get("line") or 0)))
            else:
                # Топ-уровневая функция СВОЕГО файла, объявленная ещё и в других
                # файлах, — proven по имени быть не может: честный dynamic
                # (план §5: имя-merge по проекту создаёт ложные связи).
                if (d.get("owner") == "script"
                        and len(global_funcs.get(name, [])) > 1):
                    groups["dynamic"].append(
                        "%s (×%d, объявлена в %d файлах)" % (
                            name, rec["count"], len(global_funcs[name])))
                else:
                    local_func_names.append(name)
            continue
        if name in autoloads:
            groups["autoloads"].append("%s → %s" % (name, autoloads[name]))
            continue
        if name in builtin_names:
            groups["builtins"].append(name)
            continue
        if name in class_names:
            cpath, cline = class_names[name]
            groups["external_classes"].append(
                "%s %s:%d" % (name, cpath, cline))
            continue
        gfiles = global_funcs.get(name)
        if gfiles and len(gfiles) == 1 and gfiles[0] != res_path:
            # proven: единственное топ-уровневое объявление имени в проекте.
            fpath = gfiles[0]
            fline = None
            for e in files:
                if "res://" + str(e.get("path") or "") == fpath:
                    for d in (e.get("semantic") or {}).get("declarations", []):
                        if (d.get("kind") == "function" and
                                d.get("name") == name and
                                d.get("owner") == "script"):
                            fline = int(d.get("line") or 0)
                            break
                    break
            groups["proven_funcs"].append(
                "%s %s%s" % (name, fpath, (":%d" % fline) if fline else ""))
            continue
        groups["dynamic"].append("%s (×%d%s)" % (
            name, rec["count"],
            (", " + "/".join(sorted(rec["contexts"] - {"call"})))
            if rec["contexts"] - {"call"} else ""))

    local_func_names = sorted(set(local_func_names))
    spans = {}
    if local_func_names:
        lf, _m = gd_functions.extract_functions(content, local_func_names)
        for item in lf:
            spans[item["name"]] = (item["start_line"], item["end_line"])

    return {
        "error": None, "warnings": warnings, "body": body,
        "params": params, "locals": locals_, "groups": groups,
        "spans": spans, "entries": entries, "files": files,
        "class_name": _class_of(entries, rel), "autoloads": autoloads,
    }

# === ЧАСТЬ 3: связи и форматирование — вставляется ниже ===

def subclass_count(project_root, res_path):
    """Сколько файлов наследует данный (для выбора объявления при имени,
    объявленном в нескольких файлах: карточку строим для иерархического корня).
    Ошибки глотаются — 0 означает «данных нет»."""
    try:
        snapshot = ml_project_index.semantic_snapshot(project_root)
        files = snapshot.get("files") or []
        rel = res_path[len("res://"):] if res_path.startswith("res://") else res_path
        cls = None
        for e in files:
            if str(e.get("path") or "") == rel.replace("\\", "/"):
                from symbol_refactor_part1 import _class_name_for_file
                cls = _class_name_for_file(e.get("semantic") or {})
                break
        from symbol_refactor_part1 import _find_subclasses
        return len(_find_subclasses(project_root, res_path, cls, {"files": files}))
    except Exception:
        return 0


def _collect_relations(project_root, res_path, func_name, data):
    """Три связи функции (план §2.2). Их нельзя смешивать: «call files» —
    упоминания имени с proven/probable/dynamic; «subclasses» — файлы-наследники
    по ИЕРАРХИИ extends (имя может не встречаться вовсе — греп их не находит);
    «overrides» — наследник объявляет ту же func (и зовёт ли super)."""
    files = data["files"]
    call_sites = []      # (path, line, ctx): call=proven, member=probable
    string_hits = []     # (path, line, value)
    for e in files:
        semantic = e.get("semantic") or {}
        epath = "res://" + str(e.get("path") or "")
        for r in semantic.get("references", []):
            if r.get("name") != func_name:
                continue
            ctx = str(r.get("context") or "")
            if ctx in ("call", "member"):
                # call — прямой вызов по имени (proven). member — вызов/чтение
                # через значение (`enemy.take_damage()`): для функции это
                # ПРОБНОЕ «вызывается» (может быть и свойством) — честный grade.
                call_sites.append((epath, int(r.get("line") or 0), ctx))
        for s in semantic.get("strings", []):
            if func_name in str(s.get("value") or ""):
                string_hits.append((epath, int(s.get("line") or 0),
                                    str(s.get("value") or "")))
    call_sites.sort()

    # Наследники — по иерархии extends из движка переименований (тот же
    # механизм, что у rename_symbol: карточка и rename обязаны соглашаться).
    subclasses = []
    overrides = []
    try:
        from symbol_refactor_part1 import _find_subclasses
        found = _find_subclasses(project_root, res_path,
                                 data.get("class_name"), {"files": files})
    except Exception:
        found = set()
    for path in sorted(found):
        cls = None
        decl_line = None
        override = None
        rel = str(path)[len("res://"):] if str(path).startswith("res://") else str(path)
        entry = data["entries"].get(rel)
        if entry:
            semantic = entry["semantic"]
            for d in semantic.get("declarations", []):
                if d.get("kind") == "class_name":
                    cls = d.get("name")
                    decl_line = int(d.get("line") or 0)
                elif (d.get("kind") == "function" and
                        d.get("name") == func_name and override is None):
                    override = {"line": int(d.get("line") or 0), "super": False,
                                "id": d.get("id")}
            if override:
                for r in semantic.get("references", []):
                    if (r.get("owner") == override.get("id") and
                            r.get("name") == func_name and
                            str(r.get("context") or "") in ("call", "member")):
                        # super.hurt(...) парсер даёт как member — метка
                        # честно «probable super», а не доказанный super.
                        override["super"] = True
                        break
        subclasses.append({"path": path, "class": cls, "line": decl_line})
        if override:
            overrides.append({"path": path, "line": override["line"],
                              "super": override["super"]})
    data["call_sites"] = call_sites
    data["string_hits"] = string_hits
    data["subclasses"] = subclasses
    data["overrides"] = overrides
    return data

# === ЧАСТЬ 3b: форматирование и точка входа — вставляется ниже ===

def _tail(count):
    return "  …(+%d more)" % count


def _format(func_name, res_path, data):
    """Собирает готовые строки карточки (план §3). Тело не режется."""
    body = data["body"]
    g = data["groups"]
    out = ["FUNC CARD func:%s — %s:%d-%d (class %s, rev=sha1:%s)" % (
        func_name, res_path, body["start_line"], body["end_line"],
        data.get("class_name") or "?",
        hashlib.sha1((data.get("_content") or "").encode("utf-8")
                     ).hexdigest()[:8])]
    for w in data.get("warnings") or []:
        out.append("WARNING: %s" % w)
    out.append("[BODY]")
    out.append(body["snippet"])
    out.append("[SYMBOLS]")
    show, n = _cap([str(p.get("name")) for p in data["params"]],
                   CARD_MAX_PARAMS)
    if show:
        out.append("  params: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(["%s (L%d)" % (p.get("name"), int(p.get("line") or 0))
                    for p in data["locals"]], CARD_MAX_LOCALS)
    if show:
        out.append("  locals: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["members"], CARD_MAX_MEMBERS)
    if show:
        out.append("  members: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["consts"], CARD_MAX_CONSTS)
    if show:
        out.append("  consts: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["signals"], CARD_MAX_SIGNALS)
    if show:
        out.append("  signals: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["autoloads"], CARD_MAX_AUTOLOADS)
    if show:
        out.append("  autoloads: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["external_classes"], CARD_MAX_EXTERNAL)
    if show:
        out.append("  external classes: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["builtins"], CARD_MAX_DYNAMIC)
    if show:
        out.append("  builtins: %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["proven_funcs"], CARD_MAX_PROVEN_FUNCS)
    if show:
        out.append("  funcs proven: %s" % "; ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["dynamic"], CARD_MAX_DYNAMIC)
    if show:
        out.append("  dynamic (не разрулено): %s" % ", ".join(show) + (_tail(n) if n else ""))
    show, n = _cap(g["local_funcs"], CARD_MAX_PROVEN_FUNCS)
    if show:
        out.append("  funcs (этот файл): %s" % "; ".join(show) + (_tail(n) if n else ""))
    proven_n = sum(1 for _p, _l, c in data["call_sites"] if c == "call")
    probab_n = len(data["call_sites"]) - proven_n
    out.append("[CALLERS] (%d proven, %d probable в %d файлах)" % (
        proven_n, probab_n,
        len({p for p, _l, _c in data["call_sites"]})))
    by_file = {}
    for p, ln, c in data["call_sites"]:
        by_file.setdefault(p, []).append((ln, c))
    show, n = _cap(sorted(by_file), CARD_MAX_CALL_FILES)
    for p in show:
        items = sorted(by_file[p])
        head, extra = _cap(items, CARD_MAX_CALL_LINES_PER_FILE)
        ctxs = {c for _ln, c in items}
        grade = "proven" if ctxs == {"call"} else (
            "probable" if ctxs == {"member"} else "proven+probable")
        out.append("  %s:%s%s (%s)" % (
            p, ", ".join(str(ln) for ln, _c in head),
            " (+%d)" % extra if extra else "", grade))
    if n:
        out.append("  …(+%d more files)" % n)
    if data["string_hits"]:
        show, n = _cap(sorted(data["string_hits"]), CARD_MAX_STRING_HITS)
        out.append("  dynamic strings:")
        for p, ln, val in show:
            val = val.strip("\"'")
            val = val[:48] + ("…" if len(val) > 48 else "")
            out.append('    %s:%d "%s"' % (p, ln, val.replace("\n", " ")))
        if n:
            out.append("    …(+%d more)" % n)
    if data["subclasses"]:
        out.append("[SUBCLASSES] (%d)" % len(data["subclasses"]))
        show, n = _cap(data["subclasses"], CARD_MAX_SUBCLASSES)
        for s in show:
            out.append("  %s%s" % (s["path"],
                       (" (%s, class_name L%d)" % (s["class"], s["line"]))
                       if s["class"] else ""))
        if n:
            out.append("  …(+%d more)" % n)
    if data["overrides"]:
        out.append("[OVERRIDES]")
        show, n = _cap(data["overrides"], CARD_MAX_OVERRIDES)
        for o in show:
            out.append("  %s:%d%s" % (o["path"], o["line"],
                       " (probable super)" if o["super"] else ""))
        if n:
            out.append("  …(+%d more)" % n)
    return out


def build_function_card(project_root, res_path, func_name, content=None,
                        addon_dir=None):
    """Публичная точка входа: возвращает dict {"lines": [...]} либо {"error": "..."}.
    content передаёт вызывающий (мост уже прочитал файл по политике доступа);
    addon_dir — папка аддона для вшитого кэша Godot API (как у librarian.answer)."""
    if content is None:
        from project_tools import read_project_file
        try:
            content, _trunc = read_project_file(
                project_root, res_path, max_chars=1 << 21)
        except Exception as exc:
            return {"error": "file-unreadable: %s" % exc}
    data = _collect(project_root, res_path, func_name, content,
                    addon_dir=addon_dir)
    if data.get("error"):
        return {"error": data["error"]}
    data["_content"] = content
    data["groups"]["local_funcs"] = [
        "%s:%d-%d" % (name, data["spans"][name][0], data["spans"][name][1])
        for name in sorted(data["spans"])]
    _collect_relations(project_root, res_path, func_name, data)
    return {"lines": _format(func_name, res_path, data)}
