# -*- coding: utf-8 -*-
"""v105: «Библиотекарь» (action=ask_librarian) — единая read-only точка выдачи
данных о проекте для модели. Выполняется АВТОМАТИЧЕСКИ, без подтверждения
пользователем: диск не меняется, откатывать нечего (как search_project, но
без клика). Ответ — на английском: идентификаторы кода английские, служебный
трафик дешевле по токенам, а query модель обязана писать по-английски.

Слои ответа (заполняются по порядку, пока не исчерпан бюджет символов):
  1. MAP       — релевантные файлы + символы (индекс ml_project_index);
  2. STRUCTURE — сигнатуры функций/сигналов топ-скриптов с номерами строк,
                 краткая структура топ-сцены (describe_scene);
  3. FRAGMENTS — дословные сниппеты по токенам запроса (search_project_text);
  4. GODOT API — члены упомянутых классов Godot из кэша API (gd_api_cache).

Полные тела файлов Библиотекарь НЕ отдаёт никогда — только адреса, сигнатуры
и короткие фрагменты: полное чтение остаётся за read_file с подтверждением
пользователя. Формат — плоский текст, НЕ JSON: JSON в канале модели
зарезервирован под блоки agent_action, и приучать модель к «JSON-данным»
нельзя (провоцирует срывы формата, см. tests/parser_corpus).

Улучшение поиска (синонимы, BM25, эмбеддинги) делается ТОЛЬКО внутри этого
модуля — main.py и agent_prompts.py менять не придётся.
"""
import difflib
import json
import os
import re
import time

import gd_api_cache
from minilich import ml_project_index
from project_tools import describe_scene, read_project_file, search_project_text

CHAR_BUDGET = 8000    # жёсткий потолок ответа, символов
MAP_LIMIT = 8         # слой 1: максимум файлов в карте
STRUCT_FILES = 3      # слой 2: максимум файлов с сигнатурами/структурой
SIG_PER_FILE = 24     # слой 2: максимум строк-сигнатур на один .gd
SCENE_CHARS = 900     # слой 2: максимум символов на структуру сцены
FRAGMENT_LIMIT = 6    # слой 3: максимум дословных сниппетов
FRAGMENT_TOKENS = 4   # слой 3: сколько токенов запроса ищем дословно
# v105.12 (раунд 4, п.1): квоту FRAGMENTS выбирал первый по алфавиту
# каталог — после фильтра addons/ им стал docs/. Механизм тот же:
# квота делилась по порядку обхода, без учёта ценности файла, а
# регистронезависимый проход (раунд 3) увеличил число совпадений и сделал
# перекос заметным: «болтливый» markdown вытеснял скрипты целиком.
# Лечим в два слоя — лимит на файл И приоритет по типу: одного лимита
# мало, пять .md всё равно съедят квоту по два слота.
FRAG_PER_FILE = 2     # слой 3: максимум сниппетов с ОДНОГО файла, пока есть альтернативы
FRAG_POOL = 12        # слой 3: сколько кандидатов тянем из поиска до ранжирования
CALLERS_LIMIT = 6     # слой 3.5 (патч 3): максимум мест вызова суммарно
CALLERS_FUNCS = 2     # слой 3.5 (патч 3): максимум функций, для которых ищем вызовы
AUTOLOAD_LIMIT = 12   # слой 1.5 (патч 4): максимум автозагрузок в ответе
SIGNALS_MAX = 2       # слой 3.6 (патч 4): максимум сигналов, для которых ищем связи
SIGNALS_LIMIT = 6     # слой 3.6 (патч 4): максимум строк о сигналах суммарно

# Ключевые слова, при которых список автозагрузок показывается всегда
_AUTOLOAD_KEYWORDS = {"autoload", "autoloads", "singleton", "singletons", "global", "globals"}

_LOG_FILE = "librarian_log.jsonl"   # патч 5: телеметрия обкатки
_LOG_MAX_BYTES = 262144             # ~256 КБ; старый файл уходит в .1 (одно поколение)
_LOG_SECTIONS = ("MAP", "AUTOLOADS", "STRUCTURE", "FRAGMENTS", "CALLERS", "SIGNALS", "GODOT API")

# v105.10 (шаг 8): нижний порог бюджета. Было жёсткое max(1000, ...) —
# вызов с budget_chars=500 молча получал 1000. Меньше этого смысла нет:
# FOOTER и шапка ответа должны влезать всегда.
_MIN_BUDGET = 400

# v105.10 (раунд 3, п.1): маркеры КОСВЕННОГО вызова по имени-строке.
# Строка "take_damage" сама по себе ничего не значит — это может быть
# комментарий, подпись кнопки или проверка has_method(). Вызовом её
# делает только соседство с одной из этих конструкций (сравнение в lower()).
_INDIRECT_CALL_CTX = ("call(", "callv(", "call_deferred(", "rpc", "callable(",
                      ".connect(", ".bind(", "emit_signal(")

# v105.11 (раунд 3, п.3): признаки того, что строка с «.имя_сигнала» действительно
# работает с сигналом, а не просто упоминает похожее поле.
_SIGNAL_CTX = ("await", "connect", "emit", "bind(", "signal")


def _signal_label(code, fallback):
    """Метка строки SIGNALS по её содержимому. Нужно, потому что шаблон
    connect("sig" совпадает как подстрока внутри disconnect("sig" и
    is_connected("sig": раньше отписка показывалась как подписка, и на вопрос
    «где подписываются?» модель получала место отписки. Порядок проверок
    важен: более длинные формы сначала."""
    low = str(code).lower()
    if "is_connected(" in low:
        return "is_connected"
    if "disconnect(" in low:
        return "disconnect"
    if "await" in low:
        return "await"
    if "emit" in low:
        return "emit"
    if "connect(" in low:
        return "connect"
    if "signal=" in low:
        return "scene connection"
    return fallback or "signal"


_TRUNC_NOTE = "… (truncated: char budget reached — refine the query to see more)"
# v105.11 (раунд 3, п.5): отдельная пометка для случая, когда в ответ
# не поместилось НИ ОДНОЙ строки данных: «truncated» вводил бы в заблуждение,
# будто что-то показано и надо уточнить запрос.
_BUDGET_NOTE = "… (budget_chars too small: no project data fits — raise it)"


def _is_section_header(line):
    """Строка вида «FRAGMENTS (verbatim matches):» — заголовок слоя без содержимого.
    Нужно шагу 8: после обрезки по бюджету висячий заголовок убирается."""
    s = str(line).strip()
    return any(s.startswith(n + " (") or s == n + ":" for n in _LOG_SECTIONS)
API_CLASSES = 2       # слой 4: максимум классов Godot в ответе
API_MEMBERS = 14      # слой 4: максимум членов класса в одной строке

# v105.10 (шаг 3): юникодные имена — «func лечить()» тоже объявление.
_FUNC_LINE_RE = re.compile(r"^\s*(?:static\s+)?func\s+[^\W\d]\w*\s*[(]", re.U)
# v105.11 (раунд 3, п.4): добавлен вложенный класс «class Inner:». Без него
# методы вложенного класса выглядели в STRUCTURE как методы самого
# скрипта, и модель промахивалась с областью при patch_file.
_DECL_LINE_RE = re.compile(
    r"^\s*(?:class_name\s+\w+|class\s+[^\W\d]\w*\s*:|extends\s+\S+|signal\s+\w+)", re.U)
