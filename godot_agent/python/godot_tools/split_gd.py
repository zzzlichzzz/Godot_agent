# -*- coding: utf-8 -*-
"""split_gd.py — «пила» для .gd-скриптов Godot: вынос методов донора в модули.

Зачем. Панель (agent_panel.gd, 5597 строк) и другие крупные .gd-скрипты
превышают лимит строк карты архитектуры (docs/architecture_map.json,
limits: 1500 warn / 2000 max). Для .py есть «пила» split_refactor.py; для
GDScript её не было. Эта пила делает вынос методов управляемым в духе
остальных рефакторингов ядра: подготовка — только чтение, запись — отдельным
шагом, донор сохраняет все имена методов (тонкие обёртки), поэтому внешние
ссылки (`connect(_on_x)`, `call("_on_x")`, вызовы из других скриптов и
сцен) продолжают работать без правок потребителей.

Модель выноса (v1 — обёртки всем):
  * тело метода переезжает в модуль как статическая функция
    `static func name(panel, <параметры>) -> <тип>`, где `panel` — донор
    (без типа: свойства и методы панели резолвятся динамически);
  * внутри тела переписываются: обращения к членам донора -> `panel.<член>`,
    `$Путь` -> `panel.get_node("Путь")`, `%Имя` -> `panel.get_node("%Имя")`,
    `self` -> `panel`; встроенные методы/свойства Node/Control (get_tree(),
    visible, ...) берутся из кэша ClassDB (agent_api_cache/default_api_cache.json)
    и тоже получают префикс `panel.`;
  * константы, нужные вынесенным методам, копируются в модуль (они
    неизменяемы, дрейф невозможен) — и голые ссылки на константы в теле
    остаются валидными;
  * в доноре на месте метода остаётся тонкая обёртка с исходной сигнатурой
    (и исходным блоком комментариев над методом пока нет — комментарий едет
    в модуль, над обёрткой ставится строка-указатель);
  * в начало донора вставляются preload-константы модулей.

Порядок работы (как у .py-пилы):
    split_gd scan --addon DIR --file agent_panel.gd          # карта ссылок
    split_gd plan --addon DIR --file agent_panel.gd --groups groups.json --json plan.json
    split_gd apply --prepared plan.json --godot GODOT_EXE    # запись + Godot-проверка

Чего пила не делает (осознанные рамки v1):
  * не удаляет обёртки из донора (это следующий шаг: убрать обёртку и
    переписать вызовы в доноре на прямые вызовы модуля — уменьшает донора
    ещё сильнее, но требует правки донорского кода);
  * не правит .tscn/.tres (scene-коннекты на доноре не затрагиваются, имена
    методов сохраняются обёртками);
  * не переносит переменные (@onready/state остаются в доноре);
  * не запускает тесты (приёмка после apply — на вызывающем); при заданном
    --godot проверяет синтаксис каждого записанного .gd через
    `--headless --check-only --script` до замены донора.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = 1
_DEFAULT_TARGET_LINES = 1100
_LINE_WARN = 1500   # docs/architecture_map.json limits (line_exts включают .gd)
_LINE_MAX = 2000
_PANEL_PARAM = "panel"

# Каталоги (в любой точке дерева), которые скан ссылок не обходит.
_SCAN_SKIP_DIRS = {"__pycache__", ".git", ".godot", ".import", ".agent_history",
                   "dist", "build", "minilich_brain", "parser_corpus",
                   "agent_api_cache", "node_modules", ".venv", "_tmp"}

# Расширения текстовых файлов, в которых ищем ссылки.
_SCAN_EXTS = {".gd", ".tscn", ".tres", ".godot", ".md", ".json", ".py",
              ".cfg", ".txt", ".bat", ".cmd"}

_MAX_SCAN_FILE_BYTES = 1024 * 1024
_MAX_OCCURRENCES = 1000

_FUNC_RE = re.compile(r"^(?:static\s+)?func\s+([A-Za-z_]\w*)\s*\(")
_MEMBER_RE = re.compile(r"^(?:const|var|signal|enum|class_name|extends|@\w+)")

# Вертикаль Node-методов на случай отсутствия кэша ClassDB.
_FALLBACK_METHODS = {
    "get_tree", "get_parent", "get_node", "get_node_or_null", "get_children",
    "get_child", "get_child_count", "get_index", "has_node", "find_child",
    "add_child", "remove_child", "move_child", "queue_free", "is_inside_tree",
    "is_node_ready", "set_deferred", "call_deferred", "set", "get", "call",
    "has_method", "connect", "disconnect", "is_connected", "emit_signal",
    "add_to_group", "remove_from_group", "is_in_group", "get_meta",
    "set_meta", "has_meta", "remove_meta", "grab_focus", "release_focus",
    "has_focus", "accept_event", "get_viewport", "get_window",
    "is_visible_in_tree", "get_path", "get_scene_file_path", "duplicate",
    "get_script", "set_script", "get_class", "is_class", "notification",
    "notify_property_list_changed", "set_process", "set_physics_process",
    "set_process_input", "set_process_unhandled_input", "move_to_front",
    "show", "hide", "add_theme_color_override", "add_theme_constant_override",
    "add_theme_font_override", "add_theme_font_size_override",
    "add_theme_stylebox_override", "remove_theme_color_override",
    "remove_theme_constant_override", "remove_theme_font_override",
    "remove_theme_font_size_override", "remove_theme_stylebox_override",
    "get_theme_color", "get_theme_constant", "get_theme_font",
    "get_theme_font_size", "get_theme_stylebox", "has_theme_color",
    "has_theme_constant", "has_theme_font", "has_theme_font_size",
    "has_theme_stylebox", "get_theme_default_font",
    "get_theme_default_font_size", "force_update_transform",
}

# Вертикаль свойств Node/Control на случай отсутствия кэша ClassDB.
_FALLBACK_PROPS = {
    "visible", "position", "size", "rotation", "scale", "pivot_offset",
    "modulate", "self_modulate", "custom_minimum_size", "mouse_filter",
    "focus_mode", "tooltip_text", "top_level", "clip_contents", "layout_mode",
    "anchors_preset", "anchor_left", "anchor_right", "anchor_top",
    "anchor_bottom", "offset_left", "offset_right", "offset_top",
    "offset_bottom", "size_flags_horizontal", "size_flags_vertical",
    "theme_type_variation", "alignment", "autowrap_mode", "text",
    "bbcode_enabled", "scroll_following", "selection_enabled",
    "context_menu_enabled", "editable", "wrap_mode", "placeholder_text",
    "pressed", "button_pressed", "disabled", "flat", "icon", "name", "owner",
}


class SplitGdError(ValueError):
    """Ошибка входа/применения: план нельзя построить или применить."""


class StaleSplitGdError(RuntimeError):
    """Донор изменился после plan или целевой файл уже появился."""


def _norm(rel_path):
    return str(rel_path or "").replace("\\", "/").strip("/")


def _read_text(abs_path):
    with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.read()


def _newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def _write_text(abs_path, text, newline="\n"):
    with open(abs_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\r\n", "\n").replace("\n", newline))


def _replace_text(abs_path, text, newline="\n"):
    """Замена файла через временный + os.replace (одномоментно для читателя)."""
    tmp_path = abs_path + ".split_gd_tmp"
    _write_text(tmp_path, text, newline)
    os.replace(tmp_path, abs_path)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _files_of(addon_dir):
    """Обход дерева аддона: (относительный путь через «/», абсолютный)."""
    root = os.path.abspath(str(addon_dir))
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(item for item in dirs
                         if item not in _SCAN_SKIP_DIRS
                         and not item.startswith("."))
        for name in sorted(names):
            abs_path = os.path.join(base, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            yield rel, abs_path


def _project_root_of(addon_dir):
    """Корень Godot-проекта по расположению аддона (addons/<X>/<Y>), иначе None."""
    candidate = os.path.abspath(os.path.join(str(addon_dir), os.pardir,
                                             os.pardir, os.pardir))
    if os.path.isfile(os.path.join(candidate, "project.godot")):
        return candidate
    return None


def _camel(name):
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", str(name)) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


_KEYWORDS = {
    "and", "as", "assert", "await", "break", "breakpoint", "class",
    "class_name", "const", "continue", "elif", "else", "enum", "extends",
    "for", "func", "if", "in", "is", "match", "namespace", "not", "null",
    "or", "pass", "preload", "return", "self", "signal", "static", "super",
    "trait", "true", "false", "var", "void", "while", "yield", "PI", "TAU",
    "INF", "NAN",
}

_TWO_CHAR = ("->", "==", "!=", "<=", ">=", ":=", "&&", "||", "+=", "-=",
             "*=", "/=", "%=", "**", "<<", ">>", "..")


def tokenize(text):
    """Токены GDScript с точными offsets; комментарии пропущены, строки целиком.

    kind: identifier | number | string | symbol | newline. У каждого токена
    есть start/end (offsets в исходном тексте) и line; у строк — closed.
    """
    tokens = []
    i, line, size = 0, 1, len(text)
    while i < size:
        char = text[i]
        if char in " \t\r":
            i += 1
            continue
        if char == "\n":
            tokens.append({"kind": "newline", "value": "\n", "start": i,
                           "end": i + 1, "line": line})
            i += 1
            line += 1
            continue
        if char == "#":
            end = text.find("\n", i)
            i = size if end < 0 else end
            continue
        if char in "\"'":
            quote = char
            triple = text.startswith(char * 3, i)
            width = 3 if triple else 1
            start, start_line = i, line
            i += width
            closed = False
            while i < size:
                if text[i] == "\\":
                    i += min(2, size - i)
                    continue
                if text.startswith(quote * width, i):
                    i += width
                    closed = True
                    break
                if text[i] == "\n":
                    if not triple:
                        break
                    line += 1
                i += 1
            tokens.append({"kind": "string", "value": text[start:i],
                           "start": start, "end": i, "line": start_line,
                           "closed": closed})
            continue
        if char.isdigit():
            start, start_line = i, line
            while i < size and (text[i].isalnum() or text[i] in "._"):
                i += 1
            tokens.append({"kind": "number", "value": text[start:i],
                           "start": start, "end": i, "line": start_line})
            continue
        if char == "_" or (char.isascii() and char.isalpha()):
            start, start_line = i, line
            i += 1
            while i < size and (text[i] == "_" or text[i].isalnum()
                                and text[i].isascii()):
                i += 1
            tokens.append({"kind": "identifier", "value": text[start:i],
                           "start": start, "end": i, "line": start_line})
            continue
        start_column = i
        two = text[i:i + 2]
        if two in _TWO_CHAR:
            value = two
            i += 2
        else:
            value = char
            i += 1
        tokens.append({"kind": "symbol", "value": value, "start": start_column,
                       "end": i, "line": line})
    return tokens


def _prev_token(tokens, index):
    """Предыдущий значимый токен (newline пропускается)."""
    pos = index - 1
    while pos >= 0 and tokens[pos]["kind"] == "newline":
        pos -= 1
    return tokens[pos] if pos >= 0 else None


def _parse_params(sig_text):
    """Параметры сигнатуры: [{"name", "default"}] из текста между «(» и «)».

    Учитывает типы (`x: int = 5`), коллекции (`Dictionary[String, int]`) и
    многострочные сигнатуры (текст уже склеен вызывающим).
    """
    open_at = sig_text.find("(")
    if open_at < 0:
        return []
    depth, close_at = 0, -1
    for pos in range(open_at, len(sig_text)):
        char = sig_text[pos]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                close_at = pos
                break
    if close_at < 0:
        close_at = len(sig_text)
    inner = sig_text[open_at + 1:close_at]
    parts, current, depth = [], "", 0
    for char in inner:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    params = []
    for part in parts:
        # дефолт — после первого «=» на глубине 0
        depth, eq_at = 0, -1
        for pos, char in enumerate(part):
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "=" and depth == 0:
                eq_at = pos
                break
        head = part if eq_at < 0 else part[:eq_at]
        default = None if eq_at < 0 else part[eq_at + 1:].strip()
        match = re.match(r"\s*([A-Za-z_]\w*)", head)
        if not match:
            continue
        params.append({"name": match.group(1), "default": default})
    return params


def _collect_locals(tokens):
    """Имена, объявленные внутри тела: var/const, for-переменные, параметры лямбд.

    Собирается НАДмножество (все блоки разом): если имя где-то в теле
    объявлено локально, оно нигде не получает префикс `panel.` — ложных
    префиксов не бывает, а редкий пропуск ловится Godot --check-only.
    """
    found = set()
    i = 0
    size = len(tokens)
    while i < size:
        token = tokens[i]
        if token["kind"] == "identifier":
            value = token["value"]
            if value in ("var", "const") and i + 1 < size \
                    and tokens[i + 1]["kind"] == "identifier":
                found.add(tokens[i + 1]["value"])
                i += 2
                continue
            if value == "for":
                j = i + 1
                while j < size and tokens[j]["kind"] != "identifier":
                    j += 1
                if j < size:
                    found.add(tokens[j]["value"])
                i = j + 1
                continue
            if value == "func":
                j = i + 1
                if j < size and tokens[j]["kind"] == "identifier":
                    found.add(tokens[j]["value"])
                    j += 1
                if j < size and tokens[j]["value"] == "(":
                    depth = 0
                    while j < size:
                        tok = tokens[j]
                        if tok["value"] == "(":
                            depth += 1
                        elif tok["value"] == ")":
                            depth -= 1
                            if depth == 0:
                                break
                        elif depth == 1 and tok["kind"] == "identifier":
                            prev = tokens[j - 1] if j else None
                            if prev and prev["value"] in ("(", ","):
                                found.add(tok["value"])
                        j += 1
                i = j + 1
                continue
        i += 1
    return found


_ENGINE_VIRTUALS = {
    "_init", "_ready", "_enter_tree", "_exit_tree", "_process",
    "_physics_process", "_input", "_unhandled_input", "_unhandled_key_input",
    "_shortcut_input", "_gui_input", "_notification", "_to_string",
    "_get_property_list", "_get_configuration_warnings",
}


def _indent_width(line):
    return len(line) - len(line.lstrip(" \t"))


def _code_skeleton(text):
    """Текст без содержимого строк и комментариев — для подсчёта скобок."""
    out = []
    i, size = 0, len(text)
    while i < size:
        char = text[i]
        if char == "#":
            end = text.find("\n", i)
            i = size if end < 0 else end
            out.append("\n")
            continue
        if char in "\"'":
            quote = char
            triple = text.startswith(char * 3, i)
            width = 3 if triple else 1
            i += width
            while i < size:
                if text[i] == "\\":
                    i += min(2, size - i)
                    continue
                if text.startswith(quote * width, i):
                    i += width
                    break
                if text[i] == "\n" and not triple:
                    break
                i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _balance(text):
    depth = 0
    for char in _code_skeleton(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
    return depth


def _leading_comment_start(lines, index):
    """Индекс первой строки прилегающего сверху блока #-комментариев/аннотаций."""
    start = index
    while start > 0:
        stripped = lines[start - 1].strip()
        if stripped.startswith("#") or stripped.startswith("@"):
            start -= 1
        else:
            break
    return start


