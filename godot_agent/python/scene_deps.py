# -*- coding: utf-8 -*-
"""Анализ зависимостей «скрипт <-> сцена» (v47).

Задача: найти в скриптах обработчики сигналов вида `_on_...`, которые
НИГДЕ не подключены (ни через [connection] в сценах, ни через connect()
в коде), и если трактовка ОДНОЗНАЧНА — добавить [connection] в сцену
автоматически. Во всех спорных случаях — только мягкая заметка модели,
НИКАКИХ блокировок и принудительных переписываний.

Защита от ложных срабатываний (все условия должны выполняться, иначе молчим):
1. Смотрим только на функции с префиксом `_on_` на верхнем уровне скрипта.
2. Метод не упомянут ни в одном [connection] ни этой, ни других сцен проекта.
3. Метод не подключается в коде: нет его имени ни в строках с connect(/Callable(,
   ни в виде строкового литерала "_on_x" где бы то ни было в проекте.
4. Имя обработчика совпадает со стандартным шаблоном редактора Godot:
   `_on_<имя_узла_snake_case>_<сигнал>` или `_on_<сигнал>` (сигнал от себя),
   причём сигнал из таблицы KNOWN_SIGNALS и тип узла реально его излучает.
5. Трактовка ровно ОДНА (один узел-источник + один сигнал). Две и более —
   только заметка.
6. Если этот сигнал этого узла уже подключен к ДРУГОМУ методу — не лезем,
   только заметка (возможно, так задумано).
7. Суффикс совпадает с ПОЛЬЗОВАТЕЛЬСКИМ сигналом (signal my_event в коде) —
   тип источника неизвестен, только мягкая заметка.
8. Ничего не распознали — МОЛЧИМ (никакого шума на каждый _on_-метод).
"""
import os
import re

# Сигнал -> типы узлов, которые его излучают (только часто используемые
# и ОДНОЗНАЧНЫЕ пары; широкие сигналы вроде mouse_entered/gui_input намеренно
# НЕ включены — у них слишком много возможных источников = ложные срабатывания).
_BUTTONS = ("Button", "BaseButton", "TextureButton", "CheckBox", "CheckButton",
            "MenuButton", "OptionButton", "LinkButton", "TouchScreenButton")
_AREAS = ("Area2D", "Area3D")
_RIGID = ("RigidBody2D", "RigidBody3D")

KNOWN_SIGNALS = {
    "body_entered": _AREAS + _RIGID,
    "body_exited": _AREAS + _RIGID,
    "area_entered": _AREAS,
    "area_exited": _AREAS,
    "body_shape_entered": _AREAS + _RIGID,
    "body_shape_exited": _AREAS + _RIGID,
    "area_shape_entered": _AREAS,
    "area_shape_exited": _AREAS,
    "pressed": _BUTTONS,
    "toggled": _BUTTONS,
    "timeout": ("Timer",),
    "animation_finished": ("AnimationPlayer", "AnimatedSprite2D", "AnimatedSprite3D"),
    "animation_started": ("AnimationPlayer",),
    "finished": ("AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D",
                  "GPUParticles2D", "GPUParticles3D"),
    "screen_entered": ("VisibleOnScreenNotifier2D", "VisibleOnScreenNotifier3D"),
    "screen_exited": ("VisibleOnScreenNotifier2D", "VisibleOnScreenNotifier3D"),
    "text_changed": ("LineEdit", "TextEdit", "CodeEdit"),
    "text_submitted": ("LineEdit",),
    "value_changed": ("HSlider", "VSlider", "SpinBox", "HScrollBar", "VScrollBar"),
    "item_selected": ("OptionButton", "ItemList"),
    "item_activated": ("ItemList",),
    "id_pressed": ("PopupMenu",),
    "frame_changed": ("AnimatedSprite2D", "AnimatedSprite3D", "Sprite2D"),
    "wait_time_changed": (),  # заглушка-пример, пустой список = никогда не сработает
}