# v105.7: топ-уровневые var/const/@export в STRUCTURE (без отступа — локальные не шумят)
# v105.11 (раунд 3, п.4): добавлен ведущий ^\s* — без него выражение
# требовало var/const в самом начале строки, и ЛЮБОЕ поле с отступом
# (внутри вложенного класса) в STRUCTURE не попадало.
_VARDECL_LINE_RE = re.compile(r"^\s*(?:@[^\n]*?\s+)?(?:var|const)\s+[^\W\d]\w*", re.U)
_CLASS_TOKEN_RE = re.compile(r"\b([A-Z][A-Za-z0-9]{2,})\b")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Слова запроса, бесполезные для дословного поиска по коду (слой 3).
_STOPWORDS = {
    "the", "and", "for", "with", "where", "when", "how", "what", "from",
    "this", "that", "into", "does", "are", "not", "all", "any",
    "file", "files", "code", "find", "search", "look", "project",
    "func", "function", "functions", "var", "class", "signal",
    # v105.9 (пункт 1): ключевые слова объявлений GDScript — дословный grep по
    # ним даёт мусор (совпадает почти каждый .gd) и съедает слоты FRAGMENTS,
    # вытесняя содержательные токены (например, строку автозагрузки в
    # project.godot по запросу «class_name GameClock»). Объявления и так видны
    # в STRUCTURE. preload/await НЕ добавляем: их места употребления — частая
    # осмысленная цель поиска.
    "class_name", "extends", "const", "static", "onready", "export",
}

# --- Патч 1: словарь геймдев-синонимов -------------------------------------
# Чистые данные, ноль зависимостей. Работает в двух местах:
#   1) подтокены запроса расширяются синонимами перед поиском по индексу (MAP);
#   2) если токен не нашёлся дословно (FRAGMENTS) — пробуем его синонимы.
# Худший случай при плохом синониме — чуть более широкая карта, ничего не
# ломается. Все слова английские, в нижнем регистре, длина >= 3.
_SYNONYM_GROUPS = [
    # --- бой / здоровье ---
    {"damage", "hurt", "hit", "harm", "dps"},
    {"health", "life", "lives", "healthbar"},
    {"heal", "healing", "regen", "restore", "potion"},
    {"die", "died", "death", "dead", "kill", "destroy", "queue_free"},
    {"attack", "combat", "fight", "strike", "melee"},
    {"defense", "armor", "shield", "block", "parry"},
    {"knockback", "pushback", "stun", "recoil"},
    {"invincible", "invulnerable", "immune", "iframes"},
    {"critical", "crit"},
    {"shoot", "fire", "shot", "firing"},
    {"bullet", "projectile", "missile", "arrow", "rocket"},
    {"weapon", "gun", "sword", "blade", "rifle", "pistol"},
    {"ammo", "ammunition", "reload", "magazine"},
    {"explosion", "explode", "blast", "bomb", "grenade"},
    {"aim", "aiming", "crosshair", "target", "targeting"},
    # --- движение / AI ---
    {"jump", "leap", "double_jump"},
    {"move", "movement", "walk", "run", "velocity", "motion"},
    {"speed", "acceleration", "friction", "momentum"},
    {"dash", "dodge", "roll", "blink"},
    {"climb", "climbing", "ladder"},
    {"swim", "swimming", "dive"},
    {"fly", "flying", "hover", "glide"},
    {"crouch", "duck", "slide"},
    {"sprint", "stamina"},
    {"teleport", "warp", "portal"},
    {"gravity", "fall", "falling", "airborne"},
    {"pathfinding", "navigation", "navmesh", "astar"},
    {"patrol", "wander", "chase", "follow", "pursue", "flee"},
    {"state", "fsm", "statemachine", "state_machine", "behavior"},
    # --- сущности ---
    {"enemy", "mob", "monster", "foe", "boss", "minion", "creature"},
    {"player", "character", "hero", "avatar"},
    {"npc", "villager", "townsfolk"},
    {"pet", "companion", "ally", "summon"},
    # --- предметы / экономика / прогрессия ---
    {"coin", "gold", "money", "currency", "cash", "credits"},
    {"inventory", "item", "loot", "pickup", "collect", "drop"},
    {"chest", "crate", "container", "barrel"},
    {"shop", "store", "buy", "sell", "trade", "merchant", "vendor", "price"},
    {"craft", "crafting", "recipe", "forge", "upgrade"},
    {"equip", "equipment", "gear", "slot"},
    {"key", "unlock", "door", "gate", "lock"},
    {"powerup", "power_up", "buff", "debuff", "boost", "bonus"},
    {"experience", "levelup", "level_up", "progression"},
    {"skill", "ability", "talent", "perk", "spell", "magic", "mana"},
    {"quest", "mission", "objective", "task", "goal"},
    {"achievement", "trophy", "badge"},
    # --- UI / система ---
    {"menu", "hud", "interface", "button", "panel", "popup", "overlay"},
    {"score", "points", "highscore", "leaderboard"},
    {"dialog", "dialogue", "conversation", "speech", "subtitle"},
    {"notification", "toast", "alert", "message"},
    {"cursor", "mouse", "pointer"},
    {"settings", "options", "config", "preferences"},
    {"save", "load", "persist", "serialize", "savegame", "checkpoint", "autosave"},
    {"pause", "resume", "unpause"},
    {"scene", "screen", "transition", "fade"},
    {"localization", "translation", "locale", "language"},
    # --- графика / звук ---
    {"sound", "audio", "music", "sfx", "volume", "mute"},
    {"animation", "animate", "anim", "tween", "keyframe"},
    {"particle", "particles", "vfx", "effect"},
    {"shader", "material", "gdshader"},
    {"sprite", "texture", "image", "icon"},
    {"light", "lighting", "shadow", "glow", "emission"},
    {"camera", "zoom", "shake", "viewport"},
    {"background", "parallax", "skybox"},
    {"color", "tint", "modulate", "palette"},
    {"visible", "visibility", "show", "hide"},
    # --- физика ---
    {"collision", "collide", "hitbox", "hurtbox", "area", "body", "overlap"},
    {"physics", "rigidbody", "kinematic"},
    {"raycast", "ray"},
    {"trigger", "sensor", "detect", "detection"},
    {"bounce", "bounciness", "elastic"},
    # --- мир / уровни ---
    {"level", "stage", "map", "world", "arena", "room", "dungeon"},
    {"tile", "tilemap", "tileset", "grid", "cell"},
    {"spawn", "instantiate", "instance", "preload", "respawn", "spawner"},
    {"terrain", "ground", "floor", "platform"},
    {"wall", "obstacle", "barrier"},
    # --- ввод ---
    {"input", "controls", "keyboard", "gamepad", "action", "joystick", "controller"},
    {"touch", "swipe", "tap"},
    {"click", "press", "pressed", "released"},
    # --- сеть / время / прочее ---
    {"multiplayer", "network", "online", "server", "client", "sync", "lobby", "peer", "rpc"},
    {"timer", "cooldown", "delay", "wait", "countdown", "tick", "interval"},
    {"random", "rng", "seed", "shuffle", "noise"},
    {"debug", "log", "print", "console"},
    {"error", "crash", "exception", "bug"},
    {"tutorial", "hint", "guide"},
    {"win", "victory", "lose", "defeat", "gameover", "game_over"},
    {"difficulty", "mode", "hardcore"},
]
_SYN_LOOKUP = {}
for _g in _SYNONYM_GROUPS:
    for _w in _g:
        _SYN_LOOKUP.setdefault(_w, set()).update(_g)
