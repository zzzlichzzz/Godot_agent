# -*- coding: utf-8 -*-
"""Структурная проверка .tscn до показа действия пользователю.

Аналог gd_lint/gd_api_check, но для сцен: ловит битые ссылки на ресурсы
(ExtResource/SubResource без объявления), недостижимые parent-пути, дублирующиеся
узлы и несуществующие типы узлов (по справочнику реального API Godot из
 gd_api_cache). load_steps в заголовке сцены и опечатка «>» вместо «]» на конце заголовка секции исправляются автоматически,
без участия модели — это чистая арифметика, а не вопрос найти смысл.
Do not scream — всё остальное (битые ссылки, несуществующие parent, дубли, чужие
типы) неоднозначно и требует решения модели — поэтому такие вещи только в
сисок проблем для самоисцеления модели, а не в автоисправление."""
import io
import os
import re

import gd_api_cache

_SECTION_START_RE = re.compile(r'^\[(gd_scene|ext_resource|sub_resource|node|resource|connection)\b')
# Строка-«закрывающий тег» вида [/sub_resource]: в формате .tscn таких НЕТ вообще —
# это типовая выдумка моделей (по аналогии с XML), из-за которой Godot падает с
# «ошибкой при синтаксическом разборе файла» / Failed loading resource.
_CLOSING_TAG_RE = re.compile(r'^\[/[A-Za-z_][A-Za-z0-9_]*\]$')
_HEADER_RE = re.compile(r'\[gd_scene\b([^\]]*)\]')
_EXT_RE = re.compile(r'\[ext_resource\b([^\]]*)\]')
_SUB_RE = re.compile(r'\[sub_resource\b([^\]]*)\]')

# Частые КЛАССЫ-УЗЛЫ, которые модели ошибочно объявляют как [sub_resource].
# Узел — не ресурс: Godot падает с «Can't create sub resource of type 'X'
# as it's not a resource type» и сцена не грузится вообще.
_NODE_CLASSES = {
    "Node", "Node2D", "Node3D", "Control", "CanvasLayer",
    "ColorRect", "TextureRect", "Label", "RichTextLabel", "Button",
    "TextureButton", "Panel", "PanelContainer", "NinePatchRect",
    "VBoxContainer", "HBoxContainer", "GridContainer", "MarginContainer",
    "CenterContainer", "ScrollContainer", "ProgressBar", "LineEdit", "TextEdit",
    "ItemList", "OptionButton", "CheckBox", "CheckButton",
    "Sprite2D", "AnimatedSprite2D", "Camera2D", "CollisionShape2D",
    "CollisionPolygon2D", "Area2D", "CharacterBody2D", "RigidBody2D",
    "StaticBody2D", "AnimatableBody2D", "AnimationPlayer", "Timer",
    "AudioStreamPlayer", "AudioStreamPlayer2D", "TileMap", "TileMapLayer",
    "Marker2D", "Path2D", "PathFollow2D", "RayCast2D", "VisibleOnScreenNotifier2D",
}

# ЗНАЧЕНИЯ (Variant-типы) — тоже НЕ ресурсы: модели пишут
# [sub_resource type="Color"] и ломают сцену точно так же, как с узлами.
_VARIANT_TYPES = {
    "Color", "Vector2", "Vector2i", "Vector3", "Vector3i", "Vector4", "Vector4i",
    "Rect2", "Rect2i", "Transform2D", "Transform3D", "Quaternion", "Basis",
    "Plane", "AABB", "String", "StringName", "NodePath", "bool", "int", "float",
    "Array", "Dictionary", "PackedByteArray", "PackedInt32Array",
    "PackedInt64Array", "PackedFloat32Array", "PackedFloat64Array",
    "PackedStringArray", "PackedVector2Array", "PackedVector3Array",
    "PackedColorArray",
}
_NODE_RE = re.compile(r'\[node\b([^\]]*)\]')
_EXTCALL_RE = re.compile(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)')
_SUBCALL_RE = re.compile(r'SubResource\(\s*"?([^")\s]+)"?\s*\)')
# v55: свойство «через точку» (mesh.size = ...) — в формате .tscn такого синтаксиса
# НЕТ вообще: Godot молча выбрасывает такую строку при пересохранении сцены.
_DOTTED_PROP_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*=')
_ATTR_RE = re.compile(
    r'(\w+)=(?:"([^"]*)"'
    r'|(ExtResource|SubResource)\(\s*"?([^")\s]+)"?\s*\)'
    r'|(-?\d+(?:\.\d+)?))'
)

# Ранг типа секции в КАНОНИЧЕСКОМ порядке файла .tscn (как его сохраняет сам
# редактор Godot): заголовок сцены, внешние ресурсы, внутренние ресурсы,
# узлы, коннекты. Официальная документация формата прямо говорит: если один
# внутренний ресурс ссылается на другой, ссылающийся ресурс должен идти в
# файле РАНЬШЕ. Модели (особенно быстрые/слабые) часто пишут [sub_resource]
# ПОСЛЕ узлов, которые на него ссылаются через SubResource(...) — Godot не
# резолвит такую ссылку. Порядок узлов друг относительно друга и коннектов —
# НЕ трогаем (это дерево сцены), переставляем только секции ресурсов.
_CHUNK_TYPE_RANK = {
    "gd_scene": 0,
    "ext_resource": 1,
    "sub_resource": 2,
    "resource": 2,
    "node": 3,
    "connection": 4,
}


def _reorder_resource_sections(text):
    """Переставляет секции [ext_resource]/[sub_resource] перед первым [node],
    сохраняя их взаимный порядок и порядок самих узлов/коннектов без изменений.
    Идемпотентно: если файл уже в каноническом порядке, текст не меняется."""
    lines = text.split("\n")
    preamble = []
    chunks = []
    current_type = None
    current_lines = None
    for line in lines:
        m = _SECTION_START_RE.match(line)
        if m:
            if current_lines is not None:
                chunks.append((current_type, current_lines))
            current_type = m.group(1)
            current_lines = [line]
        elif current_lines is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_lines is not None:
        chunks.append((current_type, current_lines))
    if not chunks:
        return text
    ranked = sorted(
        enumerate(chunks),
        key=lambda pair: (_CHUNK_TYPE_RANK.get(pair[1][0], 99), pair[0]),
    )
    new_lines = list(preamble)
    for _, (_type, chunk_lines) in ranked:
        new_lines.extend(chunk_lines)
    return "\n".join(new_lines)


# Настоящий uid Godot — это ВСЕГДА конкретная сгенерированная base32-строка
# (например uid://cecaux1sm7mo0), а не человеческое слово-заглушка. Модели
# часто пишут uid="uid://dummy"/"uid://dummy2" — Godot либо откажется
# резолвить такой uid, либо результат непредсказуем. Ссылка по uid не
# обязательна (Godot размечает ресурс по path, если uid отсутствует), так что
# самое безопасное механическое исправление — просто убрать битый атрибут.
_UID_IN_HEADER_RE = re.compile(
    r'(\[(?:gd_scene|ext_resource)\b[^\]]*)\s+uid="uid://([^"]*)"([^\]]*\])'
)
_VALID_UID_RE = re.compile(r'^[0-9a-z]{10,}$')


def _strip_invalid_uids(text):
    def repl(m):
        if _VALID_UID_RE.match(m.group(2)):
            return m.group(0)
        return m.group(1) + m.group(3)
    return _UID_IN_HEADER_RE.sub(repl, text)


def _attrs(head):
    """Атрибуты из заголовка типа '[node name="X" type="Y" parent="."]'.
    Строковые/числовые значения — как строка, ExtResource/SubResource —
    как кортеж (вид, id)."""
    out = {}
    for m in _ATTR_RE.finditer(head):
        key = m.group(1)
        if m.group(2) is not None:
            out[key] = m.group(2)
        elif m.group(3) is not None:
            out[key] = (m.group(3), m.group(4))
        elif m.group(5) is not None:
            out[key] = m.group(5)
    return out


def is_scene_path(path):
    return (path or "").lower().endswith((".tscn", ".scn"))