_MAX_FILE_BYTES = 512 * 1024
_SKIP_DIRS = {".godot", ".git", ".import", "__pycache__"}

_ATTR_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)')
_HANDLER_RE = re.compile(r"^(?:static\s+)?func\s+(_on_\w+)\s*\(", re.M)
_CUSTOM_SIGNAL_RE = re.compile(r"^\s*signal\s+(\w+)", re.M)


def to_snake(name):
    """Приближение Godot String.to_snake_case():
    Camera3D -> camera_3d, Wall_North -> wall_north, HTTPRequest -> http_request."""
    out = []
    prev = ""
    for i, ch in enumerate(name):
        if ch in "-. ":
            out.append("_")
            prev = ch
            continue
        if ch.isupper():
            if prev and prev.islower():
                out.append("_")
            elif prev.isupper() and i + 1 < len(name) and name[i + 1].islower():
                out.append("_")
            out.append(ch.lower())
        elif ch.isdigit():
            if prev and prev.islower():
                out.append("_")
            out.append(ch)
        else:
            out.append(ch)
        prev = ch
    s = "".join(out)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_").lower()


def _parse_attrs(head):
    res = {}
    for key, raw in _ATTR_RE.findall(head):
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = raw[1:-1]
        res[key] = raw
    return res


def parse_scene(text):
    """Разбирает .tscn: ext-ресурсы, узлы (с вычисленным путём от корня и
    привязанным скриптом) и [connection]-секции."""
    ext = {}         # id -> {"type":..., "path":...}
    nodes = []       # {"name","type","parent","path","script_id"}
    connections = [] # {"signal","from","to","method"}
    cur_node = None
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("[ext_resource") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            if a.get("id"):
                ext[a["id"]] = {"type": a.get("type", ""), "path": a.get("path", "")}
            cur_node = None
        elif stripped.startswith("[node") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            name = a.get("name", "")
            parent = a.get("parent")
            if parent is None:
                path = "."
            elif parent == ".":
                path = name
            else:
                path = parent + "/" + name
            cur_node = {
                "name": name,
                "type": a.get("type"),  # None для instance=... без type
                "parent": parent,
                "path": path,
                "script_id": None,
            }
            nodes.append(cur_node)
        elif stripped.startswith("[connection") and stripped.endswith("]"):
            a = _parse_attrs(stripped[1:-1])
            connections.append({
                "signal": a.get("signal", ""),
                "from": a.get("from", ""),
                "to": a.get("to", ""),
                "method": a.get("method", ""),
            })
            cur_node = None
        elif stripped.startswith("["):
            cur_node = None
        elif cur_node is not None and stripped.startswith("script"):
            m = re.match(r'script\s*=\s*ExtResource\(\s*"([^"]+)"\s*\)', stripped)
            if m:
                cur_node["script_id"] = m.group(1)
    return ext, nodes, connections


def extract_handlers(script_text):
    return list(dict.fromkeys(_HANDLER_RE.findall(script_text or "")))


def _res_to_abs(project_root, res_path):
    rel = (res_path or "").replace("res://", "", 1).replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return None
    return os.path.normpath(os.path.join(project_root, rel))


def _collect_project_files(project_root):
    """Собирает тексты всех .gd и .tscn проекта (небольшие файлы)."""
    gd, scenes = {}, {}
    if not project_root or not os.path.isdir(project_root):
        return gd, scenes
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if not (fn.endswith(".gd") or fn.endswith(".tscn")):
                continue
            full = os.path.join(root, fn)
            try:
                if os.path.getsize(full) > _MAX_FILE_BYTES:
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                continue
            if fn.endswith(".gd"):
                gd[os.path.normpath(full)] = text
            else:
                scenes[os.path.normpath(full)] = text
    return gd, scenes