_SYN_EXPAND_LIMIT = 12   # максимум добавляемых синонимов на запрос (слой MAP)
_SYN_GREP_LIMIT = 5      # максимум синонимов-grep на один токен (слой FRAGMENTS):
                         # словарь большой, а каждый grep — проход по файлам проекта;
                         # потолок держит время ответа предсказуемым даже на 2000 файлах

# v105.13 (патч производительности, п.3): _SYN_GREP_LIMIT — потолок НА ТОКЕН,
# и этого оказалось мало: при FRAGMENT_TOKENS = 4 запрос из нетипичных имён
# (ни одно не находится дословно) давал до 4 × 5 = 20 ПОЛНЫХ обходов
# диска на ОДИН ответ. На большом проекте именно это, а не размер индекса,
# давало основную задержку. Теперь есть ОБЩИЙ бюджет проходов на весь
# вызов _fragments().
#
# v105.14 (п.1): исправлены и цифра, и описание. Было: «8 — это два прямых
# прохода плюс шесть синонимных» — комментарий не соответствовал коду:
# прямых проходов бывает до FRAGMENT_TOKENS = 4, и они тоже списывались
# с бюджета, а остаток целиком выбирал ПЕРВЫЙ же не нашедшийся токен.
# Почему плохо: многословный разведочный запрос терял слой FRAGMENTS
# целиком и отвечал «ничего не найдено». Теперь честно: это потолок
# ТОЛЬКО на СИНОНИМНЫЕ проходы (прямые не списываются вовсе и уже
# ограничены FRAGMENT_TOKENS), и он делится между токенами поровну.
# 12 подобрано по тестам: четырёхсловный разведочный запрос получает
# не меньше 3 синонимных проходов на КАЖДЫЙ токен даже в худшем
# случае (обычно больше — неизрасходованное возвращается в котёл), а
# вырожденный запрос даёт не более 12 синонимных обходов вместо
# полного веера FRAGMENT_TOKENS × _SYN_GREP_LIMIT = 20.
_FRAG_GREP_BUDGET = 12


def _synonyms(token):
    """Синонимы токена (без самого токена), отсортированы для детерминизма."""
    tl = str(token or "").lower()
    return sorted(_SYN_LOOKUP.get(tl, set()) - {tl})


def _expanded_query(q):
    """Запрос + синонимы его подтокенов — для поиска по индексу (слой MAP).
    Возвращает (расширенный_запрос, список добавленных синонимов)."""
    ql = str(q or "").lower()
    extra = []
    for st in sorted(_query_subtokens(q)):
        for s in _synonyms(st):
            if s not in ql and s not in extra:
                extra.append(s)
    extra = extra[:_SYN_EXPAND_LIMIT]
    return ((q + " " + " ".join(extra)) if extra else q, extra)


# --- Патч 2: взвешенный скоринг + подсказки при опечатках ----------------
# Работает ПОВЕРХ скоринга индекса, не трогая ml_project_index: берём больше
# кандидатов и переранжируем детерминированно. Худший случай при ошибке
# весов — неидеальный порядок файлов в карте, упасть тут нечему.
_KIND_WEIGHT = {"gd": 2.0, "tscn": 1.0}  # скрипты > сцены > прочее (md/tres/cfg)

# v105.12 (раунд 4, п.1): тот же принцип, что у _KIND_WEIGHT в MAP, но для
# FRAGMENTS и в виде РАНГА (меньше = лучше): код важнее сцен и ресурсов,
# те важнее документации (.md/.txt/.csv и прочее — ранг 2).
_FRAG_KIND_RANK = {"gd": 0, "gdshader": 0, "shader": 0,
                   "tscn": 1, "scn": 1, "tres": 1, "godot": 1, "cfg": 1}


def _frag_rank(path):
    """Ранг файла для FRAGMENTS по расширению: 0 — код, 1 — сцены/ресурсы, 2 — прочее."""
    ext = str(path or "").rsplit(".", 1)[-1].lower() if "." in str(path or "") else ""
    return _FRAG_KIND_RANK.get(ext, 2)
_RERANK_POOL = 3                          # берём из индекса MAP_LIMIT*3 кандидатов


def _rerank_hits(hits, query, syn_used):
    """Взвешенный скоринг: совпадение с именем функции/класса/сигнала/узла
    дороже совпадения с именем файла, то — дороже папки; точный токен запроса
    дороже синонима; .gd выше .tscn и прочих. Сортировка стабильная (score, path)."""
    q_orig = _query_subtokens(query)
    q_syn = {str(s).lower() for s in (syn_used or ())}
    rescored = []
    for h in hits:
        path = str(h.get("path", ""))
        fname = path.rsplit("/", 1)[-1]
        dirs = path[: -len(fname)] if fname else path
        sym_tok = _query_subtokens(" ".join(str(s) for s in h.get("symbols", [])))
        name_tok = _query_subtokens(fname)
        dir_tok = _query_subtokens(dirs.replace("/", " "))
        score = float(h.get("score", 0))   # база: пересечение токенов из индекса
        for t in q_orig:
            if t in sym_tok:
                score += 5.0               # имя функции/класса/сигнала/узла — самое ценное
            if t in name_tok:
                score += 3.0               # имя файла
            elif t in dir_tok:
                score += 1.0               # папка
        for t in q_syn:
            if t in sym_tok:
                score += 1.5               # синоним слабее точного токена
            if t in name_tok:
                score += 1.0
        score += _KIND_WEIGHT.get(str(h.get("kind", "")), 0.0)
        rescored.append((score, path, h))
    rescored.sort(key=lambda x: (-x[0], x[1]))
    return [h for _sc, _p, h in rescored]


def _near_tokens(project_root, query, limit=6):
    """Подсказки при опечатке: похожие идентификаторы, которые РЕАЛЬНО есть
    в индексе проекта (имена функций/классов/сигналов/узлов и части путей).
    Стандартный difflib, без зависимостей. Модель сама чинит запрос следующим
    ask_librarian — без лишнего круга через пользователя."""
    try:
        data = ml_project_index._load_index(project_root, auto_build=False)
    except Exception:
        return []
    vocab = set()
    for e in (data or {}).get("files", []):
        vocab |= _query_subtokens(str(e.get("path", "")).replace("/", " "))
        vocab |= _query_subtokens(" ".join(str(s) for s in e.get("symbols", [])))
    if not vocab:
        return []
    vocab = sorted(vocab)  # детерминизм при равных ratio
    out = []
    for t in sorted(_query_subtokens(query)):
        for m in difflib.get_close_matches(t, vocab, n=2, cutoff=0.75):
            if m != t and m not in out:
                out.append(m)
    return out[:limit]


FOOTER = ("Next: use read_function for exact bodies (verbatim, usable as patch_file \"search\"); "
          "read_file only when a whole file is needed; ask_librarian again with other English "
          "terms to explore further. Line numbers are 1-based.")


