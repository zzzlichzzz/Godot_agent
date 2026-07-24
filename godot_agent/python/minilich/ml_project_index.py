# -*- coding: utf-8 -*-
"""Индекс структуры проекта пользователя для mini-lich и Библиотекаря (v105).

Задача: какой бы проект ни был, агент быстро понимает его структуру
(файлы, узлы сцен, функции скриптов) и помогает искать информацию
по проекту для отправки крупной модели — без чтения всех файлов целиком.

Индекс — компактный json в хранилище minilich, перестраивается по запросу
или если устарел. Поиск — скоринг по пересечению токенов запроса с путём
и символами файла. Это НЕ нейросеть — и не должна ею быть: для точного
поиска по структуре детерминированный индекс надёжнее и быстрее,
а сцены из индекса заодно служат сырьём для синтетического обучения.

v105 (Библиотекарь):
1) токены дополнительно разбиваются на подтокены по snake_case и camelCase
   (take_damage -> take_damage, take, damage; CharacterBody2D -> character,
   body2d) — запрос "damage" теперь находит take_damage;
2) update_entries() — микро-обновление индекса по списку изменённых/удалённых
   файлов БЕЗ полной пересборки: агент сам знает, что менял
   (_apply_write_step/copy_file), внешние правки приходят из diff_snapshots.
   Метка built при этом сохраняется: страховочная полная пересборка по
   STALE_SEC продолжает работать как раньше;
3) v105.7: топ-уровневые var/const/@export индексируются как символы
   (var:health, const:MAX_LEVEL) — поиск, скоринг и подсказки при опечатках
   видят имена переменных, а не только функций. Локальные переменные
   (с отступом) не индексируются — это шум.
"""
import json
import os
import re
import time

from . import ml_data

INDEX_FILE = "project_index.json"
MAX_FILES = 2000
STALE_SEC = 300  # перестроить, если индексу больше 5 минут
EXTS = {".tscn", ".gd", ".tres", ".cfg", ".md", ".txt", ".json", ".import"}
SKIP_DIRS = {".git", ".godot", ".import", "addons", ".agent_history", "__pycache__", "dist", "build"}

