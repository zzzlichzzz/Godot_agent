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
diff_card = read(_os0.path.join(ADDON, "DiffPreviewCard.gd"))
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
API_SIGNALS = ["api_chat_model_requested", "api_models_refresh_requested",
               "api_models_scan_requested", "api_settings_save_requested",
               "api_tab_requested", "api_test_requested",
               "new_api_chat_requested"]
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

check(u"chat request привязан к открытому chat id",
      '"chat_id": _current_chat_id' in panel)
check(u"поле ввода очищается централизованно и возвращает фокус",
      "func _clear_chat_input" in panel
      and 'call_deferred("grab_focus")' in panel
      and "_restore_chat_draft()" in panel)
check(u"повтор после site mismatch привязан к chat generation",
      "_site_resend_envelope" in panel
      and "_chat_navigation_generation" in panel
      and "_resend_after_open" not in panel)
check(u"черновики разделены между чатами",
      "_chat_drafts" in panel and "func _switch_chat_draft" in panel)
check(u"ошибка сохранения transcript видна пользователю",
      "transcript_warning" in panel)
response_pos = link.find("chats_response.emit(kind, json, extra)")
drain_pos = link.find('call_deferred("_drain_queue")', response_pos)
check(u"очередь навигации запускается после передачи ответа панели",
      response_pos >= 0 and drain_pos > response_pos)
check(u"HTTP-ошибка навигации передаётся панели без автозапуска сервера",
      "response_code != 200" in link
      and "chats_response.emit(kind, failure, extra)" in link)

# --- 8) Контекст живого редактора передаётся только как read-only снимок ---
context_path = _os0.path.join(ADDON, "agent_editor_context.gd")
check(u"сборщик контекста редактора существует", _os0.path.isfile(context_path))
context_src = read(context_path) if _os0.path.isfile(context_path) else ""
check(u"снимок имеет версию схемы", "SCHEMA_VERSION" in context_src)
send_chat = re.search(r"func _send_chat_raw\(.*?(?=\nfunc )", panel, re.DOTALL)
send_chat_src = send_chat.group(0) if send_chat else ""
check(u"снимок прикрепляется к /chat", 'body["editor_context"]' in send_chat_src)
mutating_context_calls = [call for call in (
    "ResourceSaver.save", "set_setting(", "open_scene_from_path(",
    "edit_script(", "FileAccess.WRITE") if call in context_src]
check(u"сборщик контекста не изменяет проект", not mutating_context_calls,
      mutating_context_calls)

# --- 9) русский текст из .tscn обязан переписываться из словаря ---
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

# --- 10) Несколько ключей на провайдера ---
#
# Квота бесплатных тарифов считается НА КЛЮЧ, поэтому второй аккаунт того же
# сервиса — рабочий способ продолжить работу. Панель обязана уметь ДОПИСАТЬ
# ключ, удалить один из списка и снять пометки «исчерпан».
_key_save = re.search(r"func _on_api_detail_key_save\(\).*?(?=\nfunc )",
                      start, re.DOTALL)
check(u"обработчик сохранения ключа найден", _key_save is not None)
_save_body = _key_save.group(0) if _key_save else ""
check(u"поле ключа ДОПИСЫВАЕТ ключ (add_key)", '"add_key"' in _save_body)
# ГЛАВНАЯ проверка этого раздела. Маршрут "key" на сервере ЗАМЕНЯЕТ весь список
# одним ключом; пока панель его слала, попытка завести второй аккаунт молча
# стирала первый. Проверка не даёт вернуть эту ловушку по невнимательности.
check(u"панель НЕ отправляет замену всех ключей одним",
      '"key":' not in start and '"key" :' not in start,
      [ln.strip() for ln in start.split("\n") if '"key"' in ln][:3])
check(u"удаление идёт по ПОЗИЦИИ (сырых ключей панель не видит)",
      '"delete_key_index"' in start)
check(u"есть сброс пометок «исчерпан»", '"clear_cooldowns"' in start)
for _fn in ("_api_build_key_row", "_api_key_state_text",
            "_on_api_key_row_delete", "_on_api_keys_reset"):
    check(u"объявлен %s" % _fn,
          re.search(r"^func\s+%s\s*\(" % _fn, start, re.MULTILINE) is not None)
# Срок «можно пробовать через…» показывается только когда его НАЗВАЛ провайдер:
# своих догадок про сброс суточной квоты ни сервер, ни панель не делают.
check(u"срок повтора показывается только при until > 0",
      re.search(r"until\s*>\s*0", start) is not None)

check("rename plural diffs use read-only cards",
      'json.get("pending_action_diffs")' in panel and "add_readonly_diff" in panel
      and "mark_preview_only" in diff_card)
check("rename confirmation blocks dirty scripts",
      "_dirty_open_scripts(targets)" in panel)
check("rename result reloads every changed path",
      'json.get("changed_paths")' in panel and "for changed_path in changed_paths" in panel)