# v105.10: префиксы, которые search_project_text пропускает ДО набора квоты.
# Раньше аддоны отсеивались только ПОСЛЕ поиска (_is_addon_rel), и при
# любом установленном аддоне (Dialogic, Phantom Camera…) файлы addons/
# выбирали всю квоту max_results — слои FRAGMENTS/CALLERS/SIGNALS молча
# пустели. _is_addon_rel остаётся как второй рубеж (и для hits из индекса).
_SEARCH_EXCLUDE = ("addons/",)


def _is_addon_rel(path):
    """True для путей внутри res://addons/... — библиотекарь их не выдаёт
    (та же политика, что _is_addon_path в main.py: аддоны — только по явной
    просьбе пользователя, а до библиотекаря она не доходит)."""
    p = str(path or "").replace("\\", "/")
    if p.startswith("res://"):
        p = p[len("res://"):]
    return p.lstrip("/").startswith("addons/")


def _query_tokens(query):
    """Токены запроса для дословного поиска: без стоп-слов, длинные первыми."""
    seen, out = set(), []
    # v105.10: \W+ — юникодное разбиение (русские имена тоже токены)
    for t in re.split(r"\W+", str(query or ""), flags=re.U):
        tl = t.lower()
        if len(tl) < 3 or tl in _STOPWORDS or tl in seen:
            continue
        seen.add(tl)
        out.append(t)
    out.sort(key=len, reverse=True)
    return out[:FRAGMENT_TOKENS]


def _query_subtokens(query):
    """Подтокены запроса (snake_case/camelCase разбиты) — для фильтра членов API."""
    subs = set()
    for t in re.split(r"\W+", str(query or ""), flags=re.U):
        for p in _CAMEL_RE.sub(" ", t).replace("_", " ").split():
            pl = p.lower()
            if len(pl) >= 3 and pl not in _STOPWORDS:
                subs.add(pl)
    return subs


def _gd_signatures(project_root, godot_path, limit=SIG_PER_FILE):
    """Строки-объявления .gd с номерами строк: class_name/extends/signal/func."""
    try:
        content, truncated = read_project_file(project_root, godot_path, max_chars=200000)
    except Exception as e:
        return ["  (read error: %s)" % e]
    out, func_indent = [], None
    for i, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        # Вышли из тела функции, как только отступ вернулся на её уровень.
        if func_indent is not None and indent <= func_indent:
            func_indent = None
        is_func = bool(_FUNC_LINE_RE.match(line))
        is_decl = bool(_DECL_LINE_RE.match(line))
        is_var = bool(_VARDECL_LINE_RE.match(line))
        if not (is_func or is_decl or is_var):
            continue
        # v105.11 (раунд 3, п.4): _VARDECL_LINE_RE теперь допускает отступ
        # (ради полей вложенного класса), поэтому локальные переменные
        # внутри функций надо отсекать явно — иначе STRUCTURE зашумится
        # всеми var из тел функций и вытеснит настоящие объявления по limit.
        if is_var and not is_decl and func_indent is not None:
            continue
        # Было line.strip() — отступ терялся, и метод вложенного класса
        # был неотличим от метода самого скрипта. rstrip() сохраняет
        # иерархию и не меняет вывод для топ-уровня.
        out.append("  L%d: %s" % (i, line.rstrip()))
        if is_func:
            func_indent = indent
        if len(out) >= limit:
            out.append("  … (more declarations omitted)")
            break
    # v105.10 (шаг 9): файл длиннее 200000 символов читался частично, и
    # флаг truncated молча выбрасывался: объявления из хвоста файла
    # просто отсутствовали в STRUCTURE, и модель считала список полным.
    # Отличается от пометки выше: та — про лимит строк, эта — про лимит чтения.
    if truncated:
        out.append("  … (file too large: read first 200000 chars; later declarations not scanned)")
    return out or ["  (no declarations found)"]


def _scene_summary(project_root, godot_path):
    try:
        txt = str(describe_scene(project_root, godot_path, max_chars=SCENE_CHARS * 4))
    except Exception as e:
        return ["  (scene read error: %s)" % e]
    if len(txt) > SCENE_CHARS:
        txt = txt[:SCENE_CHARS] + "…"
    return ["  " + ln for ln in txt.splitlines() if ln.strip()]


def _structure(project_root, hits):
    """Слой 2: сигнатуры топ-скриптов и структура первой сцены из карты."""
    out, used, scene_done = [], 0, False
    for h in hits:
        if used >= STRUCT_FILES:
            break
        rel = h.get("path", "")
        kind = h.get("kind", "")
        if kind == "gd":
            out.append("res://%s:" % rel)
            out += _gd_signatures(project_root, "res://" + rel)
            used += 1
        elif kind == "tscn" and not scene_done:
            txt = _scene_summary(project_root, "res://" + rel)
            if txt:
                out.append("res://%s (scene):" % rel)
                out += txt
                used += 1
                scene_done = True
    return out


def _grep_token(project_root, tok, seen, out, frags_left, case_insensitive=False):
    """Один дословный grep: складывает сниппеты в out, возвращает сколько добавил."""
    if frags_left <= 0:
        return 0
    try:
        # v105.12 (раунд 4, п.1): берём ПООЛ кандидатов, а не первые 3 по
        # порядку обхода — иначе выбирать будет не из чего.
        results, _tr = search_project_text(project_root, tok, max_results=FRAG_POOL,
                                           context_lines=1,
                                           exclude_rel_prefixes=_SEARCH_EXCLUDE,
                                           case_insensitive=case_insensitive)
    except Exception:
        return 0
    cands = [r for r in results
             if (r.get("path"), r.get("line")) not in seen
             and not _is_addon_rel(r.get("path", ""))]
    # Сначала код (.gd/.tscn), потом всё остальное; внутри ранга — стабильно по (path, line).
    cands.sort(key=lambda r: (_frag_rank(str(r.get("path", ""))),
                              str(r.get("path", "")), int(r.get("line") or 0)))

    added = 0
    per_file = {}

    def _take(r):
        key = (r.get("path"), r.get("line"))
        seen.add(key)
        out.append("%s line %d (matched «%s»):" % (r["path"], r["line"], tok))
        # ВАЖНО: extend, а не «out += [...]» — во вложенной функции «+=» делает
        # out локальной переменной и валится UnboundLocalError.
        out.extend("  " + ln for ln in str(r.get("snippet", "")).splitlines())

    # Проход 1: не более FRAG_PER_FILE сниппетов с одного файла.
    for r in cands:
        if added >= frags_left:
            return added
        p = str(r.get("path", ""))
        if per_file.get(p, 0) >= FRAG_PER_FILE:
            continue
        per_file[p] = per_file.get(p, 0) + 1
        _take(r)
        added += 1
    # Проход 2: если квота не выбрана (совпадения есть ТОЛЬКО в одном-двух
    # файлах) — добираем остаток БЕЗ лимита. Иначе одна потеря данных
    # (код вытеснен документацией) поменялась бы на другую (урезанный единственный файл).
    for r in cands:
        if added >= frags_left:
            break
        if (r.get("path"), r.get("line")) in seen:
            continue
        _take(r)
        added += 1
    return added