def file_inventory(text):
    """Инвентарь .gd: заголовок, константы, члены, функции с точными границами.

    funcs[i]: name, sig_start/start (1-based), block_start (с прилегающими
    комментариями), body_start, end, sig_lines (как в файле), sig_text
    (склеенная для разбора), params [{name, default}], ret, has_await, anns.
    """
    lines = str(text or "").splitlines()
    info = {"extends": "", "class_name": "", "header_end": 0, "consts": [],
            "vars": [], "funcs": [], "errors": [], "lines": len(lines)}
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if _indent_width(raw) > 0 or not stripped:
            i += 1
            continue
        if stripped.startswith("extends "):
            match = re.match(r"extends\s+([\w.]+)", stripped)
            if match:
                info["extends"] = match.group(1)
            info["header_end"] = i + 1
            i += 1
            continue
        if stripped.startswith("class_name "):
            info["class_name"] = stripped.split()[1]
            info["header_end"] = i + 1
            i += 1
            continue
        if stripped in ("@tool", "@static_unload") or stripped.startswith("@icon"):
            info["header_end"] = max(info["header_end"], i + 1)
            i += 1
            continue
        if stripped.startswith("const "):
            j = i + 1
            block = raw
            while j < len(lines) and _balance(block) > 0:
                block += "\n" + lines[j]
                j += 1
            match = re.match(r"const\s+([A-Za-z_]\w*)", stripped)
            block_start = _leading_comment_start(lines, i)
            info["consts"].append({
                "name": match.group(1) if match else "",
                "start": i + 1, "end": j, "block_start": block_start + 1,
                "text": "\n".join(lines[block_start:j])})
            i = j
            continue
        prefix_free = re.sub(r"^(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s*)+", "",
                             stripped)
        if prefix_free.startswith("var ") or prefix_free.startswith("signal "):
            match = re.match(r"(?:var|signal)\s+([A-Za-z_]\w*)", prefix_free)
            if match:
                info["vars"].append({"name": match.group(1), "line": i + 1})
            i += 1
            continue
        match = _FUNC_RE.match(stripped)
        if match:
            name = match.group(1)
            sig_start = i
            sig_lines = [raw]
            j = i + 1
            while not (sig_lines[-1].rstrip().endswith(":")
                     and _balance("\n".join(sig_lines)) == 0):
                if j >= len(lines):
                    info["errors"].append(
                        "line %d: сигнатура %s не закрыта" % (i + 1, name))
                    break
                sig_lines.append(lines[j])
                j += 1
            body_start = j
            while body_start < len(lines) and not lines[body_start].strip():
                body_start += 1
            last = body_start - 1
            k = body_start
            while k < len(lines):
                body_stripped = lines[k].strip()
                if body_stripped and _indent_width(lines[k]) == 0:
                    break
                if body_stripped:
                    last = k
                k += 1
            block_start = _leading_comment_start(lines, sig_start)
            sig_text = " ".join(line.strip() for line in sig_lines)
            ret = ""
            ret_match = re.search(r"->\s*([^:]+):\s*$", sig_text)
            if ret_match:
                ret = ret_match.group(1).strip()
            body_text = "\n".join(lines[body_start:last + 1]) if last >= body_start else ""
            info["funcs"].append({
                "name": name, "sig_start": sig_start + 1, "start": sig_start + 1,
                "block_start": block_start + 1, "sig_lines": sig_lines,
                "sig_text": sig_text, "body_start": body_start + 1,
                "end": last + 1, "params": _parse_params(sig_text), "ret": ret,
                "has_await": bool(re.search(r"\bawait\b", body_text)),
                "anns": [line.strip() for line in lines[block_start:sig_start]
                         if line.strip().startswith("@")],
            })
            i = last + 1
            continue
        i += 1
    return info