# v45: узлы, чей parent объявлен НИЖЕ по файлу (или порядок вперемешку) —
# частая ошибка слабых моделей. Годоту важен порядок объявления: parent
# должен идти в файле РАНЬШЕ ребёнка (тот же принцип, что и для
# ext_resource/sub_resource в _reorder_resource_sections). ��сли ��то ЧИСТО
# вопрос порядка (сам parent реально существует где-то в файле) — переставляем
# механически, без участия модели. Если parent не существует вовсе — это
# настоящая ошибка и переставлять нечего: её найдёт и вернёт модели основной
# анализ дерева узлов ниже (секция «2»).
def _reorder_nodes_for_parent_order(text):
    lines = text.split("\n")
    preamble = []
    chunks = []
    current_type = None
    current_lines = None
    for line in lines:
        m = _SECTION_START_RE.match(line)
        if m:
            if current_lines is not None:
                chunks.append((current_type, current_lines))
            current_type = m.group(1)
            current_lines = [line]
        elif current_lines is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_lines is not None:
        chunks.append((current_type, current_lines))

    node_idxs = [i for i, (t, _) in enumerate(chunks) if t == "node"]
    if len(node_idxs) < 2:
        return text  # нечего переставлять

    infos = []  # (idx, name, parent)
    for idx in node_idxs:
        head = chunks[idx][1][0]
        m = _NODE_RE.search(head)
        a = _attrs(m.group(1)) if m else {}
        infos.append((idx, a.get("name", "?"), a.get("parent")))

    root_idx = None
    full_paths = {}
    for idx, name, parent in infos:
        if parent is None:
            full_paths[idx] = name
            if root_idx is None:
                root_idx = idx
        elif parent == ".":
            full_paths[idx] = name
        else:
            full_paths[idx] = parent + "/" + name

    path_to_idx = {}
    for idx, name, parent in infos:
        path_to_idx.setdefault(full_paths[idx], idx)

    parent_of = {}
    for idx, name, parent in infos:
        if parent is None:
            parent_of[idx] = None
        elif parent == ".":
            parent_of[idx] = root_idx if (root_idx is not None and root_idx != idx) else None
        else:
            parent_of[idx] = path_to_idx.get(parent)  # None, если родитель не найден вовсе

    order = []
    emitted = set()
    remaining = list(node_idxs)
    progress = True
    while remaining and progress:
        progress = False
        next_remaining = []
        for idx in remaining:
            p = parent_of.get(idx)
            if p is None or p in emitted:
                order.append(idx)
                emitted.add(idx)
                progress = True
            else:
                next_remaining.append(idx)
        remaining = next_remaining
    order.extend(remaining)  # цикл/недостижимое — оставляем как было (не теряем данные)

    if order == node_idxs:
        return text  # уже в правильном порядке — не трогаем текст

    order_iter = iter(order)
    new_lines = list(preamble)
    for t, cl in chunks:
        if t == "node":
            new_lines.extend(chunks[next(order_iter)][1])
        else:
            new_lines.extend(cl)
    return "\n".join(new_lines)


# v45: если во всей сцене объявлен РОВНО ОДИН ext_resource/sub_resource —
# любая ссылка ExtResource("X")/SubResource("X") с чужим id однозначно (без
# каких-либо вариантов) должна указывать именно на него: чиним молча. Если
# объявлено 0 или 2+ id такого вида — цель неоднозначна, оставляем модели.
def _fix_single_candidate_refs(text, ext_ids, sub_ids):
    fixed = text
    if len(ext_ids) == 1:
        only_id = next(iter(ext_ids))
        def _fix_ext(m):
            return m.group(0) if m.group(1) == only_id else 'ExtResource("%s")' % only_id
        fixed = _EXTCALL_RE.sub(_fix_ext, fixed)
    if len(sub_ids) == 1:
        only_id = next(iter(sub_ids))
        def _fix_sub(m):
            return m.group(0) if m.group(1) == only_id else 'SubResource("%s")' % only_id
        fixed = _SUBCALL_RE.sub(_fix_sub, fixed)
    return fixed


# v50: значения вида `prop = Type.new()` — это синтаксис GDScript, в .tscn он
# невалиден: Godot падает с Parse Error и сцена не грузится вообще (случай
# пользователя: mesh = PlaneMesh.new()). Если Type — обычный ресурс и
# конструктор БЕЗ аргументов, смысл однозначен: объявляем
# [sub_resource type="Type" id="auto_..."] и подставляем SubResource("auto_...").
# Узел/Variant-значение или .new(с аргументами) — чинить вслепую нельзя,
# проблема уходит модели на решение.
_CTOR_LINE_RE = re.compile(
    r'^(\s*[A-Za-z_][A-Za-z0-9_/]*\s*=\s*)([A-Za-z_][A-Za-z0-9_]*)\.new\(\s*\)\s*$'
)
_CTOR_ARGS_RE = re.compile(
    r'^\s*[A-Za-z_][A-Za-z0-9_/]*\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.new\(\s*[^)\s]'
)


def _convert_ctor_values(text, problems):
    """Меняет `prop = Type.new()` на ссылку SubResource("auto_...") с
    автообъявлением [sub_resource]. Возвращает новый текст; спорные случаи
    дописывает в problems. Идемпотентно: после починки .new() не остаётся."""
    existing_ids = set()
    for m in _SUB_RE.finditer(text):
        a = _attrs(m.group(1))
        rid = a.get("id")
        if isinstance(rid, str):
            existing_ids.add(rid)

    lines = text.split("\n")
    new_headers = []
    counter = 0
    for i, raw_line in enumerate(lines):
        cr = "\r" if raw_line.endswith("\r") else ""
        line = raw_line[:-1] if cr else raw_line
        am = _CTOR_ARGS_RE.match(line)
        if am:
            problems.append(
                'строка «%s»: %s.new(...) с аргументами — это синтаксис GDScript, '
                'в .tscn он невалиден. Объяви [sub_resource type="%s" id="..."] '
                'с нужными свойствами отдельными строками и подставь '
                'SubResource("...").' % (line.strip(), am.group(1), am.group(1))
            )
            continue
        m = _CTOR_LINE_RE.match(line)
        if not m:
            continue
        rtype = m.group(2)
        if rtype in _NODE_CLASSES or rtype in _VARIANT_TYPES:
            problems.append(
                'строка «%s»: %s.new() — %s не ресурс (это узел или '
                'Variant-значение), в .tscn его нельзя объявить как [sub_resource]. '
                'Убери это свойство или используй дочерний узел / прямое значение.'
                % (line.strip(), rtype, rtype)
            )
            continue
        counter += 1
        rid = "auto_%s_%d" % (rtype.lower(), counter)
        while rid in existing_ids:
            counter += 1
            rid = "auto_%s_%d" % (rtype.lower(), counter)
        existing_ids.add(rid)
        lines[i] = m.group(1) + 'SubResource("%s")' % rid + cr
        new_headers.append('[sub_resource type="%s" id="%s"]' % (rtype, rid))

    if not new_headers:
        return "\n".join(lines)

    # Вставляем новые секции перед первым [node] (все ресурсы уже стоят выше
    # узлов после _reorder_resource_sections); если узлов нет — в конец файла.
    insert_at = None
    for i, line in enumerate(lines):
        sm = _SECTION_START_RE.match(line)
        if sm and sm.group(1) in ("node", "connection"):
            insert_at = i
            break
    block = []
    for header in new_headers:
        block.append(header)
        block.append("")
    if insert_at is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
    else:
        if insert_at > 0 and lines[insert_at - 1].strip():
            block.insert(0, "")
        lines[insert_at:insert_at] = block
    return "\n".join(lines)