def _grep_patterns(project_root, patterns, max_results):
    """v105.14 (п.2): ищет СРАЗУ все шаблоны слоя за ОДИН обход проекта
    и возвращает {шаблон: [результаты в порядке обхода]}.

    Было: CALLERS и SIGNALS вызывали search_project_text отдельно на КАЖДЫЙ
    шаблон: до 6 × CALLERS_FUNCS = 12 и до 13 × SIGNALS_MAX = 26 полных обходов
    диска на ОДИН ответ. Почему плохо: бюджет v105.13 ограничивал только
    FRAGMENTS, а главный веер обходов был здесь — на проекте в 2700 файлов
    запрос с сигналами был самым медленным ответом (1.49 с). Квота
    max_results считается на каждый шаблон отдельно, а порядок результатов —
    порядок обхода, поэтому выдача обоих слоёв остаётся побайтно той же,
    что при отдельных вызовах."""
    by_needle = {}
    if not patterns:
        return by_needle
    try:
        results, _tr = search_project_text(project_root, None, max_results=max_results,
                                           context_lines=0,
                                           exclude_rel_prefixes=_SEARCH_EXCLUDE,
                                           needles=list(patterns))
    except Exception:
        return by_needle  # как и раньше: ошибка поиска — просто пустой слой
    for r in results:
        by_needle.setdefault(str(r.get("needle", "")), []).append(r)
    return by_needle


