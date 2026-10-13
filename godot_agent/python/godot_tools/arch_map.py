# -*- coding: utf-8 -*-
"""arch_map.py — карта архитектуры агента: ядро и потребители.

Зачем. Функциональность агента живёт в ядре (python/godot_tools), а оболочки
(панель, сервер, browser, api, backends, tools) вызывают ядро. Стихийная
вторая-третья-четвёртая копия функции ломает правило: мост (agent_bridge,
режим agent-dev) перед записью НОВОГО файла агента сверяет его с картой
docs/architecture_map.json, а аудит (tools/arch_audit.py) из той же карты
делает сводку накопительных дублей.

Только чтение, ничего не пишет и не сетью не ходит:
  * load_map(addon_dir)                 — карта (кэш по mtime/размеру);
  * zone_for(map_data, rel_path)        — зона пути (первое совпадение);
  * public_names(text)                  — публичные имена верхнего уровня (.py, ast);
  * name_index(addon_dir)               — индекс «имя -> [(файл, вид)]» (кэш по слепку);
  * check_new_file / check_new_files    — вердикт: errors (отказ моста) и warnings
                                          (строки «arch:» в ответе preview/apply);
  * audit(addon_dir)                    — сводка для arch_audit.py.

Вердикты честные: карты нет или она битая — предупреждение, а не молчаливое «ок».
Глобы карты сегментные: `*` не пересекает «/», `**` пересекает (без fnmatch —
там `*.gd` зацепил бы и вложенные каталоги).

Чистота проекта: карта задаёт лимиты размера файлов (`limits.line_warn` /
`line_max`) и зоны размещения (какой файл куда кладётся). Новый файл сверх
лимита — отказ гейта, близкий к лимиту — предупреждение «arch:»; audit()
дополнительно перечисляет накопленные крупные файлы.
"""

import ast
import json
import os
import re

# Каталоги, которые никогда не участвуют в индексе имён и в обходе дерева.
_SKIP_DIRS = {"__pycache__", "dist", "minilich_brain", "parser_corpus",
              ".godot", "agent_api_cache", ".git"}

_MAP_CACHE = {}
_INDEX_CACHE = {"sig": None, "index": None}

# Чистота проекта: лимиты размера файлов по умолчанию (переопределяет limits карты).
_DEFAULT_LINE_LIMITS = {"line_warn": 1500, "line_max": 2000,
                        "line_exts": [".py", ".gd"],
                        "line_exempt_roles": ["workflow", "generated",
                                              "tasks", "reports"]}


def _glob_to_re(pattern):
    """Переводит сегментный glob карты в регулярное выражение.

    `**` — любая глубина (включая «/»), `*` — в пределах сегмента, `?` — один
    символ сегмента. Ведущее `**/` допускает и нулевую глубину.
    """
    out = ["^"]
    index, length = 0, len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if index + 1 < length and pattern[index + 1] == "*":
                if index + 2 < length and pattern[index + 2] == "/":
                    out.append("(?:.*/)?")
                    index += 3
                    continue
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    out.append("$")
    return re.compile("".join(out))


def load_map(addon_dir):
    """Карта архитектуры из <addon>/docs/architecture_map.json или None.

    Кэш — по (путь, mtime, размер): правка карты подхватывается сразу, без
    перезапуска моста. Битый JSON = None (вызывающий обязан предупредить).
    """
    path = os.path.join(str(addon_dir), "docs", "architecture_map.json")
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(os.path.realpath(path)), stat.st_mtime_ns,
           stat.st_size)
    cached = _MAP_CACHE.get("key")
    if cached == key and _MAP_CACHE.get("data") is not None:
        return _MAP_CACHE["data"]
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("zones"), list):
        return None
    compiled = []
    for zone in data["zones"]:
        if not isinstance(zone, dict):
            continue
        pattern = str(zone.get("glob") or "").strip()
        if pattern:
            compiled.append((_glob_to_re(pattern), zone))
    data["_compiled"] = compiled
    _MAP_CACHE["key"] = key
    _MAP_CACHE["data"] = data
    return data