# v50: внутренний ресурс, ссылающийся на другой внутренний ресурс, должен идти
# в файле ПОЗЖЕ него — формат .tscn резолвит ссылки только назад. Модели часто
# пишут [sub_resource] со ссылкой ВПЕРЁД (случай пользователя: Environment со
# sky = SubResource("ProceduralSky"), объявленным ниже) — Godot падает с
# «!int_resources.has(id)» и сцена не грузится вообще. Порядок — чистая
# механика: стабильная топологическая перестановка секций sub_resource,
# идемпотентная (корректный порядок не меняется). Циклы (невозможны и для
# самого Godot) оставляем как есть — данные не теряем.
def _toposort_sub_resources(text):
    lines = text.split("\n")
    preamble = []
    chunks = []
    current_type = None
    current_lines = None
    for line in lines:
        m = _SECTION_START_RE.match(line)
        if m:
            if current_lines is not None:
                chunks.append((current_type, current_lines))
            current_type = m.group(1)
            current_lines = [line]
        elif current_lines is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    if current_lines is not None:
        chunks.append((current_type, current_lines))

    sub_idxs = [i for i, (t, _) in enumerate(chunks) if t == "sub_resource"]
    if len(sub_idxs) < 2:
        return text

    id_to_idx = {}
    for idx in sub_idxs:
        m = _SUB_RE.search(chunks[idx][1][0])
        a = _attrs(m.group(1)) if m else {}
        rid = a.get("id")
        if isinstance(rid, str):
            id_to_idx.setdefault(rid, idx)

    deps = {}
    for idx in sub_idxs:
        body = "\n".join(chunks[idx][1][1:])
        found = set()
        for m in _SUBCALL_RE.finditer(body):
            target = id_to_idx.get(m.group(1))
            if target is not None and target != idx:
                found.add(target)
        deps[idx] = found

    order = []
    emitted = set()
    remaining = list(sub_idxs)
    progress = True
    while remaining and progress:
        progress = False
        next_remaining = []
        for idx in remaining:
            if deps[idx] <= emitted:
                order.append(idx)
                emitted.add(idx)
                progress = True
            else:
                next_remaining.append(idx)
        remaining = next_remaining
    order.extend(remaining)  # цикл — оставляем как было, не теряем данные

    if order == sub_idxs:
        return text  # уже в правильном порядке — текст не трогаем

    order_iter = iter(order)
    new_lines = list(preamble)
    for t, cl in chunks:
        if t == "sub_resource":
            new_lines.extend(chunks[next(order_iter)][1])
        else:
            new_lines.extend(cl)
    return "\n".join(new_lines)


# v74: formy kollizii trebuyut roditelya-fizicheskogo tela (CollisionObject),
# inache Godot pokazyvaet preduprezhdenie i kollizia ne rabotaet.
_COLLISION_SHAPE_2D = {"CollisionShape2D", "CollisionPolygon2D"}
_COLLISION_SHAPE_3D = {"CollisionShape3D", "CollisionPolygon3D"}
_COLLISION_OWNER_2D = {
    "Area2D", "StaticBody2D", "AnimatableBody2D", "CharacterBody2D",
    "RigidBody2D", "PhysicsBody2D", "PhysicalBone2D",  # v86: PhysicalBone2D наследуется от RigidBody2D
}
_COLLISION_OWNER_3D = {
    "Area3D", "StaticBody3D", "AnimatableBody3D", "CharacterBody3D",
    "RigidBody3D", "VehicleBody3D", "PhysicsBody3D", "PhysicalBone3D",  # v86: то же для 3D
}