_NODE_RE = re.compile(r"^\[node name=\"([^\"]+)\"[^\]]*?(?:type=\"([^\"]+)\")?[^\]]*\]", re.M)
_FUNC_RE = re.compile(r"^(?:static\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_CLASS_RE = re.compile(r"^class_name\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_SIGNAL_RE = re.compile(r"^signal\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
# Только топ-уровень (без отступа): локальные var внутри функций — шум.
# (?:@[^\n]*?\s+)? покрывает @export var, @onready var, @export_range(...) var.
_VAR_RE = re.compile(r"^(?:@[^\n]*?\s+)?var\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_CONST_RE = re.compile(r"^const\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _index_path(project_root):
    return os.path.join(ml_data.storage_dir(project_root), INDEX_FILE)


def _build_entry(root, rel):
    """Одна запись индекса для файла rel (путь с «/» относительно root)."""
    full = os.path.join(root, rel.replace("/", os.sep))
    ext = os.path.splitext(rel)[1].lower()
    entry = {"path": rel, "kind": ext.lstrip("."), "symbols": []}
    if ext in (".tscn", ".gd"):
        try:
            # utf-8-sig: как read_project_file/search_project_text — иначе BOM
            # ломает ^-регулярки первой строки (терялся class_name). Багфикс v105.8.
            with open(full, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read(200000)
        except OSError:
            text = ""
        if ext == ".tscn":
            for m in _NODE_RE.finditer(text):
                sym = m.group(1) + ((":" + m.group(2)) if m.group(2) else "")
                entry["symbols"].append(sym)
        else:
            entry["symbols"] += ["class:" + m.group(1) for m in _CLASS_RE.finditer(text)]
            entry["symbols"] += ["func:" + m.group(1) for m in _FUNC_RE.finditer(text)]
            entry["symbols"] += ["signal:" + m.group(1) for m in _SIGNAL_RE.finditer(text)]
            entry["symbols"] += ["var:" + m.group(1) for m in _VAR_RE.finditer(text)]
            entry["symbols"] += ["const:" + m.group(1) for m in _CONST_RE.finditer(text)]
        entry["symbols"] = entry["symbols"][:60]
    return entry


def _save(project_root, data):
    path = _index_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def build_index(project_root):
    """Обходит проект и сохраняет компактный индекс. Возвращает число файлов."""
    root = os.path.abspath(project_root or ".")
    entries = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS or ext == ".import":
                continue
            full = os.path.join(cur, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            entries.append(_build_entry(root, rel))
            if len(entries) >= MAX_FILES:
                break
        if len(entries) >= MAX_FILES:
            break
    _save(project_root, {"built": time.time(), "root": root, "files": entries})
    return len(entries)


def _read_index_raw(project_root):
    """Читает индекс с диска БЕЗ проверки свежести (для микро-обновлений)."""
    try:
        with open(_index_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            return data
    except Exception:
        pass
    return None


def _load_index(project_root, auto_build=True):
    data = _read_index_raw(project_root)
    # Багфикс v105.8: при «мозге в папке плагина» (set_storage_base) индексы
    # всех проектов живут в ОДНОМ файле. Сверяем root: чужой индекс считаем
    # отсутствующим, иначе проект B получит карту проекта A.
    if data is not None and data.get("root") != os.path.abspath(project_root or "."):
        data = None
    if data is not None and time.time() - float(data.get("built", 0)) < STALE_SEC:
        return data
    if auto_build:
        build_index(project_root)
        return _load_index(project_root, auto_build=False)
    return data or {"files": []}


def _norm_rel(rel):
    return str(rel or "").replace("res://", "").replace("\\", "/").strip("/")


def update_entries(project_root, changed_rels=(), deleted_rels=()):
    """v105: точечное обновление индекса без полной пересборки.

    Возвращает True, если индекс существовал и был обновлён; False — если
    индекса ещё нет (он построится лениво при первом поиске, отдельно
    строить не нужно). Метка built сохраняется прежней, чтобы страховочная
    полная пересборка по STALE_SEC работала как раньше."""
    data = _read_index_raw(project_root)
    if data is None:
        return False
    root = os.path.abspath(project_root or ".")
    if data.get("root") != root:
        # Багфикс v105.8: чужой индекс (общая папка плагина) — не смешиваем
        # записи двух проектов; индекс пересоберётся лениво при первом поиске.
        return False
    by_path = {}
    for e in data.get("files", []):
        if isinstance(e, dict) and e.get("path"):
            by_path[e["path"]] = e
    for rel in deleted_rels or ():
        by_path.pop(_norm_rel(rel), None)
    for rel in changed_rels or ():
        nrel = _norm_rel(rel)
        if not nrel:
            continue
        ext = os.path.splitext(nrel)[1].lower()
        if ext not in EXTS or ext == ".import":
            continue
        if any(part in SKIP_DIRS for part in nrel.split("/")[:-1]):
            continue
        full = os.path.join(root, nrel.replace("/", os.sep))
        if os.path.isfile(full):
            if nrel not in by_path and len(by_path) >= MAX_FILES:
                continue  # потолок индекса — как в build_index
            by_path[nrel] = _build_entry(root, nrel)
        else:
            by_path.pop(nrel, None)
    data["files"] = sorted(by_path.values(), key=lambda e: e.get("path", ""))
    data["root"] = root
    _save(project_root, data)
    return True


def _tokens(text):
    """Токены + подтокены: snake_case и camelCase дополнительно разбиваются
    (take_damage -> take_damage, take, damage), чтобы запрос "damage"
    находил take_damage (v105)."""
    out = set()
    for raw in re.split(r"[^A-Za-z0-9_\u0410-\u042f\u0430-\u044f\u0401\u0451]+", str(text or "")):
        if not raw:
            continue
        low = raw.lower()
        if len(low) >= 2:
            out.add(low)
        for part in _CAMEL_RE.sub(" ", raw).replace("_", " ").split():
            pl = part.lower()
            if len(pl) >= 2:
                out.add(pl)
    return out


def search(project_root, query, limit=8):
    """Ищет файлы/символы по запросу. Возвращает список записей с score."""
    data = _load_index(project_root)
    q = _tokens(query or "")
    if not q:
        return []
    scored = []
    for e in data.get("files", []):
        hay = _tokens(e.get("path", "")) | _tokens(" ".join(e.get("symbols", [])))
        score = len(q & hay)
        # бонус за подстроку в пути
        ql = (query or "").lower()
        if ql and ql in e.get("path", "").lower():
            score += 2
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda s: (-s[0], s[1]["path"]))
    return [dict(e, score=sc) for sc, e in scored[:limit]]


def describe_for_prompt(project_root, query, limit=6):
    """Компактный текстовый блок о найденных файлах — для вставки в промпт
    большой модели. Пустая строка, если ничего не найдено."""
    hits = search(project_root, query, limit=limit)
    if not hits:
        return ""
    lines = ["[mini-lich: найдено в проекте по запросу «%s»]" % (query or "")]
    for h in hits:
        syms = ", ".join(h.get("symbols", [])[:8])
        lines.append("- res://%s%s" % (h["path"], (" (%s)" % syms) if syms else ""))
    return "\n".join(lines)
