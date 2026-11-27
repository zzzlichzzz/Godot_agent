"""C.8 pure pipeline: literal reference order/messages, explicit read facts.

Specification port: ba0535d4, godot_tools/tscn_lint.py:953-1315.
No IO/regex/old-module import. Scanner early exits precede later fixes;
load_steps changes fixed but deliberately do not refresh the scan text.
"""
from .semantics import _scan_scene_semantics, _scan_scene_semantics_v83, _find_resource_cycles
from python.formats import tscn_lint_syntax as fmt
from .constants import (_COLLISION_OWNER_2D, _COLLISION_OWNER_3D, _COLLISION_SHAPE_2D, _COLLISION_SHAPE_3D, _NODE_CLASSES, _VARIANT_TYPES)
from .fixes import (_convert_ctor_values, _fix_single_candidate_refs, _reorder_nodes_for_parent_order, _reorder_resource_sections, _strip_invalid_uids, _toposort_sub_resources)
from .paths import (_check_connections_and_parents, _scan_node_path_refs)
from .syntax_findings import _scan_value_balance, _scan_property_syntax
def _finish(fixed, existing_paths, instance_texts, api_classes, planned_paths):
    problems = []
    fixed = _reorder_resource_sections(fixed)
    fixed = _strip_invalid_uids(fixed)
    fixed = _reorder_nodes_for_parent_order(fixed)
    fixed = _convert_ctor_values(fixed, problems)
    fixed = _toposort_sub_resources(fixed)
    text = fixed
    problems.extend(_check_connections_and_parents(text))
    problems.extend(_scan_node_path_refs(text))
    ext_ids = set()
    sub_ids = set()
    for m in fmt.ext_finditer(text):
        a = fmt.attrs(m.group(1))
        rid = a.get('id')
        if isinstance(rid, str):
            ext_ids.add(rid)
    for m in fmt.sub_finditer(text):
        a = fmt.attrs(m.group(1))
        rid = a.get('id')
        if isinstance(rid, str):
            sub_ids.add(rid)
    refixed = _fix_single_candidate_refs(text, ext_ids, sub_ids)
    if refixed != text:
        fixed = refixed
        text = fixed
    if True:
        _planned = set()
        for _pp in planned_paths or []:
            _planned.add((_pp or '').replace('res://', '').replace('\\', '/').strip('/').lower())
        for m in fmt.ext_finditer(text):
            a = fmt.attrs(m.group(1))
            rpath = a.get('path')
            if not isinstance(rpath, str) or not rpath.startswith('res://'):
                continue
            rel = rpath[len('res://'):].replace('\\', '/').strip('/')
            if not rel:
                continue
            if rel.lower() in _planned:
                continue
            if rel in existing_paths:
                continue
            rtype = a.get('type') or '?'
            problems.append('[ext_resource path="%s"] (%s): такого файла НЕТ в проекте — Godot не откроет сцену («Missing dependencies»). СНАЧАЛА создай этот файл отдельным действием create_file (в плане поставь шаг создания файла РАНЬШЕ шага этой сцены), и только потом сцену. Либо убери объявление и все ссылки на него, если файл не нужен.' % (rpath, rtype))
    for m in fmt.sub_finditer(text):
        a = fmt.attrs(m.group(1))
        rtype = a.get('type')
        if isinstance(rtype, str) and rtype in _NODE_CLASSES:
            problems.append('[sub_resource type="%s"]: %s — это УЗЕЛ (Node), а НЕ ресурс. Godot откажется грузить сцену («Can\'t create sub resource of type \'%s\' as it\'s not a resource type»). Объяви его секцией [node name="..." type="%s" parent="..."], а [sub_resource] оставь только для ресурсов (RectangleShape2D, CircleShape2D, Theme, Animation, Material и т.п.). Для цветной заглушки-прямоугольника используй ДОЧЕРНИЙ узел ColorRect со свойствами color и offset/size.' % (rtype, rtype, rtype, rtype))
        elif isinstance(rtype, str) and rtype in _VARIANT_TYPES:
            problems.append('[sub_resource type="%s"]: %s — это ЗНАЧЕНИЕ (Variant), а НЕ ресурс. Godot откажется грузить сцену («Can\'t create sub resource of type \'%s\' as it\'s not a resource type»). Такие значения пишутся ПРЯМО в строке свойства узла, например color = Color(1, 0.85, 0.1, 1) — удали эту секцию [sub_resource] и ссылки SubResource на неё.' % (rtype, rtype, rtype))
    hm = fmt.header_search(text)
    if hm:
        head_attrs = fmt.attrs(hm.group(1))
        expected_steps = len(ext_ids) + len(sub_ids) + 1
        declared = head_attrs.get('load_steps')
        if declared is not None:
            try:
                declared_n = int(declared)
            except ValueError:
                declared_n = None
            if declared_n != expected_steps:
                fixed = fmt.load_steps_sub(lambda mm: mm.group(1) + str(expected_steps), fixed, count=1)
    ext_scene_paths = {}
    for m in fmt.ext_finditer(text):
        a = fmt.attrs(m.group(1))
        _rid = a.get('id')
        _rpath = a.get('path')
        if isinstance(_rid, str) and isinstance(_rpath, str) and fmt.is_scene_path(_rpath):
            ext_scene_paths[_rid] = _rpath
    inst_map = {}
    _scene_paths_cache = {}

    def _inst_scene_paths(res_path):
        if res_path not in _scene_paths_cache:
            got = (None, None)
            if True and isinstance(res_path, str) and res_path.startswith('res://'):
                got = fmt.scene_node_paths(instance_texts.get(res_path[len('res://'):]))
            _scene_paths_cache[res_path] = got
        return _scene_paths_cache[res_path]

    def _nearest_inst(p):
        best = None
        for ip in inst_map:
            if ip == '' or p == ip or p.startswith(ip + '/'):
                if best is None or len(ip) > len(best):
                    best = ip
        return best

    def _vanished_in_inst(p):
        ip = _nearest_inst(p)
        if ip is None:
            return None
        src = inst_map[ip]
        spaths, fuzzy = _inst_scene_paths(src)
        if spaths is None:
            return False
        rel = p if ip == '' else p[len(ip) + 1:]
        if rel in spaths:
            return False
        for fz in fuzzy:
            if rel == fz or rel.startswith(fz + '/'):
                return False
        return (src, rel)
    known_paths = set()
    root_seen = False
    type_by_path = {}
    root_name = None
    root_type = None
    for m in fmt.node_finditer(text):
        a = fmt.attrs(m.group(1))
        name = a.get('name', '?')
        parent = a.get('parent')
        if parent is None:
            if root_seen:
                problems.append('узел «%s» без parent= и это не первый узел в файле — так быть не должно' % name)
                continue
            root_seen = True
            full = name
            root_name = name
            root_type = a.get('type')
        elif parent == '.':
            full = name
        else:
            if parent not in known_paths:
                _van = _vanished_in_inst(parent)
                if _van is None:
                    problems.append('узел «%s»: parent="%s" не найден среди уже объявленных выше узлов' % (name, parent))
                elif _van:
                    problems.append('узел «%s»: parent="%s" указывает внутрь инстанса сцены %s, но узла «%s» в той сцене НЕТ — Godot выбросит этот узел с предупреждением «Parent path ... has vanished when instantiating». Проверь точное имя узла в исходной сцене (вызови list_scene).' % (name, parent, _van[0], _van[1]))
            full = parent + '/' + name
        if full in known_paths:
            problems.append('узел с путём «%s» объявлен дважды — конфликт имён' % full)
        known_paths.add(full)
        type_by_path[full] = a.get('type')
        _inst_attr = a.get('instance')
        if isinstance(_inst_attr, tuple) and _inst_attr[0] == 'ExtResource' and (_inst_attr[1] in ext_scene_paths):
            inst_map['' if parent is None else full] = ext_scene_paths[_inst_attr[1]]
        if _inst_attr is None and a.get('type') is None and (parent is not None) and (a.get('instance_placeholder') is None):
            _van = _vanished_in_inst(full)
            if _van is None:
                problems.append('узел «%s»: нет ни type=, ни instance=, и среди предков нет инстанса сцены — Godot не сможет создать такой узел. Добавь type="..." (новый узел) или instance=ExtResource("...") (экземпляр сцены).' % name)
            elif _van:
                problems.append('узел «%s» (без type=) — это правка узла ВНУТРИ инстанса сцены %s, но узла «%s» в той сцене НЕТ. Godot молча выбросит его вместе со всеми детьми: предупреждение «Node ... was modified from inside an instance, but it has vanished». Проверь точное имя узла в исходной сцене (вызови list_scene) или добавь type="...", чтобы объявить НОВЫЙ узел.' % (name, _van[0], _van[1]))
        node_type = a.get('type')
        _shape_owner = None
        if node_type in _COLLISION_SHAPE_2D:
            _shape_owner = _COLLISION_OWNER_2D
        elif node_type in _COLLISION_SHAPE_3D:
            _shape_owner = _COLLISION_OWNER_3D
        if _shape_owner is not None:
            if parent is None:
                problems.append('узел «%s» (%s) — корень сцены: у формы коллизии нет родителя-физического тела, коллизия работать НЕ будет. Сделай корнем физическое тело или перенеси форму под него.' % (name, node_type))
            else:
                _pt = root_type if parent == '.' else type_by_path.get(parent)
                if _pt is not None and _pt not in _shape_owner:
                    _pn = root_name if parent == '.' else parent
                    problems.append('узел «%s» (%s): родитель «%s» имеет тип %s — это не физическое тело/область (нужен Area2D, StaticBody2D, CharacterBody2D, RigidBody2D, Area3D и т.п.). Коллизия работать НЕ будет: Godot помечает такой узел предупреждением «only serves to provide a collision shape to a CollisionObject». Перенеси узел под нужное физическое тело (например parent="Player").' % (name, node_type, _pn, _pt))
        if node_type and True:
            try:
                if bool(api_classes) and (not api_classes.get(node_type)):
                    problems.append('узел «%s»: type="%s" не найден в справочнике реального API Godot (опечатка или несуществующий класс)' % (name, node_type))
            except Exception:
                pass
    for m in fmt.extcall_finditer(text):
        ref_id = m.group(1)
        if ref_id not in ext_ids:
            problems.append('ссылка ExtResource("%s") не соответствует ни одному объявленному [ext_resource] id' % ref_id)
    for m in fmt.subcall_finditer(text):
        ref_id = m.group(1)
        if ref_id not in sub_ids:
            problems.append('ссылка SubResource("%s") не соответствует ни одному объявленному [sub_resource] id' % ref_id)
    used_ext = set((m.group(1) for m in fmt.extcall_finditer(text)))
    used_sub = set((m.group(1) for m in fmt.subcall_finditer(text)))
    for m in fmt.ext_finditer(text):
        a = fmt.attrs(m.group(1))
        rid = a.get('id')
        if not isinstance(rid, str) or rid in used_ext:
            continue
        rtype = a.get('type') or '?'
        rpath = a.get('path') or '?'
        if rtype == 'PackedScene':
            problems.append('[ext_resource id="%s"] (PackedScene, %s) объявлен, но НЕ используется ни одним узлом — эта сцена НЕ появится на экране, а Godot удалит неиспользуемое объявление при пересохранении. Добавь узел-экземпляр: [node name="..." parent="." instance=ExtResource("%s")] (без type= — тип берётся из самой сцены).' % (rid, rpath, rid))
        else:
            problems.append('[ext_resource id="%s"] (%s, %s) объявлен, но нигде не используется через ExtResource("%s") — Godot удалит его при пересохранении сцены. Сошлись на него в свойстве узла или убери объявление.' % (rid, rtype, rpath, rid))
    for m in fmt.sub_finditer(text):
        a = fmt.attrs(m.group(1))
        rid = a.get('id')
        if not isinstance(rid, str) or rid in used_sub:
            continue
        problems.append('[sub_resource id="%s"] объявлен, но нигде не используется через SubResource("%s") — Godot удалит его при пересохранении сцены. Сошлись на него в свойстве узла/ресурса или убери объявление.' % (rid, rid))
    for i, line in enumerate(text.split('\n')):
        if fmt.section_start_match(line):
            continue
        dm = fmt.dotted_prop_match(line)
        if dm:
            problems.append('строка %d: «%s» — свойств «через точку» в формате .tscn НЕ существует, Godot молча удалит эту строку при пересохранении. Задай свойство ВНУТРИ секции соответствующего [sub_resource] (например size = Vector2(60, 60) внутри [sub_resource type="PlaneMesh" ...]) и сошлись на него через SubResource(...).' % (i + 1, dm.group(1)))
    seen = set()
    uniq = []
    for p in problems:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return (fixed, uniq)