def suggest_groups(inventory, stem, target_lines=_DEFAULT_TARGET_LINES):
    """Черновые группы: функции по порядку, куски не длиннее target_lines.

    Движковые виртуальные методы (_ready и т.п.) остаются в доноре — их
    выносить можно (обёртка сохранит вызов движка), но для авто-черновика
    это плохая идея: это каркас скрипта, а не «части».
    """
    funcs = [item for item in inventory["funcs"]
             if item["name"] not in _ENGINE_VIRTUALS]
    if not funcs:
        raise SplitGdError("в файле нет методов для выноса")
    chunks, current, size = [], [], 0
    for item in funcs:
        cost = (item["end"] - item["block_start"] + 1) + 1
        if current and size + cost > target_lines:
            chunks.append(current)
            current, size = [], 0
        current.append(item)
        size += cost
    if current:
        chunks.append(current)
    return [{"module": "%s_part%d" % (stem, index),
             "funcs": [item["name"] for item in chunk]}
            for index, chunk in enumerate(chunks, 1)]


def _engine_api(addon_dir, project_root=None, base_class="Control"):
    """(methods, props) цепочки наследования донора из кэша ClassDB.

    Сначала проектный кэш (свежее), затем вшитый в аддон; при отсутствии —
    встроенные списки-вертикали. Глобальные функции Godot в кэше классов
    отсутствуют — это нормально: неизвестные голые имена не переписываются.
    """
    candidates = []
    if project_root:
        try:
            import history_manager as history
            storage = history.get_storage_dir(str(project_root))
            if storage:
                candidates.append(os.path.join(storage, "godot_api_cache.json"))
        except Exception:
            pass
    candidates.append(os.path.join(str(addon_dir), "agent_api_cache",
                                   "default_api_cache.json"))
    candidates.append(os.path.join(str(addon_dir), "default_api_cache.json"))
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                classes = (json.load(handle) or {}).get("classes") or {}
        except (OSError, ValueError):
            continue
        if not classes:
            continue
        for start_class in (base_class, "Control"):
            methods, props, seen, cur, guard = set(), set(), set(), start_class, 0
            while cur and cur not in seen and guard < 30:
                entry = classes.get(cur) or {}
                methods.update(entry.get("methods") or {})
                props.update(entry.get("properties") or [])
                seen.add(cur)
                cur = entry.get("inherits")
                guard += 1
            if methods:
                return methods, props
    return set(_FALLBACK_METHODS), set(_FALLBACK_PROPS)


