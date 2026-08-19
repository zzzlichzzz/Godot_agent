# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Проверки GDScript-части, которые нельзя сделать без запуска Godot.

Зачем этот тест. Пропущенный ключ локализации НЕ роняет плагин — вместо текста
пользователь просто видит имя ключа («api_key_save»), и заметить это можно
только глазами, на нужном языке, в нужном подразделе. То же с опечаткой в имени
обработчика сигнала: ошибка всплывёт в рантайме, когда пользователь нажмёт
кнопку. Здесь это ловится статически.

Проверяется:
  1. каждый _t("ключ") из .gd существует и в RU, и в EN;
  2. наборы ключей RU и EN совпадают (нет забытого перевода);
  3. количество и порядок подстановок (%s/%d) в RU и EN совпадают — иначе
     строка с форматированием упадёт или подставит не то;
  4. каждый обработчик, переданный в .connect(), объявлен в том же файле.
"""
import glob
import re
import sys

results = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail:
        print("     %s" % (detail,))
    results.append(bool(cond))


ADDON = _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir, _os0.pardir))
GD_FILES = sorted(glob.glob(_os0.path.join(ADDON, "*.gd")))
LOCALE = _os0.path.join(ADDON, "agent_locale.gd")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


check(u"файлы .gd найдены", len(GD_FILES) >= 10, len(GD_FILES))
check(u"agent_locale.gd найден", _os0.path.isfile(LOCALE))

src_locale = read(LOCALE)


def dict_block(name):
    """Тело словаря const NAME := { ... } до закрывающей скобки в начале строки."""
    m = re.search(r"const\s+%s\s*:?=\s*\{" % name, src_locale)
    if not m:
        return ""
    start = m.end()
    end = src_locale.find("\n}", start)
    return src_locale[start:end if end > 0 else len(src_locale)]


def keys_of(block):
    return set(re.findall(r'^\s*"([A-Za-z0-9_]+)"\s*:', block, re.MULTILINE))


def entries_of(block):
    return dict(re.findall(r'^\s*"([A-Za-z0-9_]+)"\s*:\s*"(.*?)",?\s*$',
                           block, re.MULTILINE))


ru_block, en_block = dict_block("RU"), dict_block("EN")
RU, EN = keys_of(ru_block), keys_of(en_block)
check(u"словарь RU разобран", len(RU) > 100, len(RU))
check(u"словарь EN разобран", len(EN) > 100, len(EN))

only_ru = sorted(RU - EN)
only_en = sorted(EN - RU)
check(u"нет ключей без английского перевода", not only_ru, only_ru)
check(u"нет ключей без русского перевода", not only_en, only_en)

# --- 1) все используемые ключи существуют ---
used = {}
for path in GD_FILES:
    for key in re.findall(r'_t\(\s*"([A-Za-z0-9_]+)"', read(path)):
        used.setdefault(key, set()).add(_os0.path.basename(path))
check(u"ключи локализации используются", len(used) > 50, len(used))

missing = sorted(k for k in used if k not in RU)
check(u"все используемые ключи есть в RU", not missing,
      [(k, sorted(used[k])) for k in missing])
missing_en = sorted(k for k in used if k not in EN)
check(u"все используемые ключи есть в EN", not missing_en,
      [(k, sorted(used[k])) for k in missing_en])

# --- 2) подстановки совпадают между языками ---
ru_e, en_e = entries_of(ru_block), entries_of(en_block)
_FMT_RE = re.compile(r"%[sdfx]")
bad_fmt = []
for key in sorted(set(ru_e) & set(en_e)):
    a = _FMT_RE.findall(ru_e[key])
    b = _FMT_RE.findall(en_e[key])
    if a != b:
        bad_fmt.append((key, a, b))
check(u"подстановки %s/%d одинаковы в RU и EN", not bad_fmt, bad_fmt)

# Строки с подстановками должны применяться с оператором % — иначе
# пользователь увидит сырое «%s» в интерфейсе.
fmt_keys = sorted(k for k in ru_e if _FMT_RE.search(ru_e[k]))
check(u"есть строки с подстановками", len(fmt_keys) > 5, len(fmt_keys))
unformatted = []
for path in GD_FILES:
    text = read(path)
    for key in fmt_keys:
        for m in re.finditer(r'_t\(\s*"%s"\s*\)' % re.escape(key), text):
            tail = text[m.end():m.end() + 4]
            if not tail.lstrip().startswith("%"):
                unformatted.append((_os0.path.basename(path), key))
check(u"строки с подстановками нигде не выводятся без %", not unformatted,
      unformatted)

# --- 3) обработчики сигналов объявлены ---
missing_handlers = []
for path in GD_FILES:
    text = read(path)
    defined = set(re.findall(r"^func\s+([A-Za-z0-9_]+)\s*\(", text, re.MULTILINE))
    for m in re.finditer(r"\.connect\(\s*(_[A-Za-z0-9_]+)\s*[\),]", text):
        name = m.group(1)
        if name not in defined:
            missing_handlers.append((_os0.path.basename(path), name))
check(u"все обработчики из .connect() объявлены в своём файле",
      not missing_handlers, missing_handlers)

# --- 4) сигналы стартового экрана и их подключения в панели ---
start = read(_os0.path.join(ADDON, "agent_start_screen.gd"))
panel = read(_os0.path.join(ADDON, "agent_panel.gd"))
declared = set(re.findall(r"^signal\s+([A-Za-z0-9_]+)", start, re.MULTILINE))
emitted = set(re.findall(r"([A-Za-z0-9_]+)\.emit\(", start))
check(u"сигналы стартового экрана объявлены", len(declared) >= 12, sorted(declared))
undeclared = sorted(e for e in emitted
                    if e not in declared and not e.startswith("_"))
check(u"нет emit несуществующего сигнала", not undeclared, undeclared)

api_signals = sorted(s for s in declared if s.startswith("api_")
                     or s.startswith("new_api"))
# Список ЯВНЫЙ, а не «столько-то штук»: новый сигнал работы по ключу обязан
# попасть сюда осознанно, а число рядом с ним ничего не рассказывает тому, кто
# увидит падение теста. Проверка ловит две противоположные ошибки: сигнал
# объявили и забыли подключить (следующая проверка) и сигнал переименовали,
# оставив подключение по старому имени.
API_SIGNALS = ["api_models_refresh_requested", "api_models_scan_requested",
               "api_settings_save_requested", "api_tab_requested",
               "api_test_requested", "new_api_chat_requested"]
check(u"сигналы работы по ключу объявлены", api_signals == API_SIGNALS,
      api_signals)
not_connected = [s for s in api_signals if (s + ".connect") not in panel]
check(u"все сигналы работы по ключу подключены в панели", not not_connected,
      not_connected)

# --- 5) методы, которые панель вызывает у стартового экрана ---
start_funcs = set(re.findall(r"^func\s+([A-Za-z0-9_]+)\s*\(", start, re.MULTILINE))
called = set(re.findall(r'_start_screen\.has_method\(\s*"([A-Za-z0-9_]+)"', panel))
called |= set(re.findall(r"_start_screen\.([A-Za-z0-9_]+)\(", panel))
absent = sorted(c for c in called if c not in start_funcs
                and c not in ("has_method", "has_signal", "connect",
                              "set_anchors_preset"))
check(u"панель вызывает только существующие методы экрана", not absent, absent)

# --- 6) виды запросов панели поддержаны транспортом ---
link = read(_os0.path.join(ADDON, "agent_server_link.gd"))
kinds = set(re.findall(r'_request_chats\(\s*"([a-z_]+)"', panel))
kinds |= set(re.findall(r'call_deferred\("_request_chats",\s*"([a-z_]+)"', panel))
match_block = link[link.find("match kind:"):]
match_block = match_block[:match_block.find("\n\t_kind = kind")]
routed = set(re.findall(r'"([a-z_]+)":\s*url\s*=', match_block))
routed.add("list")  # значение по умолчанию url := CHATS_LIST_URL
unrouted = sorted(k for k in kinds if k not in routed)
check(u"каждый вид запроса имеет адрес в транспорте", not unrouted, unrouted)
check(u"виды запросов работы по ключу разведены",
      {"api_providers", "api_set", "api_models", "api_scan",
       "api_test"} <= routed,
      sorted(routed))

# --- 7) токен на порт 5000 ---
# Забытый заголовок означает 403 на КАЖДЫЙ запрос после привязки сервера, то
# есть плагин, сломанный целиком. Сырые заголовки допустимы ТОЛЬКО внутри
# функций сборки заголовков (_json_headers / json_headers) — там это запасной
# путь на случай отсутствия файла токена.
def _func_spans(text, names):
    """Диапазоны (начало, конец) тел указанных функций."""
    spans = []
    for m in re.finditer(r"^(?:static )?func ([A-Za-z0-9_]+)\s*\(",
                         text, re.MULTILINE):
        if m.group(1) not in names:
            continue
        nxt = re.search(r"^(?:static )?func ", text[m.end():], re.MULTILINE)
        end = m.end() + (nxt.start() if nxt else len(text) - m.end())
        spans.append((m.start(), end))
    return spans


ALLOWED = {"_json_headers", "json_headers"}
raw_headers = []
for path in GD_FILES:
    text = read(path)
    spans = _func_spans(text, ALLOWED)
    for m in re.finditer(r'\[\s*"Content-Type: application/json"\s*\]', text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        raw_headers.append((_os0.path.basename(path),
                            text[:m.start()].count("\n") + 1))
check(u"заголовки без токена остались только в сборщике заголовков",
      not raw_headers, raw_headers)
check(u"сборщик заголовков в панели найден",
      bool(_func_spans(panel, {"_json_headers"})))

# Запрос БЕЗ заголовков вообще — самая коварная форма той же ошибки: сервер
# ответит 403, а панель не-200 в ответе прогресса молча игнорирует, и живая
# трансляция перестанет работать без единого сообщения. Именно так и было с
# _progress_http.request(PROGRESS_URL).
headerless = []
for path in GD_FILES:
    text = read(path)
    for m in re.finditer(r"\.request\(\s*[A-Za-z0-9_]+\s*\)", text):
        headerless.append((_os0.path.basename(path),
                           text[:m.start()].count("\n") + 1,
                           m.group(0)))
check(u"нет HTTP-запросов вообще без заголовков", not headerless, headerless)

# Каждая функция панели, шлющая запрос, обязана брать заголовки у сборщика.
missing_token = []
for m in re.finditer(r"^func ([A-Za-z0-9_]+)\s*\(", panel, re.MULTILINE):
    nxt = re.search(r"^func ", panel[m.end():], re.MULTILINE)
    body = panel[m.end():m.end() + (nxt.start() if nxt else len(panel))]
    if ".request(" not in body:
        continue
    if m.group(1) in ("_json_headers", "_request_chats"):
        continue
    if "_json_headers()" not in body:
        missing_token.append(m.group(1))
check(u"каждая отправляющая функция берёт заголовки у сборщика",
      not missing_token, missing_token)

tok_panel = re.search(r'const TOKEN_FILE\s*:?=\s*"([^"]+)"', panel)
tok_link = re.search(r'const TOKEN_FILE\s*:?=\s*"([^"]+)"', link)
check(u"путь к файлу токена задан в обоих файлах",
      bool(tok_panel) and bool(tok_link))
check(u"путь к файлу токена совпадает",
      bool(tok_panel) and bool(tok_link)
      and tok_panel.group(1) == tok_link.group(1),
      (tok_panel.group(1) if tok_panel else None,
       tok_link.group(1) if tok_link else None))

# Имя заголовка должно совпадать с серверным server_auth.HEADER.
import server_auth
hdr_link = re.search(r'const TOKEN_HEADER\s*:?=\s*"([^"]+)"', link)
check(u"имя заголовка токена совпадает с серверным",
      bool(hdr_link) and hdr_link.group(1) == server_auth.HEADER,
      (hdr_link.group(1) if hdr_link else None, server_auth.HEADER))
check(u"панель шлёт заголовок с тем же именем",
      ('"' + server_auth.HEADER + ': "') in panel
      or (server_auth.HEADER + ': "') in panel)

# Токен берётся у ЭКЗЕМПЛЯРА узла, а не у загруженного скрипта: has_method()
# объекта GDScript не даёт надёжного ответа про пользовательские static func.
check(u"панель не спрашивает has_method у загруженного скрипта транспорта",
      not re.search(r'load\([^)]*agent_server_link[^)]*\)\s*\n?\s*.*has_method',
                    panel))
check(u"панель берёт токен у узла ServerLink",
      "_link.project_token()" in panel)

# --- 8) русский текст из .tscn обязан переписываться из словаря ---
#
# РЕАЛЬНАЯ ПОЛОМКА, из-за которой эта проверка написана. Надписи карточек лежат
# в .tscn по-русски — так их видно в редакторе сцен, и это удобно. Но значение из
# .tscn остаётся НА ЭКРАНЕ, пока код его не перепишет, а переписать его никто не
# обязан. Замерено на английском языке: 13 надписей оставались русскими, в том
# числе кнопки «Применить», «Отклонить», «Пауза», «Продолжить», «Откатить
# цепочку» и подписи авторов сообщений «Вы» и «ИИ-Агент».
#
# Заметить это глазами почти невозможно: надо переключить язык, довести агента до
# показа диффа или плана и посмотреть именно на эти кнопки. Здесь то же ловится
# статически: для каждой русской надписи в .tscn требуем в парном .gd
# присваивание этому же свойству из _t().
_UI_PROPS = ("text", "tooltip_text", "placeholder_text")
_CYR = re.compile(u"[\u0400-\u04ff]")
scenes = sorted(glob.glob(_os0.path.join(ADDON, "*.tscn")))
check(u"файлы сцен найдены", len(scenes) >= 5, len(scenes))

unlocalized = []
checked_pairs = 0
for scene in scenes:
    stem = _os0.path.splitext(_os0.path.basename(scene))[0]
    gd_path = _os0.path.join(ADDON, stem + ".gd")
    src_scene = read(scene)
    # Сцена без парного скрипта: переписать надпись некому в принципе.
    gd = read(gd_path) if _os0.path.isfile(gd_path) else ""
    # Имя узла -> имя переменной, к которой его привязал @onready.
    node_var = {}
    for m in re.finditer(r"@onready\s+var\s+([A-Za-z0-9_]+)\s*:[^=]*=\s*\$([^\s#]+)",
                         gd):
        node_var[m.group(2).split("/")[-1]] = m.group(1)
    node = ""
    for line in src_scene.split("\n"):
        m = re.match(r'\[node name="([^"]+)"', line)
        if m:
            node = m.group(1)
            continue
        m = re.match(r'^(%s)\s*=\s*"(.*)"$' % "|".join(_UI_PROPS), line)
        if not m or not _CYR.search(m.group(2)):
            continue
        prop, text = m.group(1), m.group(2)
        checked_pairs += 1
        var = node_var.get(node, "")
        # Присваивание из словаря этому же свойству. Ищем в парном .gd, а также
        # в agent_panel.gd: он переписывает подписи своего дока сам
        # (_on_language_changed), а узлы объявлены там же.
        pat = re.compile(r"\b%s\.%s\s*=\s*[^\n#]*_t\(" % (re.escape(var), prop)) \
            if var else None
        if var and pat.search(gd):
            continue
        unlocalized.append("%s/%s.%s = %s" % (stem, node, prop, text[:40]))
check(u"русский текст из .tscn переписывается из словаря", not unlocalized,
      unlocalized)
check(u"проверка нашла надписи, которые надо переписывать", checked_pairs >= 8,
      checked_pairs)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