def zone_for(map_data, rel_path):
    """Зона карты для пути (относительно аддона, через «/») или None."""
    if not map_data:
        return None
    value = str(rel_path or "").replace("\\", "/").lstrip("/")
    for regex, zone in map_data.get("_compiled") or []:
        if regex.match(value):
            return zone
    return None


def core_dir_of(map_data):
    """Каталог ядра из карты (с завершающим «/»), по умолчанию godot_tools."""
    value = str((map_data or {}).get("core_dir") or "python/godot_tools")
    return value.strip("/").replace("\\", "/") + "/"


def line_policy(map_data):
    """Лимиты размера файла из карты (`limits`) с безопасными значениями.

    Возвращает {"warn": int, "max": int, "exts": [".py", ...],
    "exempt_roles": [...]}. Битые значения и отсутствие карты — дефолт:
    предупреждение 1500 строк, лимит 2000, .py/.gd, генерируемые зоны не
    считаем (их размер диктует экспортёр, а не автор кода).
    """
    limits = (map_data or {}).get("limits")
    limits = limits if isinstance(limits, dict) else {}

    def _int(key, fallback):
        try:
            value = int(limits.get(key))
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    warn = _int("line_warn", _DEFAULT_LINE_LIMITS["line_warn"])
    maximum = _int("line_max", _DEFAULT_LINE_LIMITS["line_max"])
    if maximum < warn:
        maximum = warn
    exts = limits.get("line_exts")
    exts = [str(item).lower() for item in exts
            if str(item).strip().startswith(".")] \
        if isinstance(exts, list) else []
    if not exts:
        exts = list(_DEFAULT_LINE_LIMITS["line_exts"])
    roles = limits.get("line_exempt_roles")
    roles = [str(item) for item in roles if str(item).strip()] \
        if isinstance(roles, list) else list(_DEFAULT_LINE_LIMITS["line_exempt_roles"])
    return {"warn": warn, "max": maximum, "exts": exts,
            "exempt_roles": roles}


def count_lines(text):
    """Число строк текста (пустой текст — 0)."""
    if not text:
        return 0
    return len(str(text).splitlines())


def name_checks_enabled(map_data, rel_path):
    """Зона может отключить сверку имён (`check_names: false`).

    Тесты, скрипты n8n и per-site парсеры держат одноимённые локальные
    помощники (`Driver`, `extract_answer`, `load_invoker`) — это норма их
    жанра, а не дубль функциональности ядра.
    """
    zone = zone_for(map_data, rel_path) or {}
    return str(zone.get("check_names", True)).lower() != "false"