def _apply_edits(text, edits):
    """Применить правки (start, end, replacement) к тексту по offsets."""
    if not edits:
        return text
    edits = sorted(edits, key=lambda item: (item[0], item[1]))
    out, cursor = [], 0
    for start, end, replacement in edits:
        if start < cursor:
            continue
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def _rewrite_body(body_text, ctx):
    """Переписать тело вынесенного метода под статическую функцию модуля.

    ctx: funcs/vars (члены донора -> panel.<имя>), copies (скопированные
    константы — не трогаются), methods/props (встроенные методы/свойства
    Node/Control -> panel.<имя>), params (параметры метода — локальные).
    Возвращает (новый текст, unknowns — голые неизвестные имена).
    """
    tokens = tokenize(body_text)
    locals_ = _collect_locals(tokens)
    locals_.update(ctx.get("params") or ())
    edits, unknowns = [], set()
    i, size = 0, len(tokens)
    while i < size:
        token = tokens[i]
        value = token["value"]
        if token["kind"] == "identifier":
            if value == "self":
                edits.append((token["start"], token["end"], _PANEL_PARAM))
            elif (value not in _KEYWORDS and value not in locals_
                    and value not in ctx["copies"]):
                prev = _prev_token(tokens, i)
                if not (prev is not None and prev["value"] == "."):
                    if value in ctx["funcs"] or value in ctx["vars"]:
                        edits.append((token["start"], token["start"],
                                      _PANEL_PARAM + "."))
                    elif value in ctx["methods"] or value in ctx["props"]:
                        edits.append((token["start"], token["start"],
                                      _PANEL_PARAM + "."))
                    else:
                        unknowns.add(value)
            i += 1
            continue
        if token["kind"] == "symbol" and value == "$":
            after = token["end"]
            if i + 1 < size and tokens[i + 1]["kind"] == "string":
                path_token = tokens[i + 1]
                edits.append((token["start"], path_token["end"],
                              "%s.get_node(%s)"
                              % (_PANEL_PARAM, path_token["value"])))
                i += 2
                continue
            match = re.match(r"[A-Za-z0-9_/]+", body_text[after:])
            if match and match.group(0):
                end = after + len(match.group(0))
                edits.append((token["start"], end,
                              '%s.get_node("%s")' % (_PANEL_PARAM,
                                                     match.group(0))))
                while i < size and tokens[i]["start"] < end:
                    i += 1
                continue
            i += 1
            continue
        if token["kind"] == "symbol" and value == "%":
            nxt = tokens[i + 1] if i + 1 < size else None
            raw_prev = tokens[i - 1] if i > 0 else None
            at_line_start = raw_prev is None or raw_prev["kind"] == "newline"
            prev = _prev_token(tokens, i)
            allowed = at_line_start or prev is None or prev["value"] in (
                "(", "[", "{", ",", "=", ":", "return", "and", "or", "not",
                "if", "elif", "while", "in", "->", ":=", "+", "-", "*", "/",
                "==", "!=", ">", "<", ">=", "<=", "&&", "||")
            if nxt is not None and nxt["kind"] == "identifier" and allowed:
                edits.append((token["start"], nxt["end"],
                              '%s.get_node("%%%s")' % (_PANEL_PARAM,
                                                       nxt["value"])))
                i += 2
                continue
            i += 1
            continue
        i += 1
    return _apply_edits(body_text, edits), unknowns