def _method_connected_in_code(method, gd_texts):
    """Метод уже подключается/упоминается в коде? Считаем подключённым, если:
    - имя встречается строковым литералом ("_on_x" / '_on_x') где угодно;
    - или имя встречается в строке вместе с connect( или Callable(.
    Лучше пропустить реальную проблему, чем подключить сигнал дважды."""
    q1, q2 = '"%s"' % method, "'%s'" % method
    word = re.compile(r"\b%s\b" % re.escape(method))
    for text in gd_texts.values():
        if q1 in text or q2 in text:
            return True
        for line in text.splitlines():
            if ("connect(" in line or "Callable(" in line) and word.search(line):
                return True
    return False


def _method_connected_in_scenes(method, scene_texts, exclude_abs=None):
    needle = 'method="%s"' % method
    for path, text in scene_texts.items():
        if exclude_abs and os.path.normpath(path) == os.path.normpath(exclude_abs):
            continue
        if needle in text:
            return True
    return False


def _collect_custom_signals(gd_texts):
    names = set()
    for text in gd_texts.values():
        names.update(_CUSTOM_SIGNAL_RE.findall(text))
    return names


def _find_candidates(handler, nodes, script_node):
    """Все возможные трактовки имени обработчика: (узел-источник, сигнал)."""
    suffix = handler[len("_on_"):]
    candidates = []
    for node in nodes:
        ntype = node.get("type")
        if not ntype:
            continue  # instance=... — тип неизвестен, не гадаем
        snake = to_snake(node.get("name", ""))
        for sig, types in KNOWN_SIGNALS.items():
            if ntype not in types:
                continue
            if suffix == "%s_%s" % (snake, sig):
                candidates.append((node, sig))
            elif node is script_node and suffix == sig:
                # сигнал от СЕБЯ: func _on_body_entered на скрипте Area3D
                candidates.append((node, sig))
    # убираем дубли (одинаковый путь + сигнал)
    seen, uniq = set(), []
    for node, sig in candidates:
        key = (node["path"], sig)
        if key not in seen:
            seen.add(key)
            uniq.append((node, sig))
    return uniq