scene_executor = read(_os0.path.join(ADDON, "agent_scene_executor.gd"))
plugin = read(_os0.path.join(ADDON, "plugin_universal.gd"))
check("plugin injects EditorPlugin into panel", "set_editor_plugin" in plugin)
check("scene executor uses PackedScene API",
      "PackedScene.GEN_EDIT_STATE_INSTANCE" in scene_executor
      and "packed.pack(root)" in scene_executor and "ResourceSaver.save" in scene_executor)
check("scene execution matches confirmed preview",
      "semantic_hash" in scene_executor and "preview_mismatch" in scene_executor
      and "_pending_scene_semantic_hash" in panel)
check("scene executor owns structural operations",
      all(name in scene_executor for name in ("_add_node", "_set_node_property",
                                               "_attach_script", "_connect_signal",
                                               "_reparent_node")))
check("scene executor avoids textual scene writes and UndoRedo",
      "FileAccess.WRITE" not in scene_executor and "UndoRedo" not in scene_executor)
check("scene executor refuses open scenes without guessing dirty state",
      'return _fail("scene_open"' in scene_executor
      and "get_unsaved_scenes" not in scene_executor
      and "is_scene_unsaved" not in scene_executor)
check("scene executor creates typed scenes through PackedScene temp save",
      "_create_detached" in scene_executor
      and "ClassDB.instantiate" in scene_executor
      and '"create_scene"' in scene_executor
      and ".agent-create-" in scene_executor
      and '"staged_hash"' in scene_executor
      and '"target_written"' in scene_executor
      and "DirAccess.rename_absolute" not in scene_executor)
check("panel sends trusted Godot executable for engine validation",
      "OS.get_executable_path()" in panel and '"godot_executable"' in panel)
check("panel coordinates scene prepare execute finalize",
      all(name in panel for name in ("_prepare_scene_action", "_execute_scene_action",
                                     "_send_scene_result", "_pending_scene_semantic_hash",
                                     "_pending_scene_finalize_body", "scene_finalize")))
check("panel stops retrying terminal scene finalize failures",
      'if response_code in [400, 403, 409, 410, 413]:' in panel
      and '_pending_scene_finalize_body = {}' in panel)
settings_executor = read(_os0.path.join(ADDON, "agent_project_settings_executor.gd"))
check("project settings executor uses Godot APIs",
      "ProjectSettings.set_setting" in settings_executor
      and "ProjectSettings.save" in settings_executor
      and "add_autoload_singleton" in settings_executor
      and "InputEventKey.new" in settings_executor)
check("project settings executor plans idempotent operations",
      "effective_operations" in settings_executor
      and "autoload_conflict" in settings_executor
      and "текущие deadzone и события сохранены" in settings_executor
      and '"apply": false' in settings_executor
      and "_apply(effective_operations)" in settings_executor)
check("project settings executor avoids textual writes and UndoRedo",
      "FileAccess.WRITE" not in settings_executor and "UndoRedo" not in settings_executor)
check("new executors avoid invalid static hashing and void return checks",
      all("HashingContext.hash(" not in src for src in
          (scene_executor, settings_executor))
      and not re.search(r"var\s+\w+\s*:?=\s*_plugin\.(?:add|remove)_autoload_singleton", settings_executor))
reserved_locals = []
for path in GD_FILES:
    text = read(path)
    for match in re.finditer(r"\bvar\s+(class_name)\b", text):
        reserved_locals.append((_os0.path.basename(path), match.group(1)))
check("зарезервированное class_name не используется как local variable",
      not reserved_locals, reserved_locals)
panel_script_paths = re.findall(
    r"var\s+\w+_path\s*([^\n=]*?)=\s*get_script\(\)\.resource_path", panel)
check("пути от get_script resource_path имеют явный String type",
      panel_script_paths and all(": String" in prefix for prefix in panel_script_paths),
      panel_script_paths)
check("panel coordinates project settings transaction",
      all(name in panel for name in ("_prepare_project_settings_action",
                                     "_execute_project_settings_action",
                                     "project_settings_finalize",
                                     "_pending_project_settings_semantic_hash",
                                       "agent_project_settings_executor.gd")))
check("panel retains settings finalize until a terminal result",
      all(name in panel for name in ("_pending_project_settings_finalize_body",
                                     "func _send_pending_project_settings_finalize",
                                     "func _schedule_project_settings_finalize_retry"))
      and "_send_pending_project_settings_finalize()" in panel[panel.find("func _on_play_watch_tick"):])
check("file operations never close user scenes automatically",
      'call("close_scene")' not in panel and "func _close_scenes_before_write" not in panel
       and "_open_pending_scene_paths()" in panel)
dirty_helper = panel[panel.find("func _dirty_open_scripts"):panel.find("func _sync_open_script_with_disk")]
check("dirty script safety does not call unavailable resource accessor",
      "editor.get_edited_resource(" not in dirty_helper
      and "get_open_scripts()" in dirty_helper and "get_open_script_editors()" in dirty_helper
      and "get_saved_version()" in dirty_helper)
autoreload_helper = panel[panel.find("func _ensure_script_autoreload_setting"):panel.find("func _force_reload_open_script")]
check("plugin does not silently change script autoreload preference",
      "set_setting(" not in autoreload_helper)