def _downgrade_panel_inference(text):
    """`var x := <выражение от panel>` -> `var x = <выражение>`.

    Тело вынесенного метода работает через нетипизированный параметр panel,
    поэтому вывод типа через «:=» от панельных выражений невозможен — Godot
    отвечает «Cannot infer the type». Заражённость (Variant) распространяется
    транзитивно: если в выражении есть panel или уже заражённая переменная,
    вывод типа невозможен. Помечаем такие var и меняем только их «:=» на «=».
    """
    tokens = tokenize(text)
    size = len(tokens)
    entries = []  # (имя, токен операции, множество идентификаторов выражения)
    for index, token in enumerate(tokens):
        if token["kind"] != "identifier" or token["value"] != "var":
            continue
        if index + 2 >= size:
            continue
        name_token, op = tokens[index + 1], tokens[index + 2]
        if name_token["kind"] != "identifier":
            continue
        if op["kind"] != "symbol" or op["value"] not in (":=", "="):
            continue
        rhs_ids, depth, pos = set(), 0, index + 3
        while pos < size:
            item = tokens[pos]
            if item["kind"] == "newline" and depth == 0:
                break
            if item["kind"] == "symbol":
                if item["value"] in ("(", "[", "{"):
                    depth += 1
                elif item["value"] in (")", "]", "}"):
                    depth -= 1
            elif item["kind"] == "identifier":
                rhs_ids.add(item["value"])
            pos += 1
        entries.append((name_token["value"], op, rhs_ids))
    tainted = set()
    changed = True
    while changed:
        changed = False
        for name, _op, rhs_ids in entries:
            if name in tainted:
                continue
            if _PANEL_PARAM in rhs_ids or rhs_ids & tainted:
                tainted.add(name)
                changed = True
    edits = [(op["start"], op["end"], "=") for name, op, _rhs in entries
             if name in tainted and op["value"] == ":="]
    return _apply_edits(text, edits)


def _render_static_sig(func):
    """Сигнатура модуля: static func name(panel[, <параметры>]) -> T."""
    lines = list(func["sig_lines"])
    needle = "func %s(" % func["name"]
    if needle not in lines[0]:
        raise SplitGdError("сигнатуру %s не удалось разобрать" % func["name"])
    if func["params"]:
        lines[0] = lines[0].replace(
            needle, "static func %s(%s, " % (func["name"], _PANEL_PARAM), 1)
    else:
        lines[0] = lines[0].replace(
            needle, "static func %s(%s" % (func["name"], _PANEL_PARAM), 1)
    return lines


def _render_wrapper(func, const_name):
    """Тонкая обёртка донора: исходная сигнатура + делегат в модуль."""
    call = "%s.%s(self%s)" % (
        const_name, func["name"],
        "".join(", " + item["name"] for item in func["params"]))
    if func["has_await"]:
        call = "await " + call
    if func["ret"] and func["ret"] != "void":
        body = "return %s" % call
    else:
        body = call
    return list(func["sig_lines"]) + ["\t" + body]


def scan_refs(addon_dir, rel_path, project_root=None):
    """Карта ссылок на донора и его публичные методы (только чтение).

    Категории: path (строка с именем файла), source_read (.py/.gd, читающие
    исходник донора — их ассерты ломает любой раскол), call (вызовы публичных
    методов из других .gd/.py), doc (.md), mention (прочее). В обёрточной
    модели пути и вызовы сохраняются; hard-файлы = source_read — их стоит
    проверить глазами до apply.
    """
    addon_dir = os.path.abspath(str(addon_dir))
    rel_path = _norm(rel_path)
    donor_abs = os.path.join(addon_dir, rel_path)
    if not os.path.isfile(donor_abs):
        raise SplitGdError("донор не найден: %s" % rel_path)
    donor_text = _read_text(donor_abs)
    inventory = file_inventory(donor_text)
    file_name = os.path.basename(rel_path)
    stem = os.path.splitext(file_name)[0]
    public_names = sorted({item["name"] for item in inventory["funcs"]
                           if not item["name"].startswith("_")})
    call_re = None
    if public_names:
        call_re = re.compile(r"(?:\.\s*(?:%s)\s*\(|\"(?:%s)\")"
                             % ("|".join(re.escape(name) for name in public_names),
                                "|".join(re.escape(name) for name in public_names)))
    read_markers = ("open(", "read_text", "read_bytes", "read_string",
                    "check-only", "--script", "source_code", "get_script")
    occurrences = []
    counts = {"path": 0, "source_read": 0, "call": 0, "doc": 0, "mention": 0}
    files_by_kind = {"source_read": set(), "call": set(), "doc": set(),
                     "path": set()}
    truncated = False
    for rel, abs_path in _files_of(addon_dir):
        if rel == rel_path:
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext not in _SCAN_EXTS:
            continue
        try:
            with open(abs_path, "rb") as handle:
                if os.path.getsize(abs_path) > _MAX_SCAN_FILE_BYTES:
                    continue
            text = _read_text(abs_path)
        except OSError:
            continue
        if file_name not in text and stem not in text and call_re is None:
            continue
        if file_name not in text and stem not in text and call_re is not None \
                and not call_re.search(text):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            has_name = file_name in line or stem in line
            relevant = has_name or (call_re is not None
                                    and bool(call_re.search(line)))
            if not relevant:
                continue
            if ext == ".md":
                kind = "doc"
            elif file_name in line and any(marker in line
                                           for marker in read_markers):
                kind = "source_read"
            elif call_re is not None and call_re.search(line):
                kind = "call"
            elif has_name:
                kind = "path"
            else:
                kind = "mention"
            counts[kind] += 1
            files_by_kind.setdefault(kind, set()).add(rel)
            if len(occurrences) < _MAX_OCCURRENCES:
                occurrences.append({"file": rel, "line": number, "kind": kind,
                                    "text": line.strip()[:160]})
            else:
                truncated = True
    all_files = set().union(*files_by_kind.values()) if files_by_kind else set()
    hard_files = sorted(files_by_kind.get("source_read") or ())
    return {
        "schema": SCHEMA, "donor": rel_path, "lines": inventory["lines"],
        "extends": inventory["extends"], "class_name": inventory["class_name"],
        "funcs": len(inventory["funcs"]), "consts": len(inventory["consts"]),
        "vars": len(inventory["vars"]), "public_methods": public_names,
        "counts": counts, "occurrences": occurrences, "truncated": truncated,
        "hard_files": hard_files,
        "soft_files": sorted(all_files - set(hard_files)),
    }