def _scene_node_paths(disk_path):
    """v72: puti uzlov sceny na diske ('' - koren). (paths, fuzzy) ili (None, None)."""
    try:
        with io.open(disk_path, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
    except Exception:
        return None, None
    paths = set()
    fuzzy = set()
    root_seen = False
    for m in _NODE_RE.finditer(src):
        a = _attrs(m.group(1))
        name = a.get("name", "?")
        parent = a.get("parent")
        if parent is None:
            if root_seen:
                continue
            root_seen = True
            full = ""
        elif parent == ".":
            full = name
        else:
            full = parent + "/" + name
        paths.add(full)
        if a.get("instance") is not None or a.get("instance_placeholder") is not None:
            fuzzy.add(full)
    if not root_seen:
        return None, None
    return paths, fuzzy


_BRACKET_OPEN = "([{"
_BRACKET_CLOSE = ")]}"


_KNOWN_SECTION_KINDS = ("gd_scene", "gd_resource", "ext_resource", "sub_resource", "node", "resource", "connection", "editable")
_ANY_SECTION_RE = re.compile(r'^\[\s*([A-Za-z_][A-Za-z0-9_]*)')
_CONNECTION_RE = re.compile(r'^\[connection\b([^\]\n]*)\]', re.M)
_NUM_VALUE_RE = re.compile(r'^-?(?:\d|\.\d)')
_KEYWORD_VALUE_RE = re.compile(r'^(?:true|false|null|nan|inf|-inf)$')
_CTOR_VALUE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\s*\(')  # v80: tochka radi PlaneMesh.new() - ego dalee razbiraet etap 0.67


def _value_looks_parseable(value):
    """v80: значение, которое Godot сможет распарсить: число, true/false/null,
    строка в кавычках, StringName (&"..."), NodePath (^"..."), массив, словарь
    или конструктор вида Vector3(...)/SubResource(...)."""
    v = value.strip()
    if not v:
        return False
    if v[0] in '"[{(':
        return True
    if v.startswith('&"') or v.startswith('^"'):
        return True
    if _NUM_VALUE_RE.match(v):
        return True
    if _KEYWORD_VALUE_RE.match(v):
        return True
    if _CTOR_VALUE_RE.match(v):
        return True
    return False


def _scan_property_syntax(text):
    """v80: построчный синтаксис свойств (только на глубине 0, вне многострочных
    значений): пропущенный знак '=', строковое значение без кавычек, неизвестный
    заголовок секции. Чинить вслепую нельзя — только problems."""
    problems = []
    depth = 0
    in_str = False
    for i, raw_line in enumerate(text.split("\n")):
        line = raw_line.rstrip("\r")
        at_top = (depth == 0 and not in_str)
        is_header = False
        if at_top:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                m = _ANY_SECTION_RE.match(stripped)
                if m:
                    is_header = True
                    kind = m.group(1)
                    if kind not in _KNOWN_SECTION_KINDS:
                        problems.append(
                            "строка %d: неизвестный заголовок секции [%s] — в .tscn бывают только "
                            "[gd_scene], [ext_resource], [sub_resource], [node], [connection] и "
                            "[editable]. Godot упадёт с «Parse Error». Убери эту секцию или замени "
                            "на правильную." % (i + 1, kind))
            elif not stripped.startswith('"'):
                if "=" not in stripped:
                    problems.append(
                        "строка %d: нет знака '=' между именем свойства и значением («%s»). "
                        "Godot упадёт с «Parse Error» при загрузке сцены. Пиши: свойство = значение."
                        % (i + 1, stripped[:80]))
                else:
                    key, _eq, value = stripped.partition("=")
                    if key.strip() and not _value_looks_parseable(value):
                        problems.append(
                            "строка %d: значение свойства %s не в кавычках и не является числом, "
                            "true/false или конструктором вида Vector3(...): «%s». Строку пиши в "
                            "кавычках, иначе Godot упадёт с «Parse Error»."
                            % (i + 1, key.strip(), value.strip()[:80]))
        if is_header:
            continue
        j = 0
        n = len(line)
        while j < n:
            ch = line[j]
            if in_str:
                if ch == "\\":
                    j += 2
                    continue
                if ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch in _BRACKET_OPEN:
                    depth += 1
                elif ch in _BRACKET_CLOSE:
                    if depth > 0:
                        depth -= 1
            j += 1
    return problems


def _check_connections_and_parents(text):
    """v80: parent="..." у узлов и from=/to= у [connection] должны указывать на
    объявленные в этой же сцене узлы. Если в сцене есть instance= — не судим:
    часть узлов приходит из инстанс-сцены и здесь не видна."""
    problems = []
    paths = set()
    root_seen = False
    for m in _NODE_RE.finditer(text):
        a = _attrs(m.group(1))
        if a.get("instance") is not None or a.get("instance_placeholder") is not None:
            return problems
        name = a.get("name", "?")
        parent = a.get("parent")
        if parent is None:
            if root_seen:
                continue
            root_seen = True
        elif parent == ".":
            paths.add(name)
        else:
            paths.add(parent + "/" + name)
    if not root_seen:
        return problems

    def _known(p):
        return p in (".", "") or p in paths

    for m in _NODE_RE.finditer(text):
        a = _attrs(m.group(1))
        parent = a.get("parent")
        if parent is None or parent == ".":
            continue
        if not _known(parent):
            problems.append(
                '[node name="%s"]: parent="%s" — такого узла в сцене нет, Godot не сможет '
                'построить дерево. Родителя объявляй ВЫШЕ по файлу и указывай его ПУТЬ от корня '
                '(parent="." для детей корня, parent="A/B" для вложенных).'
                % (a.get("name", "?"), parent))
    for m in _CONNECTION_RE.finditer(text):
        a = _attrs(m.group(1))
        for key in ("from", "to"):
            tgt = a.get(key)
            if tgt is None or _known(tgt):
                continue
            problems.append(
                '[connection signal="%s"]: %s="%s" — такого узла в сцене нет, Godot не сможет '
                'подключить сигнал. Укажи путь существующего узла (например "." для корня).'
                % (a.get("signal", "?"), key, tgt))
    return problems


def _scan_value_balance(text):
    """v78: незакрытые скобки/кавычки в ЗНАЧЕНИЯХ свойств (не в заголовках).

    Godot валится на таком файле с «Parse Error» (resource_format_text.cpp),
    например: position = Vector3(0, 5, 0  — без закрывающей «)».
    Значения МОГУТ легально занимать несколько строк (словари/массивы в
    анимациях, встроенные скрипты со строками) — поэтому баланс считается
    сквозь строки, а ошибкой считается только значение, которое так и не
    закрылось к началу СЛЕДУЮЩЕЙ секции или к концу файла.
    Чинить вслепую нельзя (обрыв значения неоднозначен) — только в problems."""
    problems = []
    depth = 0
    in_str = False
    open_line = None
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not in_str and depth == 0 and _SECTION_START_RE.match(line):
            continue  # заголовок секции: закрытость «]» проверяет этап 0
        if (in_str or depth > 0) and _SECTION_START_RE.match(line):
            problems.append(
                "строка %d: значение свойства не закрыто (не хватает закрывающей "
                "скобки или кавычки) до начала следующей секции — Godot упадёт с "
                "«Parse Error» при загрузке сцены. Допиши недостающую «)», «]», «}» "
                "или кавычку в этом значении." % ((open_line or i),))
            depth = 0
            in_str = False
            continue
        j = 0
        n = len(line)
        while j < n:
            ch = line[j]
            if in_str:
                if ch == "\\":
                    j += 2
                    continue
                if ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    if depth == 0 and open_line is None:
                        open_line = i + 1
                    in_str = True
                elif ch in _BRACKET_OPEN:
                    if depth == 0 and open_line is None:
                        open_line = i + 1
                    depth += 1
                elif ch in _BRACKET_CLOSE:
                    depth -= 1
                    if depth < 0:
                        problems.append(
                            "строка %d: лишняя закрывающая скобка «%s» в значении "
                            "свойства — Godot упадёт с «Parse Error». Убери её или "
                            "допиши парную открывающую." % (i + 1, ch))
                        depth = 0
            j += 1
        if depth == 0 and not in_str:
            open_line = None
    if depth > 0 or in_str:
        problems.append(
            "строка %d: значение свойства не закрыто (не хватает закрывающей "
            "скобки или кавычки) до конца файла — Godot упадёт с «Parse Error» "
            "при загрузке сцены. Допиши недостающее, например "
            "position = Vector3(0, 5, 0) вместо position = Vector3(0, 5, 0."
            % ((open_line or len(lines)),))
    return problems


# --- v82: смысловые проверки, которые линтер раньше пропускал (тест-сцена
# от большой модели). Всё из списка ниже роняет загрузку сцены в самом Godot:
# 1) [node] без обязательного атрибута name;
# 2) дублирующиеся id у [ext_resource]/[sub_resource];
# 3) instance=ExtResource(...) на не-сцену (инстансить можно только .tscn/.scn);
# 4) строки вместо чисел в аргументах математических конструкторов;
# 5) число вместо ресурса в свойствах вида mesh/texture/material.
_MATH_CTORS = ("Vector2", "Vector2i", "Vector3", "Vector3i", "Vector4", "Vector4i",
               "Quaternion", "Color", "Rect2", "Rect2i", "AABB", "Plane", "Basis",
               "Transform2D", "Transform3D")
_MATH_CTOR_ARGS_RE = re.compile(r'\b(%s)\(([^()]*)\)' % "|".join(_MATH_CTORS))
_NUM_ARG_RE = re.compile(r'^-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$|^-?inf$|^nan$')
_RESOURCE_PROPS = ("mesh", "texture", "material", "material_override", "shader",
                   "environment", "sky", "font", "skeleton", "skin", "animation",
                   "sprite_frames", "stylebox", "shape", "script")
_SCENE_EXTS = (".tscn", ".scn", ".res")


def _scan_scene_semantics(text):
    problems = []
    ext_types = {}
    seen_ids = {}
    for ln, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("[node"):
            if ' name="' not in stripped:
                problems.append('строка %d: у узла нет обязательного атрибута name — Godot не загрузит сцену: «%s»' % (ln, stripped[:80]))
            m_i = re.search(r'instance=ExtResource\(\s*"?([^")\s]+)"?\s*\)', stripped)
            if m_i and m_i.group(1) in ext_types:
                rtype, rpath = ext_types[m_i.group(1)]
                if (rtype and rtype != "PackedScene") or (rpath and not rpath.lower().endswith(_SCENE_EXTS)):
                    problems.append('строка %d: instance= ссылается на ext_resource id="%s" типа %s (%s) — инстансить можно только сцену (.tscn/.scn, type="PackedScene")' % (ln, m_i.group(1), rtype or "?", rpath or "?"))
            continue
        if stripped.startswith("[ext_resource") or stripped.startswith("[sub_resource"):
            kind = "ext_resource" if stripped.startswith("[ext") else "sub_resource"
            m_id = re.search(r'\bid="([^"]+)"', stripped)
            if m_id:
                rid = m_id.group(1)
                key = (kind, rid)
                if key in seen_ids:
                    problems.append('строка %d: id="%s" у %s уже используется на строке %d — id должны быть уникальны' % (ln, rid, kind, seen_ids[key]))
                else:
                    seen_ids[key] = ln
                if kind == "ext_resource":
                    m_t = re.search(r'\btype="([^"]+)"', stripped)
                    m_p = re.search(r'\bpath="([^"]+)"', stripped)
                    ext_types[rid] = (m_t.group(1) if m_t else "", m_p.group(1) if m_p else "")
            continue
        if stripped.startswith("["):
            continue
        for m_c in _MATH_CTOR_ARGS_RE.finditer(line):
            bad = None
            for arg in (a.strip() for a in m_c.group(2).split(",") if a.strip()):
                if arg.startswith('"') or not _NUM_ARG_RE.match(arg):
                    bad = arg
                    break
            if bad is not None:
                problems.append('строка %d: в конструкторе %s(...) аргумент %s — не число' % (ln, m_c.group(1), bad[:40]))
        m_pv = re.match(r'^([A-Za-z_][\w/]*)\s*=\s*(-?\d+\.?\d*)\s*$', stripped)
        if m_pv and m_pv.group(1) in _RESOURCE_PROPS:
            problems.append('строка %d: свойство %s ожидает ресурс (SubResource(...)/ExtResource(...)), а не число %s' % (ln, m_pv.group(1), m_pv.group(2)))
    return problems


# --- v83: eshe 5 problem, kotorye nashel Gemini vo vtorom raunde stress-testa ---
_NAME_ATTR_RE_V83 = re.compile(r'\bname="([^"]*)"')
_METHOD_ATTR_RE_V83 = re.compile(r'\bmethod="([^"]*)"')
_VALID_METHOD_RE_V83 = re.compile(r'^[A-Za-z_]\w*$')
_BAD_NAME_CHARS_V83 = set('./:@%"')


def _scan_scene_semantics_v83(text):
    """v83: nedopustimye simvoly/pustoe imya uzla, sub_resource bez type=,
    nevalidnoe imya metoda v [connection] (dolzhno nachinatsya s bukvy/_)."""
    problems = []
    for ln, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("[node"):
            m_name = _NAME_ATTR_RE_V83.search(stripped)
            if m_name:
                name_val = m_name.group(1)
                if name_val == "":
                    problems.append(
                        'строка %d: у узла пустое имя (name="") — Godot не примет пустое имя узла' % ln)
                else:
                    bad = sorted(set(ch for ch in name_val if ch in _BAD_NAME_CHARS_V83))
                    if bad:
                        problems.append(
                            'строка %d: имя узла "%s" содержит недопустимые символы (%s) — имена узлов '
                            'в Godot не могут содержать . / : @ %% и кавычки' % (ln, name_val, " ".join(bad)))
            continue
        if stripped.startswith("[sub_resource"):
            if 'type="' not in stripped:
                m_id = re.search(r'\bid="([^"]+)"', stripped)
                problems.append(
                    'строка %d: [sub_resource id="%s"] объявлен без type= — Godot не поймёт, какой '
                    'ресурс создавать' % (ln, m_id.group(1) if m_id else "?"))
            continue
        if stripped.startswith("[connection"):
            m_method = _METHOD_ATTR_RE_V83.search(stripped)
            if m_method and not _VALID_METHOD_RE_V83.match(m_method.group(1)):
                problems.append(
                    'строка %d: [connection method="%s"]: недопустимое имя метода — оно должно '
                    'начинаться с буквы или "_", GDScript не примет такой идентификатор' % (ln, m_method.group(1)))
            continue
    return problems


def _find_resource_cycles(text):
    """v83: sub_resource, ssylayushiysya (napryamuyu ili cherez cep) sam na sebya
    (naprimer next_pass = SubResource svoego zhe id) -- Godot ne postroit takoy resurs."""
    edges = {}
    cur_id = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("["):
            m_sub = re.match(r'\[sub_resource\b([^\]]*)\]', stripped)
            if m_sub:
                m_id = re.search(r'\bid="([^"]+)"', stripped)
                cur_id = m_id.group(1) if m_id else None
                if cur_id is not None:
                    edges.setdefault(cur_id, [])
            else:
                cur_id = None
            continue
        if cur_id is not None:
            for m_ref in _SUBCALL_RE.finditer(line):
                edges[cur_id].append(m_ref.group(1))

    problems = []
    color = {}

    def _dfs(node, path):
        color[node] = 1
        path.append(node)
        for nxt in edges.get(node, []):
            if nxt not in edges:
                continue
            if color.get(nxt) == 1:
                idx = path.index(nxt)
                cycle = path[idx:] + [nxt]
                chain = " -> ".join('SubResource("%s")' % x for x in cycle)
                problems.append(
                    'циклическая зависимость ресурсов: %s — Godot не сможет построить такой ресурс' % chain)
            elif color.get(nxt, 0) == 0:
                _dfs(nxt, path)
        path.pop()
        color[node] = 2

    for node in list(edges.keys()):
        if color.get(node, 0) == 0:
            _dfs(node, [])
    return problems


# --- v86.3: NodePath("...") в свойствах узлов + вырожденные полигоны ---------
_NODEPATH_VAL_RE = re.compile(r'NodePath\("([^"]*)"\)')
_POLYGON_PROP_RE = re.compile(r'^polygon\s*=\s*PackedVector2Array\(([^)]*)\)\s*$')
_NEXT_SECTION_RE = re.compile(r'\n\s*\[')


def _resolve_node_path(own_segs, target):
    """Разворачивает NodePath, записанный ОТНОСИТЕЛЬНО узла own_segs (корень — []),
    в путь от корня сцены. None — путь поднялся выше корня сцены."""
    out = list(own_segs)
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not out:
                return None
            out.pop()
        else:
            out.append(part)
    return out


def _scan_node_path_refs(text):
    """v86.3: NodePath("...") в свойствах узлов должен указывать на объявленный
    в этой же сцене узел. Godot битый путь ошибкой НЕ считает (узел может
    появиться из скрипта в рантайме): сцена откроется, но на узле повиснет
    жёлтое предупреждение, а свойство (remote_path, target_node и т.п.)
    работать не будет. Заодно: полигон из <3 точек у Polygon2D/CollisionPolygon2D.
    Не судим: абсолютные пути (/root/...), %UniqueName, пустые пути и сцены
    с instance= (часть узлов приходит из другой сцены и здесь не видна)."""
    problems = []
    paths = set()
    infos = []  # (имя, тип, сегменты собственного пути, конец заголовка)
    root_seen = False
    for m in _NODE_RE.finditer(text):
        a = _attrs(m.group(1))
        if a.get("instance") is not None or a.get("instance_placeholder") is not None:
            return []
        name = a.get("name", "?")
        parent = a.get("parent")
        if parent is None:
            if root_seen:
                continue  # второй «корень» — этим занимаются другие проверки
            root_seen = True
            segs = []
        elif parent == ".":
            segs = [name]
            paths.add(name)
        else:
            segs = [pp for pp in parent.split("/") if pp] + [name]
            paths.add(parent + "/" + name)
        infos.append((name, a.get("type") or "?", segs, m.end()))
    if not root_seen:
        return []
    for name, ntype, segs, body_start in infos:
        m_next = _NEXT_SECTION_RE.search(text, body_start)
        body = text[body_start:m_next.start()] if m_next else text[body_start:]
        for m_np in _NODEPATH_VAL_RE.finditer(body):
            target = m_np.group(1)
            node_part = target.split(":", 1)[0]
            if not node_part or node_part == ".":
                continue  # пустой путь / сам узел / чистый property-путь
            if node_part.startswith("/") or "%" in node_part:
                continue  # абсолютный путь или %UniqueName — вне этой сцены
            line_start = body.rfind("\n", 0, m_np.start()) + 1
            line_end = body.find("\n", m_np.start())
            prop_line = (body[line_start:line_end] if line_end != -1 else body[line_start:]).strip()
            prop = prop_line.split("=", 1)[0].strip() or "?"
            resolved = _resolve_node_path(segs, node_part)
            if resolved is None:
                problems.append(
                    u'узел "%s" (%s): %s = NodePath("%s") — путь поднимается выше корня сцены '
                    u'(лишние «..»); такого узла внутри этой сцены быть не может. Пути NodePath '
                    u'отсчитываются от самого узла: "../Имя" — сосед, "Имя" — ребёнок.'
                    % (name, ntype, prop, target))
            elif resolved and "/".join(resolved) not in paths:
                problems.append(
                    u'узел "%s" (%s): %s = NodePath("%s") указывает на узел «%s», которого в сцене НЕТ. '
                    u'Godot откроет сцену, но повесит на узел жёлтое предупреждение, и свойство работать '
                    u'не будет. Укажи путь существующего узла (пути отсчитываются от самого узла: '
                    u'"../Имя" — сосед, "Имя" — ребёнок) либо добавь недостающий узел в сцену.'
                    % (name, ntype, prop, target, "/".join(resolved)))
        if ntype in ("Polygon2D", "CollisionPolygon2D"):
            for raw_line in body.split("\n"):
                m_poly = _POLYGON_PROP_RE.match(raw_line.strip())
                if not m_poly:
                    continue
                coords = [c for c in m_poly.group(1).split(",") if c.strip()]
                pts = len(coords) // 2
                if pts < 3:
                    problems.append(
                        u'узел "%s" (%s): polygon содержит только %d точк(и) — полигону нужно минимум '
                        u'3 точки, иначе Godot повесит предупреждение, а рисовать/сталкивать будет нечего. '
                        u'Добавь недостающие вершины или убери свойство polygon.'
                        % (name, ntype, pts))
    return problems


def lint_and_fix_tscn(text, project_root=None, addon_dir=None, planned_paths=None):
    """Главная функция. Возвращает (fixed_text, problems):
    - fixed_text — текст с автоматически исправленным load_steps (если он был
      неверным); в остальном идентичен входном��.
    - problems — список строк с неоднозначными проблемами, которые должна
      исправить сама модель (пустой список — ничего не ломается).
    Функция ничего не бросает и ничего не печатает — только анализирует текст."""
    problems = []
    if "[gd_scene" not in text:
        return text, problems  # не сцена (например, .tres) — не наша забота

    fixed = text

    # --- 0) строка заголовка секции должна закрываться «]» на той же строке ---
    # иначе регулярки ниже дотягиваются до следующей «]» где угодно ниже, и Godot
    # падает с «Unexpected end of file» при открытии такого файла.
    # Частый механический случай — «>» вместо «]» на конце заголовка: смысл
    # однозначен, чиним ЛОКАЛЬНО сами (как load_steps), не тратя обращение
    # к модели. Остальные незакрытые заголовки — в problems на решение модели.
    lines = fixed.split("\n")
    out_lines = []
    for i, raw_line in enumerate(lines):
        cr = "\r" if raw_line.endswith("\r") else ""
        line = raw_line[:-1] if cr else raw_line
        # Закрывающих тегов в .tscn НЕ СУЩЕСТВУЕТ: строки [/sub_resource], [/node] и т.п.
        # удаляем ЛОКАЛЬНО без обращения к модели — смысл однозначен, как и у load_steps.
        if _CLOSING_TAG_RE.match(line.strip()):
            continue
        if not _SECTION_START_RE.match(line):
            out_lines.append(raw_line)
            continue
        stripped = line.rstrip()
        if stripped.endswith("]"):
            out_lines.append(raw_line)
            continue
        if stripped.endswith(">") and "]" not in stripped:
            out_lines.append(stripped[:-1].rstrip() + "]" + cr)
            continue
        # v46: если заголовок просто не закрыт «]», но кавычки в нём сбалансированы
        # (типичный случай — ответ модели оборвался ровно после последнего атрибута,
        # или модель просто забыла скобку) — смысл однозначен: дозакрываем «]» сами,
        # не гоняя модель переписывать всю сцену заново. Если кавычки НЕ сбалансированы
        # (обрыв посередине строкового значения) — чинить вслепую нельзя, оставляем модели.
        if "]" not in stripped and stripped.count('"') % 2 == 0:
            out_lines.append(stripped + "]" + cr)
            continue
        problems.append(
            "строка %d: заголовок се��ц��и «%s» не закрыт «]» на своей строке — "
            "Godot откажется открыть такой файл с ошибкой «Unexpected end of file». "
            "Заверши заголовок символом «]» на той же строке." % (i + 1, stripped)
        )
        out_lines.append(raw_line)
    fixed = "\n".join(out_lines)

    if problems:
        return fixed, problems

    # --- 0.55) v78: незакрытые скобки/кавычки в значениях свойств — Godot
    # падает с «Parse Error»; чинить вслепую нельзя (обрыв значения) — модели.
    problems.extend(_scan_value_balance(fixed))
    problems.extend(_scan_property_syntax(fixed))  # v80: ves sintaksis odnim otchetom
    problems.extend(_scan_scene_semantics(fixed))  # v82: imena uzlov, dubli id, instance ne-sceny, konstruktory, resursnye svoystva
    problems.extend(_scan_scene_semantics_v83(fixed))  # v83: bad node name/empty name, sub_resource bez type, nevalidnoe imya metoda
    problems.extend(_find_resource_cycles(fixed))  # v83: ciklicheskie zavisimosti resursov
    if problems:
        return fixed, problems

    # --- 0.6) ссылающийся внутренний ресурс должен идти РАНЬШЕ ресурса, на
    # который он ссылается (так документирован сам формат .tscn): переставляем
    # [ext_resource]/[sub_resource] перед первым [node], не трогая узлы/коннекты.
    fixed = _reorder_resource_sections(fixed)
    # --- 0.65) поддельные uid="uid://dummy"-заглушки — убираем битый атрибут.
    fixed = _strip_invalid_uids(fixed)
    # --- 0.66) v45: узлы, чей parent объявлен позже по файлу — переставляем.
    fixed = _reorder_nodes_for_parent_order(fixed)
    # --- 0.67) v50: prop = Type.new() — конструкторы GDScript в .tscn:
    # однозначные превращаем в [sub_resource] + SubResource(...), ��порные — модели.
    fixed = _convert_ctor_values(fixed, problems)
    # --- 0.68) v50: sub_resource со ссылкой на другой sub_resource должен
    # идти ПОЗЖЕ него — переставляем топологически.
    fixed = _toposort_sub_resources(fixed)

    text = fixed  # дальнейший анализ — по уже исправленному (автопочиненному) тексту

    # --- v80: parent="..." i [connection] from/to dolzhny ukazyvat na obyavlennye uzly ---
    problems.extend(_check_connections_and_parents(text))
    # v86.3: NodePath("...") в свойствах должен указывать на объявленный узел
    problems.extend(_scan_node_path_refs(text))

    ext_ids = set()
    sub_ids = set()
    for m in _EXT_RE.finditer(text):
        a = _attrs(m.group(1))
        rid = a.get("id")
        if isinstance(rid, str):
            ext_ids.add(rid)
    for m in _SUB_RE.finditer(text):
        a = _attrs(m.group(1))
        rid = a.get("id")
        if isinstance(rid, str):
            sub_ids.add(rid)

    # --- 0.7) v45: единственная битая ссылка на единственный объявленный
    # ресурс такого вида — чиним однозначно, без участия модели.
    refixed = _fix_single_candidate_refs(text, ext_ids, sub_ids)
    if refixed != text:
        fixed = refixed
        text = fixed

    # --- 0.45) v78: [ext_resource] указывает на файл, которого НЕТ в проекте.
    # Типовой провал: сцена объявляет скрипт/сцену/текстуру, но сам файл никто
    # не создал — Godot не откроет такую сцену («Missing dependencies»).
    # planned_paths — пути, которые СОЗДАДУТ другие шаги того же плана
    # (action=plan): их отсутствие на диске прямо сейчас — не ошибка.
    if project_root:
        _planned = set()
        for _pp in (planned_paths or []):
            _planned.add((_pp or "").replace("res://", "").replace("\\", "/").strip("/").lower())
        for m in _EXT_RE.finditer(text):
            a = _attrs(m.group(1))
            rpath = a.get("path")
            if not isinstance(rpath, str) or not rpath.startswith("res://"):
                continue
            rel = rpath[len("res://"):].replace("\\", "/").strip("/")
            if not rel:
                continue
            if rel.lower() in _planned:
                continue
            abs_p = os.path.join(os.path.abspath(project_root), *rel.split("/"))
            if os.path.isfile(abs_p):
                continue
            rtype = a.get("type") or "?"
            problems.append(
                '[ext_resource path="%s"] (%s): такого файла НЕТ в проекте — Godot не '
                'откроет сцену («Missing dependencies»). СНАЧАЛА создай этот файл отдельным '
                'действием create_file (в плане поставь шаг создания файла РАНЬШЕ шага этой '
                'сцены), и только потом сцену. Либо убери объявление и все ссылки на него, '
                'если файл не нужен.' % (rpath, rtype))

    # --- 0.5) узлы, ошибочно объявленные как [sub_resource] ---
    for m in _SUB_RE.finditer(text):
        a = _attrs(m.group(1))
        rtype = a.get("type")
        if isinstance(rtype, str) and rtype in _NODE_CLASSES:
            problems.append(
                "[sub_resource type=\"%s\"]: %s — это УЗЕЛ (Node), а НЕ ресурс. Godot откажется "
                "грузить сцену («Can't create sub resource of type '%s' as it's not a "
                "resource type»). Объяви его секцией [node name=\"...\" type=\"%s\" "
                "parent=\"...\"], а [sub_resource] оставь только для ресурсов "
                "(RectangleShape2D, CircleShape2D, Theme, Animation, Material и т.п.). "
                "Для цветной заглушки-прямоугольника используй ДОЧЕРНИЙ узел ColorRect "
                "со свойствами color и offset/size." % (rtype, rtype, rtype, rtype))
        elif isinstance(rtype, str) and rtype in _VARIANT_TYPES:
            problems.append(
                "[sub_resource type=\"%s\"]: %s — это ЗНАЧЕНИЕ (Variant), а НЕ ресурс. "
                "Godot откажется грузить сцену («Can't create sub resource of type "
                "'%s' as it's not a resource type»). Такие значения пишутся ПРЯМО "
                "в строке свойства узла, например color = Color(1, 0.85, 0.1, 1) — "
                "удали эту секцию [sub_resource] и ссылки SubResource на неё."
                % (rtype, rtype, rtype))

    # --- 1) load_steps: механически пересчитываем и тихо исправляем ---
    hm = _HEADER_RE.search(text)
    if hm:
        head_attrs = _attrs(hm.group(1))
        expected_steps = len(ext_ids) + len(sub_ids) + 1
        declared = head_attrs.get("load_steps")
        if declared is not None:
            try:
                declared_n = int(declared)
            except ValueError:
                declared_n = None
            if declared_n != expected_steps:
                fixed = re.sub(
                    r'(\[gd_scene\b[^\]]*\bload_steps=)"?\d+"?',
                    lambda mm: mm.group(1) + str(expected_steps),
                    fixed, count=1,
                )

    # --- 2) дерево узлов: parent-пути, дубли, типы ---
    # --- v72: karta instansov: pravki uzlov i parent-puti vnutri instansa ---
    ext_scene_paths = {}
    for m in _EXT_RE.finditer(text):
        a = _attrs(m.group(1))
        _rid = a.get("id")
        _rpath = a.get("path")
        if isinstance(_rid, str) and isinstance(_rpath, str) and is_scene_path(_rpath):
            ext_scene_paths[_rid] = _rpath
    inst_map = {}
    _scene_paths_cache = {}

    def _inst_scene_paths(res_path):
        if res_path not in _scene_paths_cache:
            got = (None, None)
            if project_root and isinstance(res_path, str) and res_path.startswith("res://"):
                disk = os.path.join(project_root, *res_path[len("res://"):].split("/"))
                got = _scene_node_paths(disk)
            _scene_paths_cache[res_path] = got
        return _scene_paths_cache[res_path]

    def _nearest_inst(p):
        best = None
        for ip in inst_map:
            if ip == "" or p == ip or p.startswith(ip + "/"):
                if best is None or len(ip) > len(best):
                    best = ip
        return best

    def _vanished_in_inst(p):
        # None - net instansa-predka; False - ok ili proverit nelzya;
        # (src, rel) - uzla rel v scene src NET ('vanished').
        ip = _nearest_inst(p)
        if ip is None:
            return None
        src = inst_map[ip]
        spaths, fuzzy = _inst_scene_paths(src)
        if spaths is None:
            return False
        rel = p if ip == "" else p[len(ip) + 1:]
        if rel in spaths:
            return False
        for fz in fuzzy:
            if rel == fz or rel.startswith(fz + "/"):
                return False
        return (src, rel)

    known_paths = set()
    root_seen = False
    type_by_path = {}
    root_name = None
    root_type = None
    for m in _NODE_RE.finditer(text):
        a = _attrs(m.group(1))
        name = a.get("name", "?")
        parent = a.get("parent")
        if parent is None:
            if root_seen:
                problems.append(
                    "\u0443\u0437\u0435\u043b \u00ab%s\u00bb \u0431\u0435\u0437 parent= \u0438 \u044d\u0442\u043e \u043d\u0435 \u043f\u0435\u0440\u0432\u044b\u0439 \u0443\u0437\u0435\u043b \u0432 \u0444\u0430\u0439\u043b\u0435 \u2014 \u0442\u0430\u043a \u0431\u044b\u0442\u044c \u043d\u0435 \u0434\u043e\u043b\u0436\u043d\u043e" % name)
                continue
            root_seen = True
            full = name
            root_name = name
            root_type = a.get("type")
        else:
            if parent == ".":
                full = name
            else:
                if parent not in known_paths:
                    _van = _vanished_in_inst(parent)
                    if _van is None:
                        problems.append(
                            "\u0443\u0437\u0435\u043b \u00ab%s\u00bb: parent=\"%s\" \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0441\u0440\u0435\u0434\u0438 \u0443\u0436\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u043d\u044b\u0445 \u0432\u044b\u0448\u0435 \u0443\u0437\u043b\u043e\u0432" % (name, parent))
                    elif _van:
                        problems.append(
                            "\u0443\u0437\u0435\u043b \xab%s\xbb: parent=\"%s\" \u0443\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0432\u043d\u0443\u0442\u0440\u044c \u0438\u043d\u0441\u0442\u0430\u043d\u0441\u0430 \u0441\u0446\u0435\u043d\u044b %s, \u043d\u043e \u0443\u0437\u043b\u0430 \xab%s\xbb \u0432 \u0442\u043e\u0439 \u0441\u0446\u0435\u043d\u0435 \u041d\u0415\u0422 \u2014 Godot \u0432\u044b\u0431\u0440\u043e\u0441\u0438\u0442 \u044d\u0442\u043e\u0442 \u0443\u0437\u0435\u043b \u0441 \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435\u043c \xabParent path ... has vanished when instantiating\xbb. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0442\u043e\u0447\u043d\u043e\u0435 \u0438\u043c\u044f \u0443\u0437\u043b\u0430 \u0432 \u0438\u0441\u0445\u043e\u0434\u043d\u043e\u0439 \u0441\u0446\u0435\u043d\u0435 (\u0432\u044b\u0437\u043e\u0432\u0438 list_scene)." % (name, parent, _van[0], _van[1]))
                full = parent + "/" + name
        if full in known_paths:
            problems.append("\u0443\u0437\u0435\u043b \u0441 \u043f\u0443\u0442\u0451\u043c \u00ab%s\u00bb \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d \u0434\u0432\u0430\u0436\u0434\u044b \u2014 \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442 \u0438\u043c\u0451\u043d" % full)
        known_paths.add(full)
        type_by_path[full] = a.get("type")

        _inst_attr = a.get("instance")
        if isinstance(_inst_attr, tuple) and _inst_attr[0] == "ExtResource" and _inst_attr[1] in ext_scene_paths:
            inst_map["" if parent is None else full] = ext_scene_paths[_inst_attr[1]]
        if (_inst_attr is None and a.get("type") is None and parent is not None
                and a.get("instance_placeholder") is None):
            _van = _vanished_in_inst(full)
            if _van is None:
                problems.append("\u0443\u0437\u0435\u043b \xab%s\xbb: \u043d\u0435\u0442 \u043d\u0438 type=, \u043d\u0438 instance=, \u0438 \u0441\u0440\u0435\u0434\u0438 \u043f\u0440\u0435\u0434\u043a\u043e\u0432 \u043d\u0435\u0442 \u0438\u043d\u0441\u0442\u0430\u043d\u0441\u0430 \u0441\u0446\u0435\u043d\u044b \u2014 Godot \u043d\u0435 \u0441\u043c\u043e\u0436\u0435\u0442 \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u0442\u0430\u043a\u043e\u0439 \u0443\u0437\u0435\u043b. \u0414\u043e\u0431\u0430\u0432\u044c type=\"...\" (\u043d\u043e\u0432\u044b\u0439 \u0443\u0437\u0435\u043b) \u0438\u043b\u0438 instance=ExtResource(\"...\") (\u044d\u043a\u0437\u0435\u043c\u043f\u043b\u044f\u0440 \u0441\u0446\u0435\u043d\u044b)." % name)
            elif _van:
                problems.append("\u0443\u0437\u0435\u043b \xab%s\xbb (\u0431\u0435\u0437 type=) \u2014 \u044d\u0442\u043e \u043f\u0440\u0430\u0432\u043a\u0430 \u0443\u0437\u043b\u0430 \u0412\u041d\u0423\u0422\u0420\u0418 \u0438\u043d\u0441\u0442\u0430\u043d\u0441\u0430 \u0441\u0446\u0435\u043d\u044b %s, \u043d\u043e \u0443\u0437\u043b\u0430 \xab%s\xbb \u0432 \u0442\u043e\u0439 \u0441\u0446\u0435\u043d\u0435 \u041d\u0415\u0422. Godot \u043c\u043e\u043b\u0447\u0430 \u0432\u044b\u0431\u0440\u043e\u0441\u0438\u0442 \u0435\u0433\u043e \u0432\u043c\u0435\u0441\u0442\u0435 \u0441\u043e \u0432\u0441\u0435\u043c\u0438 \u0434\u0435\u0442\u044c\u043c\u0438: \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435 \xabNode ... was modified from inside an instance, but it has vanished\xbb. \u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0442\u043e\u0447\u043d\u043e\u0435 \u0438\u043c\u044f \u0443\u0437\u043b\u0430 \u0432 \u0438\u0441\u0445\u043e\u0434\u043d\u043e\u0439 \u0441\u0446\u0435\u043d\u0435 (\u0432\u044b\u0437\u043e\u0432\u0438 list_scene) \u0438\u043b\u0438 \u0434\u043e\u0431\u0430\u0432\u044c type=\"...\", \u0447\u0442\u043e\u0431\u044b \u043e\u0431\u044a\u044f\u0432\u0438\u0442\u044c \u041d\u041e\u0412\u042b\u0419 \u0443\u0437\u0435\u043b." % (name, _van[0], _van[1]))

        node_type = a.get("type")
        _shape_owner = None
        if node_type in _COLLISION_SHAPE_2D:
            _shape_owner = _COLLISION_OWNER_2D
        elif node_type in _COLLISION_SHAPE_3D:
            _shape_owner = _COLLISION_OWNER_3D
        if _shape_owner is not None:
            if parent is None:
                problems.append("\u0443\u0437\u0435\u043b \xab%s\xbb (%s) \u2014 \u043a\u043e\u0440\u0435\u043d\u044c \u0441\u0446\u0435\u043d\u044b: \u0443 \u0444\u043e\u0440\u043c\u044b \u043a\u043e\u043b\u043b\u0438\u0437\u0438\u0438 \u043d\u0435\u0442 \u0440\u043e\u0434\u0438\u0442\u0435\u043b\u044f-\u0444\u0438\u0437\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0442\u0435\u043b\u0430, \u043a\u043e\u043b\u043b\u0438\u0437\u0438\u044f \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u041d\u0415 \u0431\u0443\u0434\u0435\u0442. \u0421\u0434\u0435\u043b\u0430\u0439 \u043a\u043e\u0440\u043d\u0435\u043c \u0444\u0438\u0437\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0442\u0435\u043b\u043e \u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u043d\u0435\u0441\u0438 \u0444\u043e\u0440\u043c\u0443 \u043f\u043e\u0434 \u043d\u0435\u0433\u043e." % (name, node_type))
            else:
                _pt = root_type if parent == "." else type_by_path.get(parent)
                if _pt is not None and _pt not in _shape_owner:
                    _pn = root_name if parent == "." else parent
                    problems.append("\u0443\u0437\u0435\u043b \xab%s\xbb (%s): \u0440\u043e\u0434\u0438\u0442\u0435\u043b\u044c \xab%s\xbb \u0438\u043c\u0435\u0435\u0442 \u0442\u0438\u043f %s \u2014 \u044d\u0442\u043e \u043d\u0435 \u0444\u0438\u0437\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0442\u0435\u043b\u043e/\u043e\u0431\u043b\u0430\u0441\u0442\u044c (\u043d\u0443\u0436\u0435\u043d Area2D, StaticBody2D, CharacterBody2D, RigidBody2D, Area3D \u0438 \u0442.\u043f.). \u041a\u043e\u043b\u043b\u0438\u0437\u0438\u044f \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u041d\u0415 \u0431\u0443\u0434\u0435\u0442: Godot \u043f\u043e\u043c\u0435\u0447\u0430\u0435\u0442 \u0442\u0430\u043a\u043e\u0439 \u0443\u0437\u0435\u043b \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435\u043c \xabonly serves to provide a collision shape to a CollisionObject\xbb. \u041f\u0435\u0440\u0435\u043d\u0435\u0441\u0438 \u0443\u0437\u0435\u043b \u043f\u043e\u0434 \u043d\u0443\u0436\u043d\u043e\u0435 \u0444\u0438\u0437\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0442\u0435\u043b\u043e (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 parent=\"Player\")." % (name, node_type, _pn, _pt))
        if node_type and project_root:
            try:
                if gd_api_cache.has_cache(project_root, addon_dir) and not gd_api_cache.get_class(project_root, node_type, addon_dir):
                    problems.append(
                        "\u0443\u0437\u0435\u043b \u00ab%s\u00bb: type=\"%s\" \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0432 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a\u0435 \u0440\u0435\u0430\u043b\u044c\u043d\u043e\u0433\u043e API Godot (\u043e\u043f\u0435\u0447\u0430\u0442\u043a\u0430 \u0438\u043b\u0438 \u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0438\u0439 \u043a\u043b\u0430\u0441\u0441)" % (name, node_type))
            except Exception:
                pass

    # --- 3) ссылки на ExtResource/SubResource внутри узлов и ресурсов ---
    for m in _EXTCALL_RE.finditer(text):
        ref_id = m.group(1)
        if ref_id not in ext_ids:
            problems.append("\u0441\u0441\u044b\u043b\u043a\u0430 ExtResource(\"%s\") \u043d\u0435 \u0441\u043e\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u0438 \u043e\u0434\u043d\u043e\u043c\u0443 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u043d\u043e\u043c\u0443 [ext_resource] id" % ref_id)
    for m in _SUBCALL_RE.finditer(text):
        ref_id = m.group(1)
        if ref_id not in sub_ids:
            problems.append("\u0441\u0441\u044b\u043b\u043a\u0430 SubResource(\"%s\") \u043d\u0435 \u0441\u043e\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u0438 \u043e\u0434\u043d\u043e\u043c\u0443 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u043d\u043e\u043c\u0443 [sub_resource] id" % ref_id)

    # --- 4) v55: объявленный, но НЕ используемый ресурс: Godot молча выбрасывает
    # такие [ext_resource]/[sub_resource] при первом же пересохранении сцены редактором.
    # Типовой провал моделей: «добавила игрока», объявив PackedScene, но НЕ добавив
    # узел с instance=ExtResource(...) — на сцене ничего не появляется, а после
    # пересохранения пропадает и само объявление ресурса.
    used_ext = set(m.group(1) for m in _EXTCALL_RE.finditer(text))
    used_sub = set(m.group(1) for m in _SUBCALL_RE.finditer(text))
    for m in _EXT_RE.finditer(text):
        a = _attrs(m.group(1))
        rid = a.get("id")
        if not isinstance(rid, str) or rid in used_ext:
            continue
        rtype = a.get("type") or "?"
        rpath = a.get("path") or "?"
        if rtype == "PackedScene":
            problems.append(
                '[ext_resource id="%s"] (PackedScene, %s) объявлен, но НЕ используется ни одним узлом — '
                'эта сцена НЕ появится на экране, а Godot удалит неиспользуемое объявление при '
                'пересохранении. Добавь узел-экзем��ляр: [node name="..." parent="." '
                'instance=ExtResource("%s")] (без type= — тип берётся из самой сцены).'
                % (rid, rpath, rid))
        else:
            problems.append(
                '[ext_resource id="%s"] (%s, %s) объявлен, но нигде не используется через '
                'ExtResource("%s") — Godot удалит его при пересохранении сцены. '
                'Сошлись на него в свойстве узла или убери объявление.'
                % (rid, rtype, rpath, rid))
    for m in _SUB_RE.finditer(text):
        a = _attrs(m.group(1))
        rid = a.get("id")
        if not isinstance(rid, str) or rid in used_sub:
            continue
        problems.append(
            '[sub_resource id="%s"] объявлен, но нигде не используется через SubResource("%s") — '
            'Godot удалит его при пересохранении сцены. Сошлись на него в свойстве '
            'узла/ресурса или убери объявление.' % (rid, rid))

    # --- 5) v55: свойство «через точку» (mesh.size = ...) — такого синтаксиса в
    # формате .tscn НЕТ: Godot молча выбросит строку, и свойство пропадёт.
    for i, line in enumerate(text.split("\n")):
        if _SECTION_START_RE.match(line):
            continue
        dm = _DOTTED_PROP_RE.match(line)
        if dm:
            problems.append(
                'строка %d: «%s» — свойств «через точку» в формате .tscn НЕ существует, '
                'Godot молча удалит эту строку при пересохранении. Задай свойство ВНУТРИ '
                'секции соответствующего [sub_resource] (например size = Vector2(60, 60) '
                'внутри [sub_resource type="PlaneMesh" ...]) и сошлись на него через SubResource(...).'
                % (i + 1, dm.group(1)))

    seen = set()
    uniq = []
    for p in problems:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return fixed, uniq