def _fragments(project_root, query):
    """Слой 3: дословные совпадения токенов запроса; если токен дословно не
    нашёлся — пробуем его геймдев-синонимы (патч 1), первый удачный."""
    seen, out, frags = set(), [], 0
    toks = list(_query_tokens(query))
    # v105.14 (п.1): бюджет тратится ТОЛЬКО на синонимные проходы.
    # Было (v105.13): «grep_budget -= 1» списывалось и за ПРЯМОЙ проход по
    # самому токену, то есть 4 из 8 единиц уходили ещё до первого синонима.
    # Почему плохо: прямых проходов и так не больше FRAGMENT_TOKENS, и именно
    # они дают ТОЧНЫЕ совпадения — экономить на них нельзя (в v105.13 это
    # было написано в комментарии, но сделано ровно наоборот).
    syn_budget = _FRAG_GREP_BUDGET
    for i, tok in enumerate(toks):
        # v105.11 (раунд 3, п.2): один регистронезависимый проход вместо связки
        # «строгий + фолбэк»: запрос «health» находит и var health, и HealthUp,
        # и стоит ровно один обход диска.
        added = _grep_token(project_root, tok, seen, out, FRAGMENT_LIMIT - frags,
                            case_insensitive=True)
        if added == 0 and syn_budget > 0:
            # v105.14 (п.1): честная доля вместо «кто первый — того и бюджет».
            # Было: первый же не нашедшийся токен выбирал весь остаток (до
            # _SYN_GREP_LIMIT = 5 проходов), и на все последующие токены
            # синонимных проходов не оставалось вовсе. Почему плохо:
            # многословный разведочный запрос («inventory crafting shop ui
            # save») — обычный сценарий, а он терял слой FRAGMENTS целиком и
            # отвечал «ничего не найдено». Чиним делением остатка на число
            # ЕЩЁ НЕ ОБРАБОТАННЫХ токенов; неизрасходованная часть доли сама
            # остаётся в общем котле (списываем только фактические проходы),
            # так что токены без синонимов отдают свою долю следующим.
            share = max(1, syn_budget // max(1, len(toks) - i))
            share = min(share, _SYN_GREP_LIMIT, syn_budget)
            for syn in _synonyms(tok)[:share]:
                added = _grep_token(project_root, syn, seen, out, FRAGMENT_LIMIT - frags,
                                    case_insensitive=True)
                syn_budget -= 1
                if added:
                    break  # per-token break оставлен как был: первый удачный синоним
        frags += added
        if frags >= FRAGMENT_LIMIT:
            break
    return out


def _callers(project_root, query, hits):
    """Слой 3.5 (патч 3): обратные ссылки — места вызова функций, чьё имя
    ТОЧНО совпало с токеном запроса (по символам func: из карты).
    Закрывает типовой вопрос «кто это дёргает?» без двух-трёх read_file.
    Переиспользует search_project_text; строка-определение (func имя() фильтруется."""
    q_full = {t.lower() for t in re.split(r"\W+", str(query or ""), flags=re.U) if len(t) >= 3}
    names = []
    for h in hits:
        if str(h.get("kind", "")) != "gd":
            continue
        for s in h.get("symbols", []):
            s = str(s)
            if s.startswith("func:"):
                name = s[len("func:"):]
                if name.lower() in q_full and name not in names:
                    names.append(name)
    cands, seen = [], set()
    more_names = names[CALLERS_FUNCS:]  # v105.10: что не поместилось в CALLERS_FUNCS
    # v105.14 (п.2): шаблоны всех имён собираются ЗАРАНЕЕ и ищутся за ОДИН
    # обход проекта. Было: search_project_text на КАЖДЫЙ шаблон, то есть до
    # 6 шаблонов × CALLERS_FUNCS (2) = 12 полных обходов диска на ОДИН ответ.
    # Почему плохо: бюджет v105.13 ограничивал только FRAGMENTS, а главный
    # веер обходов был здесь и в SIGNALS — и на большом проекте именно он
    # давал самые медленные ответы. Порядок перебора (имя-мажор, шаблон-минор)
    # и max_results на каждый шаблон сохранены, поэтому выдача побайтно та же.
    specs = []  # (имя, шаблон, это_имя_в_кавычках)
    for name in names[:CALLERS_FUNCS]:
        # v105.10 (шаг 6): вызов не всегда записан как «имя(» вплотную:
        #   p.take_damage (7)          — пробел перед скобкой (валидный GDScript);
        #   p.callv("take_damage", [3]) и call_deferred('take_damage') — косвенный
        #   вызов по имени-строке (обе разновидности кавычек).
        direct = (name + "(", name + " (")
        quoted = ('"%s"' % name, "'%s'" % name)
        # v105.12 (раунд 4, п.4): повседневная связка Godot 4 — Callable без
        # скобки вызова сразу после имени: p.take_damage.bind(4) в tween_callback
        # и connect с аргументами, или p.take_damage.call(4)/.call_deferred(4).
        # Эти шаблоны безопасны: имя идёт без кавычек и вплотную к .bind(/.call —
        # в комментарии или подписи кнопки такого не бывает, поэтому проверка
        # контекста им не нужна (она только для quoted).
        callable_forms = (name + ".bind(", name + ".call")
        for pattern in direct + quoted + callable_forms:
            specs.append((name, pattern, pattern in quoted))
    by_needle = _grep_patterns(project_root, [p for _n, p, _q in specs], max_results=10)
    def_res = {}
    for name, pattern, is_quoted in specs:
        def_re = def_res.get(name)
        if def_re is None:
            def_re = def_res[name] = re.compile(r"\bfunc\s+%s\s*[(]" % re.escape(name))
        for r in by_needle.get(pattern, []):
            snippet = str(r.get("snippet", "")).strip()
            if _is_addon_rel(r.get("path", "")) or def_re.search(snippet):
                continue  # определение — не вызов; аддоны не выдаём
            code = re.sub(r"^\d+:\s*", "", snippet)  # убрать префикс «N: » сниппета
            # Регрессия шага 6, найдена рецензентом: шаблоны "имя"/'имя'
            # ловили любое упоминание имени в тексте — комментарий,
            # print("имя"), has_method("имя"), присваивание в переменную —
            # и выдавали их за места вызова. Косвенный вызов отличается
            # от упоминания только контекстом строки — требуем его явно.
            if is_quoted:
                low = code.lower()
                if not any(ctx in low for ctx in _INDIRECT_CALL_CTX):
                    continue
            if code.lstrip().startswith("#"):
                continue  # закомментированная строка — не вызов
            key = (str(r.get("path", "")), r.get("line"))
            if key in seen:
                continue  # одна и та же строка могла совпасть несколькими шаблонами
            seen.add(key)
            cands.append((str(r.get("path", "")), int(r.get("line") or 0), code))
    # Рецензент также верно заметил: порядок «10, 3, 4, 7, 8» выглядит как
    # ошибка — это был порядок перебора шаблонов. Собираем всё и сортируем
    # по файлу и номеру строки, и только потом режем по CALLERS_LIMIT.
    cands.sort(key=lambda c: (c[0], c[1]))
    out = ["- %s line %d: %s" % c for c in cands[:CALLERS_LIMIT]]
    if out and len(cands) > CALLERS_LIMIT:
        out.append("  (+%d more call sites not shown \u2014 refine the query)"
                   % (len(cands) - CALLERS_LIMIT))
    # v105.10 (шаг 6): раньше третья и дальнейшие функции отбрасывались
    # молча — модель считала, что вызовов нет.
    if out and more_names:
        out.append("  (call sites shown only for: %s; also matched: %s)"
                   % (", ".join(names[:CALLERS_FUNCS]), ", ".join(more_names[:4])))
    return out


def _log_query(project_root, record):
    """Патч 5: телеметрия обкатки — append-only jsonl в хранилище minilich
    (.agent_history). По журналу видно, какие запросы модель шлёт на самом
    деле, где ответ пуст и каких синонимов не хватает — сырьё для точечной
    настройки словаря и весов. Ошибки глотаются целиком: телеметрия
    никогда не должна ломать или замедлять ответ."""
    try:
        from minilich import ml_data
        record = dict(record)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        # Багфикс v105.8: при «мозге в папке плагина» лог общий для всех
        # проектов — помечаем каждую запись корнем проекта.
        record["root"] = os.path.abspath(project_root or ".")
        path = os.path.join(ml_data.storage_dir(project_root), _LOG_FILE)
        if os.path.isfile(path) and os.path.getsize(path) > _LOG_MAX_BYTES:
            os.replace(path, path + ".1")  # простая ротация, без бесконечного роста
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _autoloads(project_root):
    """Слой 1.5 (патч 4): секция [autoload] из project.godot — глобальные
    синглтоны, доступные из любого скрипта по имени.
    Простой построчный разбор ini-секции, без новых зависимостей.
    Возвращает [(имя, res://путь)]."""
    try:
        content, _tr = read_project_file(project_root, "res://project.godot", max_chars=200000)
    except Exception:
        return []
    out, in_section = [], False
    for line in str(content).splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_section = (s == "[autoload]")
            continue
        if in_section and "=" in s and not s.startswith(";"):
            name, _eq, val = s.partition("=")
            val = val.strip().strip('"').lstrip("*")  # звёздочка = «включено»
            if name.strip() and val:
                out.append((name.strip(), val))
    return out[:AUTOLOAD_LIMIT]


def _autoload_lines(project_root, query):
    """Строки слоя AUTOLOADS. Показываем только если запрос задевает
    имя/путь автозагрузки или содержит ключевые слова (autoload/singleton/
    global) — чтобы не съедать бюджет каждого ответа без нужды."""
    autos = _autoloads(project_root)
    if not autos:
        return []
    low = {t.lower() for t in re.split(r"\W+", str(query or ""), flags=re.U) if t}
    if not (low & _AUTOLOAD_KEYWORDS):
        subs = _query_subtokens(query)
        if not any(subs & _query_subtokens(name + " " + path.replace("/", " "))
                   for name, path in autos):
            return []
    return ["- %s -> %s" % (name, path) for name, path in autos]


def _signal_wiring(project_root, query, hits):
    """Слой 3.6 (патч 4): карта сигналов, чьё имя ТОЧНО совпало с токеном
    запроса: связи [connection ...] в .tscn + подключения в коде (v105.9:
    «name.connect(…)» Godot 4 и «connect("name"…)» legacy) + места эмита в .gd.
    Как и CALLERS — чистый дословный поиск, без парсинга кода. Шаблоны
    привязаны к имени сигнала, поэтому чужие connect (таймеры и пр.)
    не цепляются.

    v105.11 (раунд 3, п.3): добавлены три повседневные формы Godot 4 —
    «await $P.sig», «is_connected("sig"» и «disconnect("sig"», а также запись
    с пробелом «$P.sig .connect(». Метка теперь вычисляется по САМОЙ СТРОКЕ,
    а не по шаблону: раньше connect("sig" совпадал как ПОДСТРОКА внутри
    disconnect("sig", и отписка показывалась как подписка."""
    q_full = {t.lower() for t in re.split(r"\W+", str(query or ""), flags=re.U) if len(t) >= 3}
    names = []
    for h in hits:
        for s in h.get("symbols", []):
            s = str(s)
            if s.startswith("signal:"):
                name = s[len("signal:"):]
                if name.lower() in q_full and name not in names:
                    names.append(name)
    # v105.12 (раунд 4, п.5): строки копим в cands и сортируем в конце, как
    # в CALLERS. Раньше вывод шёл в порядке перебора шаблонов
    # (a_ui:4, z_hud:4, player:6, a_ui:6, a_ui:7) и выглядел как сбой.
    cands, seen_lines = [], set()
    # v105.14 (п.2): то же, что в CALLERS — все шаблоны слоя ищутся за ОДИН
    # обход проекта. Было: до 12 шаблонов × SIGNALS_MAX (2) = до 24 полных
    # обходов диска на один ответ; на проекте в 2700 файлов запрос со словом
    # signal был самым медленным именно из-за этого веера. Порядок перебора,
    # метки, фильтры и max_results на шаблон сохранены без изменений.
    specs = []  # (имя, шаблон, метка)
    for name in names[:SIGNALS_MAX]:
        # v105.10 (шаг 2): в GDScript строка может быть в ЛЮБЫХ кавычках —
        # у шаблонов со строковым именем сигнала есть парные варианты с '.
        # signal="..." остаётся только с ", т.к. это формат сериализации .tscn
        # (его пишет сам Godot), а name.connect(/name.emit кавычек не содержит.
        for pattern, label in ((('signal="%s"' % name), "scene connection"),
                               ("%s.connect(" % name, "connect"),
                               ("%s .connect(" % name, "connect"),
                               ('connect("%s"' % name, "connect"),
                               ("connect('%s'" % name, "connect"),
                               ("%s.emit" % name, "emit"),
                               ('emit_signal("%s"' % name, "emit"),
                               ("emit_signal('%s'" % name, "emit"),
                               # v105.11: «is_connected(» НЕ ловится шаблоном connect("sig" —
                               # в нём «connected(», а не «connect(»; и имя в кавычках, так что
                               # широкий шаблон «.sig» его тоже не видит. Нужен явный.
                               ('is_connected("%s"' % name, "is_connected"),
                               ("is_connected('%s'" % name, "is_connected"),
                               ('disconnect("%s"' % name, "disconnect"),
                               ("disconnect('%s'" % name, "disconnect"),
                               # v105.11: «await $P.sig» — между await и именем стоит узел,
                               # поэтому ищем «.sig» и фильтруем по контексту ниже.
                               (".%s" % name, None)):
            specs.append((name, pattern, label))
    by_needle = _grep_patterns(project_root, [p for _n, p, _l in specs], max_results=6)
    for name, pattern, label in specs:
        for r in by_needle.get(pattern, []):
            if _is_addon_rel(r.get("path", "")):
                continue
            code = re.sub(r"^\d+:\s*", "", str(r.get("snippet", "")).strip())
            if code.lstrip().startswith("#"):
                continue  # закомментированная строка — не проводка
            # Широкий шаблон «.sig» без метки: пускаем только то, где имя —
            # целое слово (не died_count) и есть сигнальный контекст.
            if label is None:
                if not re.search(r"\.%s\b" % re.escape(name), code):
                    continue
                if not any(m in code.lower() for m in _SIGNAL_CTX):
                    continue
            # v105.11 (раунд 3, п.3): метка — по строке, а не по шаблону.
            line_label = _signal_label(code, label)
            line_txt = "- %s line %d (%s): %s" % (r["path"], r["line"], line_label, code)
            if line_txt in seen_lines:
                continue
            seen_lines.add(line_txt)
            cands.append((str(r.get("path", "")), int(r.get("line") or 0), line_txt))
    # Сортировка по (path, line) — та же, что в CALLERS. Резать по SIGNALS_LIMIT
    # ПОСЛЕ сортировки: иначе порядок перебора шаблонов решал бы, что
    # показать, и выдача зависела бы от порядка в кортеже patterns.
    cands.sort(key=lambda c: (c[0], c[1]))
    return [txt for _p, _ln, txt in cands[:SIGNALS_LIMIT]]


def _pick_members(names, query_subtokens, limit):
    """Члены класса: сперва совпадающие с подтокенами запроса, иначе первые по алфавиту."""
    all_sorted = sorted(names)
    rel = [n for n in all_sorted if any(st in n.lower() for st in query_subtokens)]
    chosen = rel or all_sorted
    head = ", ".join(chosen[:limit])
    if len(chosen) > limit:
        head += " …(+%d more)" % (len(chosen) - limit)
    if rel and len(all_sorted) > len(rel):
        head += " [query-related of %d total]" % len(all_sorted)
    return head or "(none)"


def _godot_api(project_root, query, addon_dir=None):
    """Слой 4: члены классов Godot, упомянутых в запросе (из кэша API)."""
    try:
        if not gd_api_cache.has_cache(project_root, addon_dir=addon_dir):
            return []
    except Exception:
        return []
    subs = _query_subtokens(query)
    out, done, classes = [], set(), 0
    for name in _CLASS_TOKEN_RE.findall(str(query or "")):
        if name in done:
            continue
        done.add(name)
        try:
            if not gd_api_cache.get_class(project_root, name, addon_dir=addon_dir):
                continue
            methods, _props, signals = gd_api_cache.collect_members(
                project_root, name, addon_dir=addon_dir)
        except Exception:
            continue
        out.append("- %s: methods %s" % (name, _pick_members(methods, subs, API_MEMBERS)))
        if signals:
            out.append("  signals: %s" % _pick_members(signals, subs, API_MEMBERS))
        classes += 1
        if classes >= API_CLASSES:
            break
    return out


def answer(project_root, query, budget_chars=CHAR_BUDGET, addon_dir=None):
    """Главная функция Библиотекаря: компактная английская справка о проекте.
    Никогда не бросает наружу ничего, кроме понятного текста (ошибки слоёв
    глотаются послойно) — но вызывающий код всё равно оборачивает в try."""
    # v105.10 (шаг 9): нестроковый query молча превращался в своё repr:
    # ["died"] -> "['died']", и Библиотекарь честно искал эту строку со скобками
    # и кавычками, ничего не находил и отвечал "no matches" вместо того,
    # чтобы сказать вызывающему, что формат аргумента неверный.
    # v105.11 (раунд 3, п.6): раньше ЛЮБОЙ нестроковый query получал ответ
    # «empty "query"» — формально неверно: query=123 не пустой, а не того
    # типа. Модели нужна разная подсказка: «заполни поле» или «исправь тип».
    if not isinstance(query, str):
        return ("[Librarian]: \"query\" must be a string, got %s. Resend: "
                "{\"action\": \"ask_librarian\", \"query\": \"English code terms: "
                "function/class/signal/node names and synonyms\"}." % type(query).__name__)
    q = query.strip()
    if not q:
        return ("[Librarian]: empty \"query\". Resend: {\"action\": \"ask_librarian\", "
                "\"query\": \"English code terms: function/class/signal/node names and synonyms\"}.")
    q_expanded, syn_used = _expanded_query(q)
    try:
        hits = ml_project_index.search(project_root, q_expanded, limit=MAP_LIMIT * _RERANK_POOL)
    except Exception:
        hits = []
    hits = [h for h in hits if not _is_addon_rel(h.get("path", ""))]
    # v105.10 (шаг 4): индекс отстаёт от диска, если файл удалили снаружи
    # (Git, Проводник, другая ветка) — до STALE_SEC агент видел призрака в MAP
    # и «read error» в STRUCTURE. Убираем из выдачи и сразу починим индекс,
    # чтобы следующие запросы не платили за ту же проверку снова.
    try:
        _root_abs = os.path.abspath(project_root or ".")
        _ghosts = [str(h.get("path", "")) for h in hits
                   if not os.path.isfile(os.path.join(_root_abs,
                                                      str(h.get("path", "")).replace("/", os.sep)))]
        if _ghosts:
            _gone = set(_ghosts)
            hits = [h for h in hits if str(h.get("path", "")) not in _gone]
            note_files_changed(project_root, deleted=_ghosts)
    except Exception:
        pass  # самолечение не должно убить ответ
    try:
        hits = _rerank_hits(hits, q, syn_used)[:MAP_LIMIT]
    except Exception:
        hits = hits[:MAP_LIMIT]  # патч 2 не должен убить ответ целиком
    lines = ["[Librarian] Project reference for query «%s»:" % q]
    if syn_used:
        lines.append("(gamedev synonyms also searched: %s)" % ", ".join(syn_used))
    base_len = len(lines)  # сколько строк было ДО слоёв — для детекта пустого ответа
    # v105.13 (п.1): если проект не влез в потолок индекса, модель обязана это знать:
    # раньше ответ по половине проекта выглядел ровно так же, как полный, а
    # «nothing found» читалось как «такого в проекте нет». Строка идёт ПОСЛЕ base_len
    # (то есть в теле ответа) и учитывается в детекте пустоты отдельно (warn_len):
    # предупреждение — не данные и не должно превращать пустой ответ в непустой.
    # Специально обычная строка lines, а не отдельный хвост после обрезки:
    # иначе она не попадала бы под учёт char budget и ответ мог бы вылезть за него.
    try:
        _meta = ml_project_index.index_meta(project_root)
    except Exception:
        _meta = {}  # предупреждение не должно убить ответ
    index_truncated = bool(_meta.get("truncated"))
    if index_truncated:
        lines.append("⚠ project index incomplete: %d files not indexed "
                     "(project exceeds the index limit) — results may miss some files."
                     % int(_meta.get("skipped_files") or 0))
    warn_len = 1 if index_truncated else 0
    if hits:
        lines.append("MAP (most relevant files, best first):")
        for h in hits:
            syms = ", ".join(h.get("symbols", [])[:10])
            lines.append("- res://%s%s" % (h["path"], (" — " + syms) if syms else ""))
    try:
        auto_lines = _autoload_lines(project_root, q)
    except Exception:
        auto_lines = []  # патч 4 не должен убить ответ целиком
    if auto_lines:
        lines.append("AUTOLOADS (global singletons from project.godot):")
        lines += auto_lines
    # v105.10 (шаг 5): оставались единственными необёрнутыми слоями —
    # сбой чтения одного файла убивал весь ответ, включая уже собранный MAP.
    try:
        struct_lines = _structure(project_root, hits)
    except Exception:
        struct_lines = []
    if struct_lines:
        lines.append("STRUCTURE (declarations with line numbers):")
        lines += struct_lines
    try:
        frag_lines = _fragments(project_root, q)
    except Exception:
        frag_lines = []
    if frag_lines:
        lines.append("FRAGMENTS (verbatim matches):")
        lines += frag_lines
    try:
        caller_lines = _callers(project_root, q, hits)
    except Exception:
        caller_lines = []  # патч 3 не должен убить ответ целиком
    if caller_lines:
        lines.append("CALLERS (call sites of exactly matched functions, definition excluded):")
        lines += caller_lines
    try:
        signal_lines = _signal_wiring(project_root, q, hits)
    except Exception:
        signal_lines = []  # патч 4 не должен убить ответ целиком
    if signal_lines:
        lines.append("SIGNALS (scene connections and emit sites of exactly matched signals):")
        lines += signal_lines
    # v105.15: последний необёрнутый слой. Внутри _godot_api try закрывает
    # только обращения к кэшу (has_cache/get_class/collect_members), а
    # _pick_members стоит уже вне его: нестроковое имя члена в кэше роняло
    # n.lower() и уносило ВЕСЬ собранный ответ (MAP, STRUCTURE, FRAGMENTS)
    # в except main.py — пользователь видел «internal error» вместо справки.
    try:
        api_lines = _godot_api(project_root, q, addon_dir=addon_dir)
    except Exception:
        api_lines = []
    if api_lines:
        lines.append("GODOT API (from the project's API cache):")
        lines += api_lines
    # v105.13 (п.1): + warn_len — строка об усечении не считается данными,
    # иначе ответ без единого совпадения перестал бы попадать в ветку
    # «nothing matches» с подсказкой по похожим именам.
    if len(lines) == base_len + warn_len:
        try:
            near = _near_tokens(project_root, q)
        except Exception:
            near = []
        hint = (" Similar identifiers that DO exist in the project index: %s." %
                ", ".join(near)) if near else ""
        _no_match_rec = {"query": q, "result": "no_matches",
                         "synonyms": syn_used, "near": near}
        if index_truncated:
            # Поле добавляется ТОЛЬКО при усечении: записи журнала на обычных
            # проектах остаются такими же, как до патча. Здесь это важнее
            # всего: «no_matches» на усечённом индексе может означать не то,
            # что файла нет, а что он отброшен по лимиту.
            _no_match_rec["index_truncated"] = True
        _log_query(project_root, _no_match_rec)
        return ("[Librarian]: nothing in the project index matches «%s». Try other English "
                "terms (synonyms of function/class/signal/node names), or search_project for "
                "literal text, or list_files for a directory tree.%s" % (q, hint))
    # v105.10 (шаг 5): докстринг обещает «никогда не бросает наружу», но
    # int(None) давал TypeError, а int("много") — ValueError уже ПОСЛЕ всей
    # работы: ответ был готов, но терялся. Плохое значение — не повод
    # выбрасывать справку; тихо откатываемся к дефолту.
    try:
        _budget_req = int(budget_chars)
    except (TypeError, ValueError):
        _budget_req = CHAR_BUDGET
    # v105.10 (шаг 8): max(1000, ...) молча игнорировал меньшие бюджеты:
    # budget_chars=500 и 1000 давали один и тот же ответ. Нижний порог
    # остаётся, но маленький — чтобы всегда влезали шапка и FOOTER.
    budget = max(_MIN_BUDGET, _budget_req) - len(FOOTER) - 8
    total, kept, cut = 0, [], False
    for ln in lines:
        if total + len(ln) + 1 > budget:
            cut = True
            break
        kept.append(ln)
        total += len(ln) + 1
    if cut:
        # v105.10 (шаг 8): если обрезало сразу после заголовка секции,
        # в ответе оставался «FRAGMENTS (...):» без единой строки — модель
        # видела пустую секцию вместо «здесь было больше».
        # v105.10 (шаг 8): два условия решаются ОДНИМ циклом до стабилизации:
        # сначала освободить место под саму пометку (раньше её добавляли
        # ПОСЛЕ проверки, и ответ вылезал за бюджет), потом убрать висячий
        # заголовок секции. Раздельные циклы не работают: подгонка под
        # пометку снова оголяет заголовок, а удаление заголовка меняет длину.
        while kept and (total + len(_TRUNC_NOTE) + 1 > budget
                        or _is_section_header(kept[-1])):
            total -= len(kept[-1]) + 1
            kept.pop()
        kept.append(_TRUNC_NOTE)
    # v105.11 (раунд 3, п.5): при budget_chars 0–400 от ответа оставалась
    # только шапка и пометка об усечении — ноль данных, но в телеметрию
    # шло result: "ok". По журналу такой вызов был неотличим от успешного,
    # и проблема настройки не видна при разборе обкатки.
    has_content = any(str(ln).startswith(("- ", "  ", "res://")) for ln in kept)
    if cut and not has_content and kept:
        kept[-1] = _BUDGET_NOTE  # честнее, чем «truncated»: данных не было вовсе
    kept.append(FOOTER)
    text = "\n".join(kept)
    _rec = {
        "query": q, "result": "ok" if has_content else "empty_budget",
        "hits": len(hits), "synonyms": syn_used,
        "sections": [n for n in _LOG_SECTIONS if any(ln.startswith(n + " (") for ln in kept)],
        "chars": len(text), "cut": cut,
    }
    if index_truncated:
        # v105.13 (п.1): чтобы неполнота индекса была видна при разборе
        # обкатки, а не только в тексте ответа (его в журнал не пишем).
        _rec["index_truncated"] = True
    _log_query(project_root, _rec)
    return text


def note_files_changed(project_root, changed=(), deleted=()):
    """Микро-обновление индекса по путям res:// или относительным путям —
    вызывается после каждой записи агента (_apply_write_step, copy_file) и
    при внешних правках (_external_changes_note). Ошибки глотаются: индекс
    в худшем случае достроится лениво при следующем поиске (STALE_SEC)."""
    def _rels(paths):
        out = []
        for p in paths or ():
            r = str(p or "").replace("res://", "").replace("\\", "/").strip("/")
            if r:
                out.append(r)
        return out
    try:
        ml_project_index.update_entries(project_root, _rels(changed), _rels(deleted))
    except Exception:
        pass