def _print_scan_summary(result):
    counts = result["counts"]
    print("Донор: %s (%d строк, extends %s, методов %d, const %d, членов %d)"
          % (result["donor"], result["lines"], result["extends"] or "?",
             result["funcs"], result["consts"], result["vars"]))
    print("Упоминаний: path=%d, call=%d, doc=%d, source_read=%d, mention=%d"
          % (counts["path"], counts["call"], counts["doc"],
             counts["source_read"], counts["mention"]))
    hard = result["hard_files"]
    if hard:
        print("hard-файлы (читают исходник донора — проверь вручную):")
        for item in hard:
            print("  * %s" % item)
    else:
        print("hard-файлов нет: раскол в обёрточной модели безопасен.")


def _normalize_groups(groups, func_by_name):
    """Проверить и очистить группы: [{"module": name, "funcs": [методы]}]."""
    if not groups:
        raise SplitGdError("пустой список групп (--groups или auto)")
    if isinstance(groups, dict):
        groups = groups.get("groups")
    result, seen_modules, used = [], set(), {}
    for index, raw in enumerate(groups, 1):
        if not isinstance(raw, dict):
            raise SplitGdError("группа %d: ожидается объект {module, funcs}" % index)
        module = str(raw.get("module") or "").strip()
        if not re.match(r"^[a-z][a-z0-9_]*$", module):
            raise SplitGdError("группа %d: некорректное имя модуля %r"
                               % (index, module))
        if module in seen_modules:
            raise SplitGdError("модуль %s указан дважды" % module)
        seen_modules.add(module)
        names = raw.get("funcs")
        if not isinstance(names, list) or not names:
            raise SplitGdError("группа %s: пустой список funcs" % module)
        clean = []
        for name in names:
            name = str(name)
            if name not in func_by_name:
                raise SplitGdError("метод %s не найден в доноре" % name)
            if name in used:
                raise SplitGdError("метод %s назначен дважды (модули %s и %s)"
                                   % (name, used[name], module))
            used[name] = module
            clean.append(name)
        result.append({"module": module, "funcs": clean})
    return result


def _render_module(donor_rel, module_name, const_texts, blocks):
    """Текст модуля: @tool RefCounted + копии констант + статические методы."""
    parts = [
        "@tool",
        "extends RefCounted",
        "",
        "# Модуль %s: методы вынесены «пилой» split_gd из %s."
        % (module_name, donor_rel),
        "# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,",
        "# поэтому connect()/call() по исходным именам продолжают работать.",
        "# Тело работает через параметр panel: к членам донора — panel.<член>,",
        "# к другим методам донора — panel.<метод> (через его обёртку).",
    ]
    if const_texts:
        parts.append("")
        parts.append("# --- константы, скопированные из донора (неизменяемы) ---")
        parts.extend(const_texts)
    for _name, lines, _func in blocks:
        parts.append("")
        parts.extend(lines)
    return "\n".join(parts) + "\n"


