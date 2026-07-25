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
# v105.13 (патч производительности, п.1): было MAX_FILES = 2000 — потолок
# из времён, когда индекс строился на демо-проектах. Реальный крупный
# проект (несколько тысяч сцен и скриптов) в него не влезал, и лишние
# файлы отбрасывались МОЛЧА: агент уверенно отвечал по половине проекта.
# Новое значение выбрано замером, а не на глаз (см. tests/test_librarian.py,
# test_index_size_budget): типичный проект — ~0.2 КБ индекса на файл,
# «болтливый» (длинные вложенные пути + упор в лимит 60 символов на файл) —
# до ~3 КБ. При 12000 файлах это ~2.5 МБ на типичном проекте и ~10 МБ на
# смешанном профиле (~0.8 КБ/файл) — верхняя граница, за которой разбор
# json начинает стоить заметную долю времени ответа.
MAX_FILES = 12000
STALE_SEC = 300  # перестроить, если индексу больше 5 минут
EXTS = {".tscn", ".gd", ".tres", ".cfg", ".md", ".txt", ".json", ".import"}
SKIP_DIRS = {".git", ".godot", ".import", "addons", ".agent_history", "__pycache__", "dist", "build"}

_NODE_RE = re.compile(r"^\[node name=\"([^\"]+)\"[^\]]*?(?:type=\"([^\"]+)\")?[^\]]*\]", re.M)
# v105.10 (шаг 3): имена — юникодные. GDScript разрешает кириллицу в
# идентификаторах, а шаблон [A-Za-z_] терял «func лечить()» целиком:
# файл попадал в MAP, но без единого символа. [^\W\d]\w* = буква/_
# в начале, дальше буквы/цифры/_ (в Python 3 \w юникодный по умолчанию).
_FUNC_RE = re.compile(r"^(?:static\s+)?func\s+([^\W\d]\w*)", re.M | re.U)
_CLASS_RE = re.compile(r"^class_name\s+([^\W\d]\w*)", re.M | re.U)
_SIGNAL_RE = re.compile(r"^signal\s+([^\W\d]\w*)", re.M | re.U)
# Только топ-уровень (без отступа): локальные var внутри функций — шум.
# (?:@[^\n]*?\s+)? покрывает @export var, @onready var, @export_range(...) var.
_VAR_RE = re.compile(r"^(?:@[^\n]*?\s+)?var\s+([^\W\d]\w*)", re.M | re.U)
_CONST_RE = re.compile(r"^const\s+([^\W\d]\w*)", re.M | re.U)

# v105.12 (раунд 4, п.3): все регулярки выше — ^-якорные, поэтому члены
# вложенных классов в индекс не попадали. STRUCTURE в раунде 3 починили,
# а индекс — нет: файл с FSM-паттерном (class Idle: / class Run: внутри
# одного скрипта) давал символы только топ-уровня, и запрос «field_a Inner»
# не находил файл вообще — ответ шёл без MAP и без STRUCTURE.
_NESTED_CLASS_RE = re.compile(r"^[ \t]*class\s+([^\W\d]\w*)\s*(?:extends\s+\S+\s*)?:", re.U)
_NESTED_FUNC_RE = re.compile(r"^[ \t]+(?:static\s+)?func\s+([^\W\d]\w*)", re.U)
_NESTED_VAR_RE = re.compile(r"^[ \t]+(?:@[^\n]*?\s+)?var\s+([^\W\d]\w*)", re.U)
_NESTED_CONST_RE = re.compile(r"^[ \t]+const\s+([^\W\d]\w*)", re.U)


def _nested_symbols(text):
    """Символы вложенных классов: class Inner: и его члены.

    Голой регуляркой вида «\\s+var» это не решается: локальные var внутри тел
    функций — тоже строки с отступом, и в индекс уехал бы весь шум, от
    которого избавлялись раньше (см. комментарий к _VAR_RE). Поэтому идём
    построчно и следим за отступами (та же механика, что в
    librarian._gd_signatures): берём только члены НЕПОСРЕДСТВЕННО внутри
    class-блока и вне тел его функций.
    """
    out = []
    class_indent = None
    func_indent = None
    for line in text.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        # Порядок важен: сначала закрываем тело функции, потом блок класса,
        # и только затем распознаём объявление нового класса.
        if func_indent is not None and indent <= func_indent:
            func_indent = None
        if class_indent is not None and indent <= class_indent:
            class_indent = None
            func_indent = None
        m = _NESTED_CLASS_RE.match(line)
        if m:
            out.append("class:" + m.group(1))
            class_indent = indent
            func_indent = None
            continue
        # Топ-уровень уже разобран ^-якорными регулярками; тело функции — шум.
        if class_indent is None or func_indent is not None:
            continue
        mf = _NESTED_FUNC_RE.match(line)
        if mf:
            out.append("func:" + mf.group(1))
            func_indent = indent
            continue
        mv = _NESTED_VAR_RE.match(line)
        if mv:
            out.append("var:" + mv.group(1))
            continue
        mc = _NESTED_CONST_RE.match(line)
        if mc:
            out.append("const:" + mc.group(1))
    return out


