# -*- coding: utf-8 -*-
"""Кэш реального API Godot (из ClassDB), присланный из редактора кнопкой
«Обновить справочник API Godot». Без этого кэша проверка в gd_api_check
просто ничего не делает (никаких ложных срабатываний — это важно).

За каждый проект кэш хранится рядом с журналом изменений проекта
(history.get_storage_dir) — это уже гарантированно доступная на запись папка.

Дополнительно поддерживается «вшитый» справоциик рядом с самим аддоном
(DEFAULT_CACHE_FILENAME): разработчик нажимает кнопку ОДИН раз у себя, эта копия
сохраняется в папке аддона и едет вместе с плагином при раздаче —
и все скачавшие плагин пользователи получают работающую проверку без своих
собственных нажатий кнопки."""
import os
import json

import history_manager as history

CACHE_FILENAME = "godot_api_cache.json"
DEFAULT_CACHE_FILENAME = "default_api_cache.json"
# Вшитый кэш кладём не прямо в папку аддона, а в эту подпапку — вместе с
# .gdignore, чтобы редактор Godot вообще не пытался сканировать/импортировать
# .json как ресурс (иначе иногда вылетает мусорная "Unknown error getting
# token" из инспектора ресурсов — сам файл при этом не ломается и агент это
# не видит и не использует эту ошибку). Сами .gd/.tscn аддона лежат выше по
# дереву и .gdignore их не касается — сканируются как обычно.
DEFAULT_CACHE_SUBDIR = "agent_api_cache"

_cache = {"root": None, "classes": {}, "godot_version": ""}


def _migrate_legacy_addon_cache(addon_dir):
    """Одноразовая миграция старого вшитого кэша (лежавшего прямо в addon_dir
    без .gdignore в старых версиях аддона) в защищённое место. Вызывается при
    КАЖДОМ чтении кэша (а не только при save_cache), потому что плагин пропускает
    переотправку справочника на сервер, если версия Godot не изменилась — тогда
    старый незащищённый файл без этой функции мог бы никогда не убраться."""
    if not addon_dir:
        return
    old_bpath = os.path.join(addon_dir, DEFAULT_CACHE_FILENAME)
    if not os.path.isfile(old_bpath):
        return
    try:
        bdir = os.path.join(addon_dir, DEFAULT_CACHE_SUBDIR)
        os.makedirs(bdir, exist_ok=True)
        gi = os.path.join(bdir, ".gdignore")
        if not os.path.isfile(gi):
            with open(gi, "w", encoding="utf-8") as f:
                f.write("")
        new_bpath = os.path.join(bdir, DEFAULT_CACHE_FILENAME)
        if not os.path.isfile(new_bpath):
            with open(old_bpath, "r", encoding="utf-8") as f:
                data = f.read()
            with open(new_bpath, "w", encoding="utf-8") as f:
                f.write(data)
        os.remove(old_bpath)
    except Exception:
        pass  # миграция лучше-усилие — не критична, попробуется в следующий раз


def _cache_path(project_root):
    try:
        base = history.get_storage_dir(project_root)
    except Exception:
        return None
    if not base:
        return None
    return os.path.join(base, CACHE_FILENAME)


