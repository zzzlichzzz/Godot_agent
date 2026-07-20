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


def lint_and_fix_tscn(text, project_root=None, addon_dir=None):
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

    # --- 0.6) ссылающийся внутренний ресурс должен идти РАНЬШЕ ресурса, на
    # который он ссылается (так документирован сам формат .tscn): переставляем
    # [ext_resource]/[sub_resource] перед первым [node], не трогая узлы/коннекты.
    fixed = _reorder_resource_sections(fixed)
    # --- 0.65) поддельные uid="uid://dummy"-заглушки — убираем битый атрибут.
    fixed = _strip_invalid_uids(fixed)
    # --- 0.66) v45: узлы, чей parent объявлен позже по файлу — переставляем.
    fixed = _reorder_nodes_for_parent_order(fixed)
    # --- 0.67) v50: prop = Type.new() — конструкторы GDScript в .tscn:
    # однозначные превращаем в [sub_resource] + SubResource(...), спорные — модели.
    fixed = _convert_ctor_values(fixed, problems)
    # --- 0.68) v50: sub_resource со ссылкой на другой sub_resource должен
    # идти ПОЗЖЕ него — переставляем топологически.
    fixed = _toposort_sub_resources(fixed)

    text = fixed  # дальнейший анализ — по уже исправленному (автопочиненному) тексту

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
    known_paths = set()
    root_seen = False
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
        else:
            if parent == ".":
                full = name
            else:
                if parent not in known_paths:
                    problems.append(
                        "\u0443\u0437\u0435\u043b \u00ab%s\u00bb: parent=\"%s\" \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0441\u0440\u0435\u0434\u0438 \u0443\u0436\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u043d\u044b\u0445 \u0432\u044b\u0448\u0435 \u0443\u0437\u043b\u043e\u0432" % (name, parent))
                full = parent + "/" + name
        if full in known_paths:
            problems.append("\u0443\u0437\u0435\u043b \u0441 \u043f\u0443\u0442\u0451\u043c \u00ab%s\u00bb \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d \u0434\u0432\u0430\u0436\u0434\u044b \u2014 \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442 \u0438\u043c\u0451\u043d" % full)
        known_paths.add(full)

        node_type = a.get("type")
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
                'пересохранении. Добавь узел-экземпляр: [node name="..." parent="." '
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