def public_names(text):
    """Публичные имена верхнего уровня .py-текста или None (не разобрался).

    Возвращает [(имя, "def"|"class")]: приватные (`_…`) пропускаются — это
    локальная кухня файла, у ядра она не крадёт имя.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            names.append((node.name, kind))
    return names


def _source_signature(addon_dir, exts):
    """Слепок файлов аддона с расширениями exts (путь, mtime, размер)."""
    exts = tuple(str(item).lower() for item in exts)
    entries = []
    for root, dirs, files in os.walk(str(addon_dir)):
        dirs[:] = [item for item in dirs
                   if item not in _SKIP_DIRS and not item.startswith(".")]
        for name in files:
            if not name.lower().endswith(exts):
                continue
            full = os.path.join(root, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, addon_dir).replace("\\", "/")
            entries.append((rel, stat.st_mtime_ns, stat.st_size))
    entries.sort()
    return tuple(entries)


def _py_signature(addon_dir):
    """Слепок всех .py аддона (относительный путь, mtime, размер) — для кэша."""
    return _source_signature(addon_dir, (".py",))


def name_index(addon_dir):
    """Индекс «публичное имя -> [(относительный путь, "def"|"class")]».

    Пересобирается только когда слепок каталога изменился: гейт вызывается и
    на preview, и на apply, а дерево между ними обычно не меняется.
    """
    signature = _py_signature(addon_dir)
    if _INDEX_CACHE.get("sig") == signature:
        return _INDEX_CACHE["index"]
    index = {}
    for rel, _mtime, _size in signature:
        try:
            with open(os.path.join(addon_dir, rel), "r",
                      encoding="utf-8-sig") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        names = public_names(text)
        if not names:
            continue
        for name, kind in names:
            index.setdefault(name, []).append((rel, kind))
    _INDEX_CACHE["sig"] = signature
    _INDEX_CACHE["index"] = index
    return index


def _join_hits(hits, limit=3):
    """«файл(а), файл(б)» — короткая и честная ссылка на источники имени."""
    files = sorted({rel for rel, _kind in hits})
    shown = ", ".join(files[:limit])
    if len(files) > limit:
        shown += ", …"
    return shown


def check_new_file(addon_dir, rel_path, text, map_data=None, index=None):
    """Вердикт для ОДНОГО нового файла агента: (errors, warnings).

    errors — отказ моста (имя из ядра или зона deny);
    warnings — предупреждения «arch:» (зона-потребитель, соседи по имени, зона
    вне карты). Не-.py файлы проверяются только по зоне.
    """
    value = str(rel_path or "").replace("\\", "/").lstrip("/")
    errors, warnings = [], []
    if map_data is None:
        map_data = load_map(addon_dir)
    if map_data is None:
        warnings.append("%s: карта архитектуры не найдена "
                        "(docs/architecture_map.json) — гейт пропущен" % value)
        return errors, warnings
    zone = zone_for(map_data, value) or {}
    role = str(zone.get("role") or "unknown")
    new_files = str(zone.get("new_files") or "warn").lower()
    hint = str(zone.get("hint") or "").strip()
    suffix = (" — %s" % hint) if hint else ""
    if new_files == "deny":
        errors.append("%s: зона %s (%s) — только генерируемые файлы%s"
                      % (value, zone.get("glob") or "?", role, suffix))
        return errors, warnings
    policy = line_policy(map_data)
    extension = os.path.splitext(value)[1].lower()
    if extension in policy["exts"] and role not in policy["exempt_roles"]:
        lines = count_lines(text)
        if lines > policy["max"]:
            errors.append(
                "%s: %d строк — больше лимита %d строк на файл (чистота проекта, "
                "docs/ARCHITECTURE.md): раздели функциональность на модули ядра "
                "(%s), каждый — со своим тестом"
                % (value, lines, policy["max"],
                   core_dir_of(map_data).rstrip("/")))
        elif lines >= policy["warn"]:
            warnings.append(
                "%s: %d строк — близко к лимиту %d строк на файл: планируй "
                "разделение на модули ядра" % (value, lines, policy["max"]))
    if not value.lower().endswith(".py"):
        if new_files == "warn":
            warnings.append("%s: зона %s (%s)%s" % (value, zone.get("glob") or "?",
                                                     role, suffix))
        return errors, warnings
    if not name_checks_enabled(map_data, value):
        if new_files == "warn":
            warnings.append(
                "%s: зона %s (%s)%s — новая функциональность живёт в ядре (%s)"
                % (value, zone.get("glob") or "?", role, suffix,
                   core_dir_of(map_data).rstrip("/")))
        return errors, warnings
    names = public_names(text)
    if names is None:
        warnings.append("%s: файл не разобран как Python — имена не проверены"
                        % value)
        return errors, warnings
    stoplist = set(map_data.get("name_stoplist") or [])
    core_dir = core_dir_of(map_data)
    in_core = value.startswith(core_dir)
    if index is None:
        index = name_index(addon_dir)
    for name, kind in names:
        if name in stoplist:
            continue
        hits = [(rel, k) for rel, k in (index.get(name) or [])
                if name_checks_enabled(map_data, rel)]
        core_hits = [(rel, k) for rel, k in hits if rel.startswith(core_dir)]
        if core_hits:
            where = _join_hits(core_hits)
            if in_core and all(rel == value for rel, _k in core_hits):
                continue  # имя уже в этом же файле (apply повторяет preview)
            errors.append(
                "дубль из ядра: %s %s уже определён в ядре (%s). "
                "Функциональность одна: вызови ядро из своей сферы, а не копию. "
                "Если это осознанное исключение — расширь name_stoplist карты "
                "в том же коммите" % (kind, name, where))
            continue
        other_hits = [(rel, k) for rel, k in hits if rel != value]
        if other_hits:
            warnings.append(
                "имя %s %s уже встречается: %s — если это та же "
                "функциональность, общая часть должна жить в ядре (%s)"
                % (kind, name, _join_hits(other_hits), core_dir.rstrip("/")))
    if new_files == "warn" and not errors:
        warnings.append(
            "%s: зона %s (%s)%s. Новая функциональность живёт в ядре (%s); "
            "здесь — только тонкая проводка"
            % (value, zone.get("glob") or "?", role, suffix,
               core_dir.rstrip("/")))
    return errors, warnings


def check_new_files(addon_dir, items, map_data=None):
    """Пакетная проверка: items = [(rel_path, text)] -> (errors, warnings, checked).

    Индекс имён и карта читаются один раз на пакет — гейту моста важно не
    сканировать дерево повторно для каждого файла транзакции.
    """
    if map_data is None:
        map_data = load_map(addon_dir)
    index = name_index(addon_dir) if map_data is not None else None
    errors, warnings, checked = [], [], []
    for rel_path, text in items:
        file_errors, file_warnings = check_new_file(
            addon_dir, rel_path, text, map_data=map_data, index=index)
        checked.append(str(rel_path).replace("\\", "/").lstrip("/"))
        errors.extend(file_errors)
        warnings.extend(file_warnings)
    return errors, warnings, checked


def audit(addon_dir, map_data=None):
    """Сводка архитектуры для arch_audit.py (только чтение).

    Возвращает dict: core_duplicates (имя есть и в ядре, и вне ядра),
    consumer_duplicates (одно имя у двух и более файлов вне ядра),
    unknown_files (существующие .py в зоне «unknown» карты — файл не на своём
    месте либо зона не описана), large_files (файлы от warn-лимита строк,
    over_max — сверх жёсткого лимита), line_policy (действующие лимиты), count.
    """
    if map_data is None:
        map_data = load_map(addon_dir)
    index = name_index(addon_dir)
    core_dir = core_dir_of(map_data)
    stoplist = set((map_data or {}).get("name_stoplist") or [])
    core_duplicates, consumer_duplicates, unknown_files = [], [], []
    for name in sorted(index):
        if name in stoplist:
            continue
        hits = [(rel, k) for rel, k in index[name]
                if name_checks_enabled(map_data, rel)]
        core_files = sorted({rel for rel, _k in hits if rel.startswith(core_dir)})
        other_files = sorted({rel for rel, _k in hits
                              if not rel.startswith(core_dir)})
        if core_files and other_files:
            core_duplicates.append({"name": name, "core": core_files,
                                    "outside": other_files})
        elif len(other_files) >= 2:
            consumer_duplicates.append({"name": name, "files": other_files})
    for rel, _mtime, _size in _py_signature(addon_dir):
        zone = zone_for(map_data, rel) or {}
        if str(zone.get("role") or "unknown") == "unknown":
            unknown_files.append(rel)
    policy = line_policy(map_data)
    large_files = []
    for rel, _mtime, _size in _source_signature(addon_dir, policy["exts"]):
        zone = zone_for(map_data, rel) or {}
        if str(zone.get("role") or "unknown") in policy["exempt_roles"]:
            continue
        try:
            with open(os.path.join(str(addon_dir), rel), "r",
                      encoding="utf-8-sig", errors="replace") as handle:
                lines = count_lines(handle.read())
        except OSError:
            continue
        if lines >= policy["warn"]:
            large_files.append({"rel": rel, "lines": lines,
                                "over_max": lines > policy["max"]})
    large_files.sort(key=lambda item: (-item["lines"], item["rel"]))
    return {
        "addon_dir": str(addon_dir),
        "core_dir": core_dir.rstrip("/"),
        "count": len(index),
        "core_duplicates": core_duplicates,
        "consumer_duplicates": consumer_duplicates,
        "unknown_files": unknown_files,
        "large_files": large_files,
        "line_policy": {"warn": policy["warn"], "max": policy["max"],
                        "exts": list(policy["exts"]),
                        "exempt_roles": list(policy["exempt_roles"])},
    }