_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# v105.13 (п.1): приоритет расширения при обрезке по MAX_FILES. Раньше
# лимит применялся в порядке os.walk (фактически почти алфавитно по
# каталогам): на проекте с большим docs/ в индекс уезжала документация,
# а скрипты из src/, идущие позже, выпадали — то есть терялось ровно то,
# ради чего индекс и существует. Теперь порядок обхода решает только
# внутри одного приоритета: 0 — код и сцены, 1 — ресурсы/конфиги и всё
# незнакомое, 2 — текст и да��ные (их всегда много, а пользы для поиска
# по структуре меньше всего).
_EXT_PRIORITY = {
    ".gd": 0, ".tscn": 0,
    ".tres": 1, ".cfg": 1, ".import": 1,
    ".md": 2, ".txt": 2, ".json": 2,
}


def _ext_priority(rel):
    """Приоритет файла при обрезке индекса: меньше — важнее (0..2)."""
    ext = os.path.splitext(str(rel or ""))[1].lower()
    return _EXT_PRIORITY.get(ext, 1)


# v105.13 (п.2): кэш распарсенного индекса в памяти процесса.
# Было: _read_index_raw() читал и разбирал json НА КАЖДЫЙ вызов —
# и на search(), и на update_entries(), и на каждый слой ответа
# Библиотекаря. На индексе в 2000 файлов это доли миллисекунды, но после
# п.1 индекс вырастает до мегабайтов, и разбор становится заметной частью
# времени ответа — при том, что между вызовами файл обычно не менялся.
# Ключ — abs_root (как и везде в модуле: при «мозге в папке плагина»
# индексы разных проектов живут в одном файле, путать их нельзя).
# Инвалидация — по (mtime, size) файла индекса: если его переписал кто-то
# другой, отпечаток не совпадёт и данные перечитаются. size добавлен к
# mtime не из паранойи: на Windows/FAT гранулярность mtime грубая, и две
# записи подряд могут получить одинаковую метку.
_MEM_CACHE = {}  # abs_root -> {"stamp": (mtime, size), "data": dict}


def _cache_key(project_root):
    return os.path.abspath(project_root or ".")


def _index_stamp(path):
    """Отпечаток файла индекса (mtime, size) или None, если файла нет.
    Ввод-вывод обёрнут, как и весь остальной в модуле: отсутствие индекса —
    штатная ситуация, а не ошибка."""
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _cache_store(project_root, data):
    """Положить только что сохранённые данные в кэш вместе со свежим
    отпечатком файла — чтобы следующий локальный вызов не читал диск."""
    try:
        stamp = _index_stamp(_index_path(project_root))
        if stamp is not None:
            _MEM_CACHE[_cache_key(project_root)] = {"stamp": stamp, "data": data}
    except Exception:
        _MEM_CACHE.pop(_cache_key(project_root), None)  # лучше без кэша, чем с враньём


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
            # v105.12 (раунд 4, п.3): члены вложенных классов (FSM-паттерн).
            entry["symbols"] += _nested_symbols(text)
            # Порядок сохраняем, дубли убираем: имя метода вложенного
            # класса может совпасть с уже взятым с топ-уровня.
            _seen_syms = set()
            _uniq = []
            for s in entry["symbols"]:
                if s in _seen_syms:
                    continue
                _seen_syms.add(s)
                _uniq.append(s)
            entry["symbols"] = _uniq
        entry["symbols"] = entry["symbols"][:60]
    return entry