def plan_split(addon_dir, rel_path, groups=None, target_lines=_DEFAULT_TARGET_LINES,
               project_root=None):
    """План раскола (только чтение): модули + новый текст донора + diff-статистика.

    Возвращает prepared-dict, пригодный и для печати, и для apply
    (--prepared). Все проверки входа (группы, имена, конфликты, super,
    аннотации, дефолты-идентификаторы) выполняются ЗДЕСЬ; при провале
    готовится SplitGdError, донор не трогается вовсе.
    """
    addon_dir = os.path.abspath(str(addon_dir))
    rel_path = _norm(rel_path)
    donor_abs = os.path.join(addon_dir, rel_path)
    if not os.path.isfile(donor_abs):
        raise SplitGdError("донор не найден: %s" % rel_path)
    project_root = project_root or _project_root_of(addon_dir)
    if not project_root:
        raise SplitGdError("не найден корень проекта (project.godot рядом с addons); "
                           "укажите --project")
    project_root = os.path.abspath(str(project_root))
    donor_text = _read_text(donor_abs)
    newline = _newline_of(donor_text)
    lines = donor_text.split("\n")
    inventory = file_inventory(donor_text)
    if inventory["errors"]:
        raise SplitGdError("разбор донора: " + "; ".join(inventory["errors"]))
    if not inventory["funcs"]:
        raise SplitGdError("в доноре не найдено методов")
    stem = os.path.splitext(os.path.basename(rel_path))[0]
    func_by_name = {item["name"]: item for item in inventory["funcs"]}
    if not groups:
        groups = suggest_groups(inventory, stem, target_lines)
    groups = _normalize_groups(groups, func_by_name)
    const_by_name = {item["name"]: item for item in inventory["consts"]
                     if item["name"]}
    var_names = {item["name"] for item in inventory["vars"]}
    fn_names = set(func_by_name)
    methods, props = _engine_api(addon_dir, project_root,
                                 inventory["extends"] or "Control")
    addon_rel = os.path.relpath(addon_dir, project_root).replace("\\", "/")
    warnings = []
    modules, wrappers, spans = [], [], []
    targets = []
    for group in groups:
        module_name = group["module"]
        module_rel = _norm(os.path.join(os.path.dirname(rel_path),
                                        module_name + ".gd"))
        if os.path.exists(os.path.join(addon_dir, module_rel)):
            raise StaleSplitGdError("целевой модуль уже существует: %s" % module_rel)
        const_name = _camel(module_name)
        if const_name in const_by_name or const_name in var_names \
                or const_name in fn_names:
            raise SplitGdError("preload-константа %s конфликтует с членом донора"
                               % const_name)
        targets.append((module_name, module_rel, const_name, group["funcs"]))
    for module_name, module_rel, const_name, names in targets:
        funcs = sorted((func_by_name[name] for name in names),
                       key=lambda item: item["block_start"])
        module_consts, blocks = set(), []
        for func in funcs:
            name = func["name"]
            if name in _ENGINE_VIRTUALS:
                warnings.append("%s — движковый виртуальный метод: обёртка "
                                "сохранит вызов движка" % name)
            if func["anns"]:
                raise SplitGdError("метод %s: аннотации %s не поддерживаются v1"
                                   % (name, ", ".join(func["anns"])))
            if any(item["name"] == _PANEL_PARAM for item in func["params"]):
                raise SplitGdError("метод %s: параметр %s конфликтует с "
                                   "параметром модуля" % (name, _PANEL_PARAM))
            body = "\n".join(lines[func["body_start"] - 1:func["end"]])
            if not body.strip():
                raise SplitGdError("метод %s: пустое тело — нечего выносить" % name)
            if re.search(r"\bsuper\b", body):
                raise SplitGdError("метод %s: super() не поддерживается "
                                   "статическим модулем v1" % name)
            tokens = tokenize(body)
            if _PANEL_PARAM in _collect_locals(tokens):
                raise SplitGdError("метод %s: тело объявляет имя %s — конфликт "
                                   "с параметром модуля" % (name, _PANEL_PARAM))
            for param in func["params"]:
                default = (param.get("default") or "").strip()
                if re.match(r"^[A-Za-z_]\w*$", default):
                    if default in var_names or default in fn_names:
                        raise SplitGdError("метод %s: дефолт параметра %s = %s "
                                           "ссылается на член донора (в статике "
                                           "нельзя)" % (name, param["name"], default))
                    if default in const_by_name:
                        module_consts.add(default)
            used_here = {token["value"] for token in tokens
                         if token["kind"] == "identifier"} & set(const_by_name)
            module_consts.update(used_here)
            context = {"funcs": fn_names, "vars": var_names,
                       "copies": used_here, "methods": methods, "props": props,
                       "params": [item["name"] for item in func["params"]]}
            rewritten, _unknowns = _rewrite_body(body, context)
            rewritten = _downgrade_panel_inference(rewritten)
            block_lines = list(lines[func["block_start"] - 1:func["sig_start"] - 1])
            block_lines.extend(_render_static_sig(func))
            block_lines.extend(rewritten.split("\n"))
            blocks.append((name, block_lines, func))
            spans.append((func["block_start"], func["end"], name))
        ordered = sorted(spans, key=lambda item: item[0])
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] <= previous[1]:
                raise SplitGdError("блоки методов %s и %s пересекаются — "
                                   "разбор донора неточен" % (previous[2], current[2]))
        const_texts = [const_by_name[name]["text"] for name
                       in sorted(module_consts, key=lambda item:
                                 const_by_name[item]["start"])]
        module_text = _render_module(rel_path, module_name, const_texts, blocks)
        module_lines = module_text.count("\n") + 1
        if module_lines > _LINE_MAX:
            raise SplitGdError("модуль %s: %d строк — больше максимума %d"
                               % (module_rel, module_lines, _LINE_MAX))
        if module_lines > _LINE_WARN:
            warnings.append("модуль %s: %d строк — больше warn-порога %d"
                            % (module_rel, module_lines, _LINE_WARN))
        modules.append({"module": module_name, "rel": module_rel,
                        "const": const_name, "funcs": [item["name"]
                                                       for item in funcs],
                        "content": module_text, "lines": module_lines,
                        "_blocks": blocks})
        for func in funcs:
            wrappers.append({"name": func["name"], "module": module_name,
                             "await": bool(func["has_await"])})


    block_map = {}
    for module in modules:
        for _name, _block_lines, func in module["_blocks"]:
            block_map[func["block_start"]] = (module, func)
    donor_out, installed = [], False
    number, total = 1, len(lines)
    while number <= total:
        entry = block_map.get(number)
        if entry:
            module, func = entry
            donor_out.append("# split_gd: тело — %s" % module["rel"])
            donor_out.extend(_render_wrapper(func, module["const"]))
            number = func["end"] + 1
            continue
        donor_out.append(lines[number - 1])
        if number == inventory["header_end"] and modules and not installed:
            installed = True
            donor_out.append("")
            donor_out.append("# --- части (вынесены «пилой» split_gd) ---")
            donor_dir = os.path.dirname(rel_path)
            for module in modules:
                rel_from_donor = os.path.relpath(module["rel"], donor_dir or ".")
                rel_from_donor = rel_from_donor.replace("\\", "/")
                donor_out.append('const %s = preload("%s")'
                                 % (module["const"], rel_from_donor))
        number += 1
    donor_new = re.sub(r"\n{4,}", "\n\n\n", "\n".join(donor_out))
    donor_lines_new = donor_new.count("\n") + 1
    if donor_lines_new > _LINE_MAX:
        warnings.append("донор после раскола: %d строк — всё ещё больше "
                        "максимума %d" % (donor_lines_new, _LINE_MAX))
    elif donor_lines_new > _LINE_WARN:
        warnings.append("донор после раскола: %d строк — всё ещё больше "
                        "warn-порога %d (следующий шаг: снять обёртки, v2)"
                        % (donor_lines_new, _LINE_WARN))
    prepared = {
        "schema": SCHEMA, "kind": "split_gd",
        "addon_dir": addon_dir, "project_root": project_root,
        "donor": rel_path, "donor_abs": donor_abs,
        "donor_sha256": _sha256(donor_text), "newline": newline,
        "target_lines": int(target_lines),
        "groups": [{"module": item["module"], "funcs": item["funcs"]}
                   for item in modules],
        "modules": [{"rel": item["rel"], "const": item["const"],
                     "funcs": item["funcs"], "content": item["content"],
                     "lines": item["lines"]} for item in modules],
        "donor_content": donor_new,
        "wrappers": wrappers,
        "warnings": warnings,
        "stats": {"moved": len(wrappers), "modules": len(modules),
                  "donor_before": inventory["lines"],
                  "donor_after": donor_lines_new},
    }
    return prepared


def _public_plan(prepared):
    """Копия плана без содержимого файлов — для --json и логов."""
    view = dict(prepared)
    view["modules"] = [{key: value for key, value in item.items()
                        if key != "content"} for item in prepared["modules"]]
    view["donor_content"] = None
    view["warnings"] = list(prepared.get("warnings") or [])
    return view


def _print_plan_summary(prepared):
    stats = prepared["stats"]
    print("План раскола %s (модель: статические модули + обёртки в доноре):"
          % prepared["donor"])
    for module in prepared["modules"]:
        print("  + %s (%d строк): %s"
              % (module["rel"], module["lines"], ", ".join(module["funcs"])))
    print("  Донор: %d -> %d строк; обёрток %d, модулей %d"
          % (stats["donor_before"], stats["donor_after"], stats["moved"],
             stats["modules"]))
    for warning in prepared["warnings"]:
        print("  ! %s" % warning)