def prepare(text):
    problems = []
    if not fmt.has_scene_marker(text):
        return text, problems, False
    out = []
    for number, kind, raw, candidate, header in fmt.header_candidates(text):
        if kind == 'closing':
            continue
        if kind in ('angle', 'append'):
            out.append(candidate)
        else:
            if kind == 'odd':
                problems.append("строка %d: заголовок секции «%s» не закрыт «]» на своей строке — Godot откажется открыть такой файл с ошибкой «Unexpected end of file». Заверши заголовок символом «]» на той же строке." % (number, header))
            out.append(raw)
    fixed = "\n".join(out)
    if problems:
        return fixed, problems, False
    for scan in (_scan_value_balance, _scan_property_syntax, _scan_scene_semantics,
                 _scan_scene_semantics_v83, _find_resource_cycles):
        problems.extend(scan(fixed))
    if problems:
        return fixed, problems, False
    return fixed, problems, True


def finish(prepared, content, existing_paths=(), instance_texts=None, api_classes=None, planned_paths=()):
    fixed, problems, ready = prepared
    if ready:
        fixed, problems = _finish(fixed, existing_paths, instance_texts or {}, api_classes or {}, planned_paths)
    return {'fixed': fixed, 'changed': fixed != content, 'problems': problems}


def check(content, existing_paths=(), instance_texts=None, api_classes=None, planned_paths=()):
    return finish(prepare(content), content, existing_paths, instance_texts, api_classes, planned_paths)