def _save(project_root, data):
    path = _index_path(project_root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    # v105.13 (п.2): оба писателя индекса (build_index и update_entries)
    # ходят через _save, поэтому кэш обновляем здесь — так невозможно
    # забыть его в новом месте записи и отдать следующему вызову старьё.
    _cache_store(project_root, data)


def build_index(project_root):
    """Обходит проект и сохраняет компактный индекс. Возвращает число файлов."""
    root = os.path.abspath(project_root or ".")
    # v105.13 (п.1): раньше обход ПРЕРЫВАЛСЯ по MAX_FILES, и решение,
    # какой файл важен, принимал порядок каталогов на диске. Сначала
    # собираем все пути (только строки, парсинга ещё нет — дёшево),
    # потом выбираем лучшие по приоритету и только затем читаем файлы.
    rels = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS or ext == ".import":
                continue
            full = os.path.join(cur, fn)
            rels.append(os.path.relpath(full, root).replace(os.sep, "/"))
    skipped = 0
    if len(rels) > MAX_FILES:
        skipped = len(rels) - MAX_FILES
        # Сортировка только ДЛЯ ОТБОРА: ключ (приоритет, номер в обходе),
        # потом выжившие возвращаются в исходный порядок обхода.
        # Это важно для совместимости: пока лимит не сработал, содержимое
        # и порядок files байт-в-байт такие же, как до патча.
        order = sorted(range(len(rels)), key=lambda i: (_ext_priority(rels[i]), i))
        rels = [rels[i] for i in sorted(order[:MAX_FILES])]
    entries = [_build_entry(root, rel) for rel in rels]
    data = {"built": time.time(), "root": root, "files": entries}
    if skipped:
        # Индекс — единственное место, где факт усечения известен. Ключи
        # добавляются ТОЛЬКО при усечении: на обычном проекте формат
        # файла индекса не меняется вообще.
        data["truncated"] = True
        data["skipped_files"] = skipped
    _save(project_root, data)
    return len(entries)


def _read_index_raw(project_root):
    """Читает индекс БЕЗ проверки свежести (для микро-обновлений).

    v105.13 (п.2): источник данных — сначала кэш в памяти, и только при
    промахе — диск. Сами данные не меняются ни на байт: это тот же dict,
    который вернул бы json.load, просто без повторного разбора."""
    path = _index_path(project_root)
    stamp = _index_stamp(path)
    key = _cache_key(project_root)
    if stamp is not None:
        cached = _MEM_CACHE.get(key)
        if cached is not None and cached.get("stamp") == stamp:
            return cached.get("data")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            if stamp is not None:
                _MEM_CACHE[key] = {"stamp": stamp, "data": data}
            return data
    except Exception:
        pass
    # Битый/отсутствующий индекс — кэшировать нечего; чистим запись,
    # чтобы не отдать её позже по совпавшему отпечатку.
    _MEM_CACHE.pop(key, None)
    return None


def index_meta(project_root):
    """v105.13 (п.1): служебные поля индекса для вызывающего кода
    (Библиотекарь) — без доступа к внутренним _-функциям модуля.
    Возвращает {"truncated": bool, "skipped_files": int}; если индекса нет
    или он от ДРУГОГО проекта («мозг в папке плагина») — пустое
    состояние, чтобы не предупреждать об усечении чужого индекса.
    Чтение идёт через кэш (п.2), то есть лишнего разбора json нет."""
    try:
        data = _read_index_raw(project_root)
        if not isinstance(data, dict):
            return {"truncated": False, "skipped_files": 0}
        if data.get("root") != os.path.abspath(project_root or "."):
            return {"truncated": False, "skipped_files": 0}
        return {"truncated": bool(data.get("truncated")),
                "skipped_files": int(data.get("skipped_files") or 0)}
    except Exception:
        return {"truncated": False, "skipped_files": 0}


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
    skipped_now = 0
    # v105.13 (п.1): тот же приоритет, что и в build_index. Раньше при упоре
    # в потолок выигрывал тот, кто раньше оказался в списке изменённых,
    # то есть случайность: новый .md мог занять последний слот и вытеснить
    # новый скрипт. Сортировка устойчивая и влияет только на порядок
    # ОБРАБОТКИ: итоговый files всё равно сортируется по path ниже.
    for rel in sorted(changed_rels or (), key=lambda r: _ext_priority(_norm_rel(r))):
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
                skipped_now += 1
                continue  # потолок индекса — как в build_index
            by_path[nrel] = _build_entry(root, nrel)
        else:
            by_path.pop(nrel, None)
    data["files"] = sorted(by_path.values(), key=lambda e: e.get("path", ""))
    data["root"] = root
    if skipped_now:
        # v105.13 (п.1): микро-обновление тоже умеет терять файлы по лимиту,
        # и раньше делало это молча. Счётчик накапливается: полная
        # пересборка по STALE_SEC пересчитает его точно.
        data["truncated"] = True
        data["skipped_files"] = int(data.get("skipped_files") or 0) + skipped_now
    _save(project_root, data)
    return True


def _tokens(text):
    """Токены + подтокены: snake_case и camelCase дополнительно разбиваются
    (take_damage -> take_damage, take, damage), чтобы запрос "damage"
    находил take_damage (v105)."""
    out = set()
    # v105.10: \W+ — юникод целиком (был ручной диапазон только для кириллицы)
    for raw in re.split(r"\W+", str(text or ""), flags=re.U):
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


# Служебные префиксы символов .gd (см. _build_entry) — НЕ токены поиска:
# из-за них запрос со словом «class»/«func»/«var» совпадал с почти каждым
# .gd проекта и MAP набирал шумной хвост. Багфикс v105.9 (пункт 2).
# Символы узлов .tscn («Имя:Тип») не трогаем — там до двоеточия имя узла.
_SYM_PREFIXES = ("class:", "func:", "signal:", "var:", "const:")


def _symbol_search_text(sym):
    """Текст символа для токенов поиска: известный префикс .gd срезается,
    остальное (включая «Имя:Тип» узлов сцен) возвращается как есть."""
    s = str(sym)
    for p in _SYM_PREFIXES:
        if s.startswith(p):
            return s[len(p):]
    return s


def search(project_root, query, limit=8):
    """Ищет файлы/символы по запросу. Возвращает список записей с score."""
    data = _load_index(project_root)
    q = _tokens(query or "")
    if not q:
        return []
    scored = []
    for e in data.get("files", []):
        hay = _tokens(e.get("path", "")) | _tokens(
            " ".join(_symbol_search_text(s) for s in e.get("symbols", [])))
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
