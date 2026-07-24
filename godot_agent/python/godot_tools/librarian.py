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
API_CLASSES = 2       # слой 4: максимум классов Godot в ответе
API_MEMBERS = 14      # слой 4: максимум членов класса в одной строке

_FUNC_LINE_RE = re.compile(r"^\s*(?:static\s+)?func\s+[A-Za-z_]\w*\s*[(]")
_DECL_LINE_RE = re.compile(r"^\s*(?:class_name\s+\w+|extends\s+\S+|signal\s+\w+)")
# v105.7: топ-уровневые var/const/@export в STRUCTURE (без отступа — локальные не шумят)
_VARDECL_LINE_RE = re.compile(r"^(?:@[^\n]*?\s+)?(?:var|const)\s+[A-Za-z_]\w*")
_CLASS_TOKEN_RE = re.compile(r"\b([A-Z][A-Za-z0-9]{2,})\b")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Слова запроса, бесполезные для дословного поиска по коду (слой 3).
_STOPWORDS = {
    "the", "and", "for", "with", "where", "when", "how", "what", "from",
    "this", "that", "into", "does", "are", "not", "all", "any",
    "file", "files", "code", "find", "search", "look", "project",
    "func", "function", "functions", "var", "class", "signal",
}

# --- Патч 1: словарь геймдев-синонимов -------------------------------------
# Чистые данные, ноль зависимостей. Ра��отает в двух местах:
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
    ask_librarian — без лишнего ��руга через пользователя."""
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


def _is_addon_rel(path):
    """True для путей внутри res://addons/... — библиотекарь их не выдаёт
    (та же политика, что _is_addon_path в main.py: аддоны — только по явной
    просьбе ��ользователя, а до библиотекаря она не доходит)."""
    p = str(path or "").replace("\\", "/")
    if p.startswith("res://"):
        p = p[len("res://"):]
    return p.lstrip("/").startswith("addons/")


def _query_tokens(query):
    """Токены запроса для дословного поиска: без стоп-слов, длинные первыми."""
    seen, out = set(), []
    for t in re.split(r"[^A-Za-z0-9_]+", str(query or "")):
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
    for t in re.split(r"[^A-Za-z0-9_]+", str(query or "")):
        for p in _CAMEL_RE.sub(" ", t).replace("_", " ").split():
            pl = p.lower()
            if len(pl) >= 3 and pl not in _STOPWORDS:
                subs.add(pl)
    return subs


def _gd_signatures(project_root, godot_path, limit=SIG_PER_FILE):
    """Строки-объявления .gd с номерами строк: class_name/extends/signal/func."""
    try:
        content, _tr = read_project_file(project_root, godot_path, max_chars=200000)
    except Exception as e:
        return ["  (read error: %s)" % e]
    out = []
    for i, line in enumerate(content.splitlines(), 1):
        if (_FUNC_LINE_RE.match(line) or _DECL_LINE_RE.match(line)
                or _VARDECL_LINE_RE.match(line)):
            out.append("  L%d: %s" % (i, line.strip()))
            if len(out) >= limit:
                out.append("  … (more declarations omitted)")
                break
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


def _grep_token(project_root, tok, seen, out, frags_left):
    """Один дословный grep: складывает сниппеты в out, возвращает сколько добавил."""
    if frags_left <= 0:
        return 0
    try:
        results, _tr = search_project_text(project_root, tok, max_results=3, context_lines=1)
    except Exception:
        return 0
    added = 0
    for r in results:
        key = (r.get("path"), r.get("line"))
        if key in seen or _is_addon_rel(r.get("path", "")):
            continue
        seen.add(key)
        out.append("%s line %d (matched «%s»):" % (r["path"], r["line"], tok))
        out += ["  " + ln for ln in str(r.get("snippet", "")).splitlines()]
        added += 1
        if added >= frags_left:
            break
    return added


def _fragments(project_root, query):
    """Слой 3: дословные совпадения токенов запроса; если токен дословно не
    нашёлся — пробуем его геймдев-синонимы (патч 1), первый удачный."""
    seen, out, frags = set(), [], 0
    for tok in _query_tokens(query):
        added = _grep_token(project_root, tok, seen, out, FRAGMENT_LIMIT - frags)
        if added == 0 and tok.lower() != tok:
            # Багфикс v105.8: search_project_text регистрозависим — до синонимов
            # пробуем lowercase-вариант токена (Take_Damage -> take_damage),
            # чтобы FRAGMENTS был согласован с регистронезависимым MAP.
            added = _grep_token(project_root, tok.lower(), seen, out, FRAGMENT_LIMIT - frags)
        if added == 0:
            for syn in _synonyms(tok)[:_SYN_GREP_LIMIT]:
                added = _grep_token(project_root, syn, seen, out, FRAGMENT_LIMIT - frags)
                if added:
                    break
        frags += added
        if frags >= FRAGMENT_LIMIT:
            break
    return out


def _callers(project_root, query, hits):
    """Слой 3.5 (патч 3): обратные ссылки — места вызова функций, чьё имя
    ТОЧНО совпало с токеном запроса (по символам func: из карты).
    Закрывает типовой вопрос «кто это дёргает?» без двух-трёх read_file.
    Переиспользует search_project_text; строка-определение (func имя() фильтруется."""
    q_full = {t.lower() for t in re.split(r"[^A-Za-z0-9_]+", str(query or "")) if len(t) >= 3}
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
    out, shown = [], 0
    for name in names[:CALLERS_FUNCS]:
        def_re = re.compile(r"\bfunc\s+%s\s*[(]" % re.escape(name))
        try:
            results, _tr = search_project_text(project_root, name + "(", max_results=10, context_lines=0)
        except Exception:
            continue
        for r in results:
            snippet = str(r.get("snippet", "")).strip()
            if _is_addon_rel(r.get("path", "")) or def_re.search(snippet):
                continue  # определение — не вызов; аддоны не выдаём
            code = re.sub(r"^\d+:\s*", "", snippet)  # убрать префикс «N: » сниппета
            out.append("- %s line %d: %s" % (r["path"], r["line"], code))
            shown += 1
            if shown >= CALLERS_LIMIT:
                return out
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
    low = {t.lower() for t in re.split(r"[^A-Za-z0-9_]+", str(query or "")) if t}
    if not (low & _AUTOLOAD_KEYWORDS):
        subs = _query_subtokens(query)
        if not any(subs & _query_subtokens(name + " " + path.replace("/", " "))
                   for name, path in autos):
            return []
    return ["- %s -> %s" % (name, path) for name, path in autos]


def _signal_wiring(project_root, query, hits):
    """Слой 3.6 (патч 4): карта сигналов, чьё имя ТОЧНО совпало с токеном
    запроса: связи [connection ...] в .tscn + места эмита в .gd.
    Как и CALLERS — чистый дословный поиск, без парсинга кода."""
    q_full = {t.lower() for t in re.split(r"[^A-Za-z0-9_]+", str(query or "")) if len(t) >= 3}
    names = []
    for h in hits:
        for s in h.get("symbols", []):
            s = str(s)
            if s.startswith("signal:"):
                name = s[len("signal:"):]
                if name.lower() in q_full and name not in names:
                    names.append(name)
    out, shown = [], 0
    for name in names[:SIGNALS_MAX]:
        patterns = (('signal="%s"' % name, "scene connection"),
                    ("%s.emit" % name, "emit"),
                    ('emit_signal("%s"' % name, "emit"))
        for pattern, label in patterns:
            try:
                results, _tr = search_project_text(project_root, pattern, max_results=6, context_lines=0)
            except Exception:
                continue
            for r in results:
                if _is_addon_rel(r.get("path", "")):
                    continue
                code = re.sub(r"^\d+:\s*", "", str(r.get("snippet", "")).strip())
                line_txt = "- %s line %d (%s): %s" % (r["path"], r["line"], label, code)
                if line_txt in out:
                    continue
                out.append(line_txt)
                shown += 1
                if shown >= SIGNALS_LIMIT:
                    return out
    return out


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
    """Слой 4: члены классов Godot, упомянутых в з��просе (из кэша API)."""
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
    q = str(query or "").strip()
    if not q:
        return ("[Librarian]: empty \"query\". Resend: {\"action\": \"ask_librarian\", "
                "\"query\": \"English code terms: function/class/signal/node names and synonyms\"}.")
    q_expanded, syn_used = _expanded_query(q)
    try:
        hits = ml_project_index.search(project_root, q_expanded, limit=MAP_LIMIT * _RERANK_POOL)
    except Exception:
        hits = []
    hits = [h for h in hits if not _is_addon_rel(h.get("path", ""))]
    try:
        hits = _rerank_hits(hits, q, syn_used)[:MAP_LIMIT]
    except Exception:
        hits = hits[:MAP_LIMIT]  # патч 2 не должен убить ответ целиком
    lines = ["[Librarian] Project reference for query «%s»:" % q]
    if syn_used:
        lines.append("(gamedev synonyms also searched: %s)" % ", ".join(syn_used))
    base_len = len(lines)  # сколько строк было ДО ��лоёв — для детекта пустого ответа
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
    struct_lines = _structure(project_root, hits)
    if struct_lines:
        lines.append("STRUCTURE (declarations with line numbers):")
        lines += struct_lines
    frag_lines = _fragments(project_root, q)
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
    api_lines = _godot_api(project_root, q, addon_dir=addon_dir)
    if api_lines:
        lines.append("GODOT API (from the project's API cache):")
        lines += api_lines
    if len(lines) == base_len:
        try:
            near = _near_tokens(project_root, q)
        except Exception:
            near = []
        hint = (" Similar identifiers that DO exist in the project index: %s." %
                ", ".join(near)) if near else ""
        _log_query(project_root, {"query": q, "result": "no_matches",
                                  "synonyms": syn_used, "near": near})
        return ("[Librarian]: nothing in the project index matches «%s». Try other English "
                "terms (synonyms of function/class/signal/node names), or search_project for "
                "literal text, or list_files for a directory tree.%s" % (q, hint))
    budget = max(1000, int(budget_chars)) - len(FOOTER) - 8
    total, kept, cut = 0, [], False
    for ln in lines:
        total += len(ln) + 1
        if total > budget:
            cut = True
            break
        kept.append(ln)
    if cut:
        kept.append("… (truncated: char budget reached — refine the query to see more)")
    kept.append(FOOTER)
    text = "\n".join(kept)
    _log_query(project_root, {
        "query": q, "result": "ok", "hits": len(hits), "synonyms": syn_used,
        "sections": [n for n in _LOG_SECTIONS if any(ln.startswith(n + " (") for ln in kept)],
        "chars": len(text), "cut": cut,
    })
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