def _godot_check(godot, project_root, abs_script, timeout=90):
    """Проверка синтаксиса .gd: godot --headless --check-only --script."""
    rel = os.path.relpath(str(abs_script), str(project_root)).replace("\\", "/")
    cmd = [str(godot), "--headless", "--path", str(project_root),
           "--check-only", "--script", "res://" + rel]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(project_root), timeout=timeout)
    except OSError as error:
        raise SplitGdError("не удалось запустить Godot (%s): %s" % (godot, error))
    except subprocess.TimeoutExpired:
        return 1, "таймаут проверки %s сек" % timeout
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def apply_prepared_split(prepared, godot=None, timeout=90):
    """Записать модули и новый донор; при --godot проверить каждый .gd.

    Порядок: повторные проверки -> модули на диск -> Godot-check каждого
    модуля и временной копии нового донора -> замена донора. Любой провал
    Godot: созданные модули/temp удаляются, донор не трогается вовсе.
    """
    if not isinstance(prepared, dict) or prepared.get("kind") != "split_gd":
        raise SplitGdError("ожидается prepared-план split_gd (JSON команды plan)")
    donor_abs = prepared["donor_abs"]
    if not os.path.isfile(donor_abs):
        raise StaleSplitGdError("донор исчез: %s" % prepared["donor"])
    if _sha256(_read_text(donor_abs)) != prepared["donor_sha256"]:
        raise StaleSplitGdError("донор изменился после plan: %s"
                                % prepared["donor"])
    addon_dir = prepared["addon_dir"]
    project_root = prepared.get("project_root")
    created, checks = [], []
    for module in prepared["modules"]:
        if os.path.exists(os.path.join(addon_dir, module["rel"])):
            raise StaleSplitGdError("целевой файл уже существует: %s"
                                    % module["rel"])
    try:
        for module in prepared["modules"]:
            target = os.path.join(addon_dir, module["rel"])
            _write_text(target, module["content"], prepared["newline"])
            created.append(target)
        if godot:
            if not project_root:
                raise SplitGdError("для --godot в плане нужен project_root")
            for module in prepared["modules"]:
                code, output = _godot_check(
                    godot, project_root, os.path.join(addon_dir, module["rel"]),
                    timeout)
                checks.append({"file": module["rel"], "code": code,
                               "output": output[-400:]})
                if code != 0:
                    raise SplitGdError("модуль %s не прошёл проверку Godot:\n%s"
                                       % (module["rel"], output[-800:]))
            temp_rel = prepared["donor"][:-3] + ".check_tmp.gd"
            temp_abs = os.path.join(addon_dir, temp_rel)
            _write_text(temp_abs, prepared["donor_content"], prepared["newline"])
            created.append(temp_abs)
            code, output = _godot_check(godot, project_root, temp_abs, timeout)
            checks.append({"file": temp_rel, "code": code,
                           "output": output[-400:]})
            os.remove(temp_abs)
            created.remove(temp_abs)
            if code != 0:
                raise SplitGdError("новый донор не прошёл проверку Godot:\n%s"
                                   % output[-800:])
        _replace_text(donor_abs, prepared["donor_content"], prepared["newline"])
    except Exception:
        for path in reversed(created):
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    return {"donor": prepared["donor"],
            "modules": [item["rel"] for item in prepared["modules"]],
            "wrappers": len(prepared["wrappers"]),
            "donor_lines": prepared["stats"]["donor_after"],
            "checks": checks}


def _dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="split_gd — раскол .gd-донора на модули (scan/plan/apply)")
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan", help="карта ссылок на донора (только чтение)")
    scan.add_argument("--addon", required=True, help="каталог аддона")
    scan.add_argument("--file", required=True, help=".gd-донор (от аддона)")
    scan.add_argument("--project", default="", help="корень Godot-проекта")
    scan.add_argument("--json", default="", help="куда записать отчёт")
    plan = sub.add_parser("plan", help="план раскола (только чтение)")
    plan.add_argument("--addon", required=True)
    plan.add_argument("--file", required=True)
    plan.add_argument("--groups", default="",
                      help="JSON [{module, funcs}]; без него — авто-черновик")
    plan.add_argument("--target-lines", type=int, default=_DEFAULT_TARGET_LINES)
    plan.add_argument("--project", default="")
    plan.add_argument("--json", default="", help="публичный план (без контента)")
    plan.add_argument("--prepared", default="", help="полный план для apply")
    apply_cmd = sub.add_parser("apply", help="записать модули и донора")
    apply_cmd.add_argument("--prepared", required=True)
    apply_cmd.add_argument("--godot", default="", help="путь к Godot для check")
    apply_cmd.add_argument("--timeout", type=int, default=90)
    apply_cmd.add_argument("--json", default="")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 3
    try:
        if args.command == "scan":
            result = scan_refs(args.addon, args.file, args.project or None)
            _print_scan_summary(result)
            if args.json:
                _dump_json(args.json, result)
                print("отчёт записан: %s" % args.json)
            return 2 if result["hard_files"] else 0
        if args.command == "plan":
            groups = None
            if args.groups:
                with open(args.groups, "r", encoding="utf-8-sig") as handle:
                    groups = json.load(handle)
                if isinstance(groups, dict):
                    groups = groups.get("groups")
            prepared = plan_split(args.addon, args.file, groups,
                                  args.target_lines, args.project or None)
            _print_plan_summary(prepared)
            if args.prepared:
                _dump_json(args.prepared, prepared)
                print("prepared записан: %s" % args.prepared)
            if args.json:
                _dump_json(args.json, _public_plan(prepared))
                print("план записан: %s" % args.json)
            return 0
        if args.command == "apply":
            with open(args.prepared, "r", encoding="utf-8-sig") as handle:
                prepared = json.load(handle)
            receipt = apply_prepared_split(prepared, args.godot or None,
                                           args.timeout)
            print("Донор %s обновлён: %d строк, модулей %d, обёрток %d"
                  % (receipt["donor"], receipt["donor_lines"],
                     len(receipt["modules"]), receipt["wrappers"]))
            for check in receipt["checks"]:
                print("  check %s: %s" % (check["file"],
                                          "ok" if check["code"] == 0
                                          else "код %s" % check["code"]))
            if args.json:
                _dump_json(args.json, receipt)
            return 0
    except (SplitGdError, StaleSplitGdError) as error:
        print("split_gd: %s" % error, file=sys.stderr)
        return 3
    except OSError as error:
        print("split_gd: %s" % error, file=sys.stderr)
        return 3
    return 3


if __name__ == "__main__":
    sys.exit(main())