def analyze_scene_action(scene_text, scene_res_path, project_root):
    """Анализ СЦЕНЫ, которую собираемся записать.
    Возвращает (новый_текст, список_описаний_добавленных_подключений, список_заметок)."""
    added, notes = [], []
    text = scene_text.replace("\r\n", "\n")
    try:
        ext, nodes, connections = parse_scene(text)
    except Exception:
        return scene_text, [], []
    script_nodes = []
    for node in nodes:
        sid = node.get("script_id")
        if not sid or sid not in ext:
            continue
        info = ext[sid]
        if info.get("type") != "Script" or not info.get("path", "").endswith(".gd"):
            continue
        script_nodes.append((node, info["path"]))
    if not script_nodes:
        return scene_text, [], []

    gd_texts, scene_texts = _collect_project_files(project_root)
    custom_signals = _collect_custom_signals(gd_texts)
    scene_abs = _res_to_abs(project_root, scene_res_path) if project_root else None
    existing_methods = {c["method"] for c in connections}
    existing_from_signal = {(c["from"], c["signal"]) for c in connections}

    new_lines = []
    for node, script_res in script_nodes:
        script_abs = _res_to_abs(project_root, script_res) if project_root else None
        if not script_abs or not os.path.isfile(script_abs):
            continue  # скрипта ещё нет на диске — не гадаем
        try:
            with open(script_abs, "r", encoding="utf-8", errors="replace") as f:
                script_text = f.read()
        except Exception:
            continue
        for handler in extract_handlers(script_text):
            if handler in existing_methods:
                continue
            if _method_connected_in_code(handler, gd_texts):
                continue
            if _method_connected_in_scenes(handler, scene_texts, exclude_abs=scene_abs):
                continue
            suffix = handler[len("_on_"):]
            candidates = _find_candidates(handler, nodes, node)
            if len(candidates) == 1:
                src, sig = candidates[0]
                if (src["path"], sig) in existing_from_signal:
                    notes.append(
                        "сигнал %s узла %s уже подключен к другому методу, а обработчик "
                        "%s в %s остался неподключённым — проверь, какой из них нужен"
                        % (sig, src["path"], handler, script_res)
                    )
                    continue
                line = '[connection signal="%s" from="%s" to="%s" method="%s"]' % (
                    sig, src["path"], node["path"], handler)
                new_lines.append(line)
                existing_methods.add(handler)
                existing_from_signal.add((src["path"], sig))
                added.append("%s: %s -> %s.%s" % (sig, src["path"], node["path"], handler))
                if (src.get("type") or "").startswith("RigidBody"):
                    notes.append(
                        "для сигнала %s у %s (RigidBody) нужны contact_monitor = true и "
                        "max_contacts_reported > 0, иначе сигнал не будет срабатывать"
                        % (sig, src["path"])
                    )
            elif len(candidates) > 1:
                variants = ", ".join("%s.%s" % (c[0]["path"], c[1]) for c in candidates[:4])
                notes.append(
                    "обработчик %s в %s нигде не подключен, но подходят несколько "
                    "источников (%s) — добавь [connection] вручную для нужного"
                    % (handler, script_res, variants)
                )
            elif suffix in custom_signals:
                notes.append(
                    "обработчик %s в %s похож на обработчик пользовательского сигнала "
                    "%s, но нигде не подключен — подключи его через connect() в коде "
                    "или [connection] в сцене" % (handler, script_res, suffix)
                )
            # ноль трактовок и не пользовательский сигнал — молчим.

    if not new_lines:
        return scene_text, [], notes
    out = text
    if not out.endswith("\n"):
        out += "\n"
    out += "\n" + "\n".join(new_lines) + "\n"
    return out, added, notes


def analyze_script_action(script_text, script_res_path, project_root):
    """Анализ СКРИПТА, который собираемся записать: если какая-то сцена на
    диске уже использует этот скрипт и в нём появился неподключённый обработчик
    с ОДНОЗНАЧНОЙ трактовкой — вернём заметки (без автоправок чужих файлов)."""
    notes = []
    handlers = extract_handlers(script_text)
    if not handlers:
        return notes
    gd_texts, scene_texts = _collect_project_files(project_root)
    # текст скрипта берём ИТОГОВЫЙ (из действия), а не с диска
    script_abs = _res_to_abs(project_root, script_res_path)
    if script_abs:
        gd_texts[os.path.normpath(script_abs)] = script_text
    needle = 'path="%s"' % script_res_path
    for scene_abs, scene_text in scene_texts.items():
        if needle not in scene_text:
            continue
        try:
            ext, nodes, connections = parse_scene(scene_text)
        except Exception:
            continue
        sid = None
        for eid, info in ext.items():
            if info.get("path") == script_res_path and info.get("type") == "Script":
                sid = eid
                break
        if sid is None:
            continue
        existing_methods = {c["method"] for c in connections}
        for node in nodes:
            if node.get("script_id") != sid:
                continue
            for handler in handlers:
                if handler in existing_methods:
                    continue
                if _method_connected_in_code(handler, gd_texts):
                    continue
                if _method_connected_in_scenes(handler, scene_texts):
                    continue
                candidates = _find_candidates(handler, nodes, node)
                if len(candidates) >= 1:
                    src, sig = candidates[0]
                    notes.append(
                        "в скрипте %s есть обработчик %s, но в сцене %s нет [connection] "
                        "для него (похоже на сигнал %s узла %s) — добавь подключение в сцену "
                        "или через connect() в _ready()"
                        % (script_res_path, handler,
                           "res://" + os.path.relpath(scene_abs, project_root).replace("\\", "/"),
                           sig, src["path"])
                    )
    return notes
