# -*- coding: utf-8 -*-
"""Индекс структуры проекта пользователя для mini-lich.

Задача: какой бы проект ни был, mini-lich быстро понимает его структуру
(файлы, узлы сцен, функции скриптов) и помогает агенту искать информацию
по проекту для отправки крупной модели — без чтения всех файлов целиком.

Индекс — компактный json в хранилище minilich, перестраивается по запросу
или если устарел. Поиск — скоринг по пересечению токенов запроса с путём
и символами файла. Это НЕ нейросеть — и не должна ею быть: для точного
поиска по структуре детерминированный индекс надёжнее и быстрее,
а сцены из индекса заодно служат сырьём для синтетического обучения.
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


def _index_path(project_root):
    return os.path.join(ml_data.storage_dir(project_root), INDEX_FILE)


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
            entry = {"path": rel, "kind": ext.lstrip("."), "symbols": []}
            if ext in (".tscn", ".gd"):
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
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
                entry["symbols"] = entry["symbols"][:60]
            entries.append(entry)
            if len(entries) >= MAX_FILES:
                break
        if len(entries) >= MAX_FILES:
            break
    data = {"built": time.time(), "root": root, "files": entries}
    path = _index_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return len(entries)


def _load_index(project_root, auto_build=True):
    try:
        with open(_index_path(project_root), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            if time.time() - float(data.get("built", 0)) < STALE_SEC:
                return data
    except Exception:
        pass
    if auto_build:
        build_index(project_root)
        return _load_index(project_root, auto_build=False)
    return {"files": []}


def _tokens(text):
    return set(t for t in re.split(r"[^a-z0-9_\u0430-\u044f\u0451]+", text.lower()) if len(t) >= 2)


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
