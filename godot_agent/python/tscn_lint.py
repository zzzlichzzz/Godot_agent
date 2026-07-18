# -*- coding: utf-8 -*-
"""Структурная проверка .tscn до показа действия пользователю.

Аналог gd_lint/gd_api_check, но для сцен: ловит битые ссылки на ресурсы
(ExtResource/SubResource без объявления), недостижимые parent-пути, дублирующиеся
узлы и несуществующие типы узлов (по справочнику реального API Godot из
 gd_api_cache). load_steps в заголовке сцены исправляется автоматически,
без участия модели — это чистая арифметика, а не вопрос найти смысл.
Do not scream — всё остальное (битые ссылки, несуществующие parent, дубли, чужие
типы) неоднозначно и требует решения модели — поэтому такие вещи только в
сисок проблем для самоисцеления модели, а не в автоисправление."""
import re

import gd_api_cache

_HEADER_RE = re.compile(r'\[gd_scene\b([^\]]*)\]')
_EXT_RE = re.compile(r'\[ext_resource\b([^\]]*)\]')
_SUB_RE = re.compile(r'\[sub_resource\b([^\]]*)\]')
_NODE_RE = re.compile(r'\[node\b([^\]]*)\]')
_EXTCALL_RE = re.compile(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)')
_SUBCALL_RE = re.compile(r'SubResource\(\s*"?([^")\s]+)"?\s*\)')
_ATTR_RE = re.compile(
    r'(\w+)=(?:"([^"]*)"'
    r'|(ExtResource|SubResource)\(\s*"?([^")\s]+)"?\s*\)'
    r'|(-?\d+(?:\.\d+)?))'
)


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


def lint_and_fix_tscn(text, project_root=None, addon_dir=None):
    """Главная функция. Возвращает (fixed_text, problems):
    - fixed_text — текст с автоматически исправленным load_steps (если он был
      неверным); в остальном идентичен входному.
    - problems — список строк с неоднозначными проблемами, которые должна
      исправить сама модель (пустой список — ничего не ломается).
    Функция ничего не бросает и ничего не печатает — только анализирует текст."""
    problems = []
    if "[gd_scene" not in text:
        return text, problems  # не сцена (например, .tres) — не наша забота

    fixed = text

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

    seen = set()
    uniq = []
    for p in problems:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return fixed, uniq