for finalize_kind in ("resource_finalize", "project_settings_finalize"):
    failure_branch = panel[panel.rfind('if kind == "%s":' % finalize_kind):]
    check("terminal %s is not retried forever" % finalize_kind,
          'if response_code in [400, 403, 409, 410, 413]:' in failure_branch.split("\n\t\tif kind ==", 1)[0])
resource_executor = read(_os0.path.join(ADDON, "agent_resource_executor.gd"))
check("resource executor avoids invalid static hashing",
      "HashingContext.hash(" not in resource_executor)
check("resource executor uses detached Godot resource APIs",
      "ResourceLoader.load" in resource_executor and "ResourceSaver.save" in resource_executor
      and "ResourceLoader.CACHE_MODE_IGNORE" in resource_executor)
check("resource executor supports specialized editors",
      all(name in resource_executor for name in ("_animation_add_value_track",
                                                  "_sprite_frames_add_animation",
                                                  "_theme_set_item",
                                                  "_tileset_add_atlas_source")))
check("resource executor tracks imports previews and semantic state",
      "dependency_fingerprint" in resource_executor and "semantic_hash" in resource_executor
       and "queue_resource_preview" in resource_executor and "check_for_invalidation" in resource_executor)
check("resource executor validates staged save and preserves recovery evidence",
      "temporary_semantic_mismatch" in resource_executor
      and "DirAccess.rename_absolute" in resource_executor
      and "saved_semantic_mismatch" in resource_executor
      and "canonical_path" in resource_executor)
check("resource executor avoids textual writes and UndoRedo",
      "FileAccess.WRITE" not in resource_executor and "UndoRedo" not in resource_executor)
check("panel coordinates resource transaction",
      all(name in panel for name in ("_prepare_resource_action", "_execute_resource_action",
                                     "resource_finalize", "_pending_resource_semantic_hash",
                                      "agent_resource_executor.gd")))
check("panel retries retained resource finalize envelope",
      "_pending_resource_finalize_body" in panel
      and "_schedule_resource_finalize_retry" in panel
      and "not _pending_resource_finalize_body.is_empty()" in panel[panel.find("func _has_pending_action"):]
      and "_send_pending_resource_finalize()" in panel[panel.find("func _on_play_watch_tick"):])
check("panel explicitly dispatches all editor transaction kinds",
      all(value in panel for value in ('editor_action_kind == "scene"',
                                       'editor_action_kind == "project_settings"',
                                       'editor_action_kind == "resource"')))
runtime_debugger = read(_os0.path.join(ADDON, "agent_runtime_debugger.gd"))
runtime_bridge = read(_os0.path.join(ADDON, "agent_runtime_bridge.gd"))
check("runtime error assertion uses only current check errors",
      '_errors_since(int(_check.get("error_cursor", 0))).is_empty()' in runtime_bridge)
check("plugin registers and removes runtime debugger",
      "add_debugger_plugin" in plugin and "remove_debugger_plugin" in plugin
      and "set_runtime_debugger" in plugin)
check("runtime debugger uses public capture protocol",
      "extends EditorDebuggerPlugin" in runtime_debugger
      and "_has_capture" in runtime_debugger and "_capture" in runtime_debugger
      and 'NAMESPACE + ":inspect"' in runtime_debugger
      and "session.is_active()" in runtime_debugger
      and '"result_token"' not in runtime_debugger)
check("runtime bridge is debug-only and read-only",
      "OS.is_debug_build()" in runtime_bridge and "EngineDebugger.is_active()" in runtime_bridge
      and "register_message_capture" in runtime_bridge
      and all(name not in runtime_bridge for name in ("set_property", "queue_free(", "change_scene_to", "UndoRedo")))
check("panel sends compact runtime status and handles bounded result",
      '"runtime_status": _runtime_status' in panel
      and "_start_runtime_inspect" in panel and "RUNTIME_RESULT_URL" in panel
      and "_pending_runtime_request" in panel)
check("automatic runtime log setup is read-only",
      "ProjectSettings.save()" not in panel[panel.find("func _ensure_file_logging_enabled"):panel.find("func _start_progress_poll")])
check("runtime debugger supports deterministic checks",
      'NAMESPACE + ":run_check"' in runtime_debugger
      and "check_completed" in runtime_debugger and "run_check_v1" in runtime_debugger)
check("runtime bridge executes bounded InputMap checks",
      "InputEventAction.new" in runtime_bridge and "InputMap.has_action" in runtime_bridge
      and "_run_check_steps" in runtime_bridge and "_release_inputs" in runtime_bridge
      and "_error_sequence" in runtime_bridge and "MAX_CHECK_RESULT_BYTES" in runtime_bridge
      and all(value not in runtime_bridge for value in ("InputEventKey.new", "InputEventMouseButton.new")))
check("panel refuses unprovable runtime ownership without starting or stopping games",
       "EditorInterface.play_custom_scene" not in panel and "EditorInterface.stop_playing_scene" not in panel
       and "RUNTIME_CHECK_RESULT_URL" in panel and '"bridge_unavailable"' in panel
       and "_pending_runtime_check_result_body" in panel
       and "func _exit_tree" in panel)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