def save_cache(project_root, classes, godot_version="", addon_dir=None):
    """Сохраняет словарь классов (от экспортёра ClassDB в Godot) на диск
    и в памяти. Возвращает количество сохранённых классов.

    Если задан addon_dir — дополнительно кладёт резервную копию рядом
    с аддоном — именно она едет вместе с плагином при раздаче и даёт
    работающий кэш всем скачавшим плагин пользователям без их собственных
    нажатий кнопки."""
    if not isinstance(classes, dict) or not classes:
        raise ValueError("Пустой или некорректный список классов.")
    path = _cache_path(project_root)
    if not path:
        raise RuntimeError("Не удалось определить путь для сохранения кэша API (проект не синхронизирован).")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"godot_version": godot_version, "classes": classes}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    if addon_dir:
        try:
            bdir = os.path.join(addon_dir, DEFAULT_CACHE_SUBDIR)
            os.makedirs(bdir, exist_ok=True)
            gi = os.path.join(bdir, ".gdignore")
            if not os.path.isfile(gi):
                with open(gi, "w", encoding="utf-8") as f:
                    f.write("")
            bpath = os.path.join(bdir, DEFAULT_CACHE_FILENAME)
            with open(bpath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            # Старая версия аддона клала файл прямо в addon_dir без .gdignore —
            # убираем его, чтобы не остался дублирующийся кэш без защиты.
            old_bpath = os.path.join(addon_dir, DEFAULT_CACHE_FILENAME)
            if os.path.isfile(old_bpath):
                try:
                    os.remove(old_bpath)
                except Exception:
                    pass
        except Exception:
            pass  # базовый кэш необязателен — основное сохранение выше уже удалось
    _cache["root"] = project_root
    _cache["classes"] = classes
    _cache["godot_version"] = godot_version
    return len(classes)


def _load_if_needed(project_root, addon_dir=None):
    _migrate_legacy_addon_cache(addon_dir)
    if _cache["root"] == project_root and _cache["classes"]:
        return
    _cache["root"] = project_root
    _cache["classes"] = {}
    _cache["godot_version"] = ""
    path = _cache_path(project_root)
    loaded = False
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cache["classes"] = data.get("classes", {}) or {}
            _cache["godot_version"] = data.get("godot_version", "")
            loaded = bool(_cache["classes"])
        except Exception:
            _cache["classes"] = {}
    if not loaded and addon_dir:
        # Своего кэша ещё нет — берём вшитый в аддон разработчиком справочник, если он есть.
        # Сначала новое (защищённое .gdignore) место, затем старое — для тех, кто
        # обновился с более старой версии аддона и ещё не пересохранял справочник.
        bpath = os.path.join(addon_dir, DEFAULT_CACHE_SUBDIR, DEFAULT_CACHE_FILENAME)
        if not os.path.isfile(bpath):
            bpath = os.path.join(addon_dir, DEFAULT_CACHE_FILENAME)
        if os.path.isfile(bpath):
            try:
                with open(bpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _cache["classes"] = data.get("classes", {}) or {}
                _cache["godot_version"] = data.get("godot_version", "")
            except Exception:
                _cache["classes"] = {}


def get_cached_version(project_root, addon_dir=None):
    """Возвращает версию Godot, зашитую в активном кэше (своём или вшитом в аддон), или "" если кэша нет."""
    _load_if_needed(project_root, addon_dir)
    return _cache.get("godot_version", "") if _cache["classes"] else ""


def has_cache(project_root, addon_dir=None):
    """Есть ли вообще что-то экспортированное для этого проекта (своё или вшитое в аддон)."""
    _load_if_needed(project_root, addon_dir)
    return bool(_cache["classes"])


def get_class(project_root, class_name, addon_dir=None):
    _load_if_needed(project_root, addon_dir)
    return _cache["classes"].get(class_name)


def resolve_chain(project_root, class_name, max_depth=30, addon_dir=None):
    """[class_name, ..., корневой известный класс]. Обрывается, если дошли
    до класса, которого нет в кэше (например, собственный класс игры)."""
    _load_if_needed(project_root, addon_dir)
    chain = []
    seen = set()
    cur = class_name
    depth = 0
    while cur and cur not in seen and depth < max_depth:
        info = _cache["classes"].get(cur)
        if not info:
            break
        seen.add(cur)
        chain.append(cur)
        cur = info.get("inherits") or None
        depth += 1
    return chain


def collect_members(project_root, class_name, addon_dir=None):
    """Объединённые методы (имя -> [min_арг, max_арг]) / свойства / сигналы
    по всей цепочке наследования, начиная с class_name включительно."""
    chain = resolve_chain(project_root, class_name, 30, addon_dir)
    methods = {}
    props = set()
    signals = set()
    for c in chain:
        info = get_class(project_root, c, addon_dir=addon_dir) or {}
        for name, arity in (info.get("methods") or {}).items():
            methods.setdefault(name, arity)
        props.update(info.get("properties") or [])
        signals.update(info.get("signals") or [])
    return methods, props, signals
