# -*- coding: utf-8 -*-
"""agent_bridge.py — «альфа MCP» (v0): командный мост между внешней нейросетью
и плагином Godot_agent.

ЗАЧЕМ. Нейросеть, запущенная снаружи редактора (Cline, Cursor, руки человека),
должна получать АКТУАЛЬНЫЕ данные о проекте и о Godot API из тех же источников,
что и встроенный агент, а не полагаться на свою обучающую выборку. Мост
работает напрямую с модулями плагина (без запущенного сервера), поэтому его
ответы всегда соответствуют коду, который реально лежит в аддоне.

КОМАНДЫ (engine/api/ask/search/paths preview работают без сервера):
  status                          сервер жив? привязан к нашему проекту?
  engine                          версия Godot и состояние кэша API
  api <ClassName>                 методы/свойства/сигналы класса с наследованием
  ask <запрос...>                 компактная справка о проекте (Библиотекарь)
  search [--max N] <текст...>  поиск подстроки по текущему режиму доступа
  read [--max-chars N] <res://path>
  context --request FILE          bounded local project context
  check <res://path...>          gd/tscn/py/json/cfg + headless Godot
  check_action --request FILE    local action judge without a model
  write preview --request FILE    подготовить create/patch без записи
  write apply --request FILE --plan-id ID
  write rollback --entry-id ID [--force]
  paths preview <old> <new>       предпросмотр; apply остаётся в панели агента
                                  (bridge apply не выполняется)

ГРАНИЦА ЗАПИСИ: write всегда двухфазный. preview не меняет исходники и
печатает plan_id; apply повторно строит тот же план, проверяет режим,
исходные хэши и изолированную проверку Godot, затем пишет через журнал
и transaction engine. Режим agent-dev открывает текущий Godot Agent
только при явном --access agent-dev; модель не может прислать addon_dir.

КОНТРАКТ КОДОВ ВОЗВРАТА (это важно для нейросети-потребителя):
  0  ok        — данные в stdout;
  2  not-found — ЗАПРОШЕННОГО НЕ СУЩЕСТВУЕТ или операция обоснованно отклонена
                 по существу (класс неизвестен кэшу, совпадений нет, отказ
                 политики доступа). Это ОТВЕТ инструмента, а не его поломка:
                 повторять тот же запрос бессмысленно, надо переформулировать
                 или признать, что искомого нет;
  3  error     — инструмент НЕ СМОГ ответить: нет кэша, сервер недоступен,
                 обязательный Godot недоступен, ПОТЕРЯНА КВИТАНЦИЯ ПЛАНА или
                 запись журнала, недоступен доверенный корень агента. Ответу
                 доверять нельзя — его нет. Квитанцию и журнал ведёт сам мост,
                 поэтому их отсутствие — сбой инструмента, а НЕ «объекта нет»;
  4  usage     — неверные аргументы командной строки ИЛИ ошибки самого запроса
                 (нет --request, файл не читается, битый JSON, повтор опции).
                 Это ошибка вызова: исправь запрос и повтори.
В stderr всегда ровно одна строка «bridge: <kind>: <пояснение>».
Traceback наружу не утекает никогда — внешняя нейросеть не обязана разбирать
наши внутренности, ей нужен честный статус.
"""
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import time

RC_OK = 0
RC_NOT_FOUND = 2
RC_ERROR = 3
RC_USAGE = 4

MAX_REQUEST_BYTES = 2 * 1024 * 1024
# Локальные линтеры в `check` получают файл целиком: молчаливое усечение
# превращало проверку в ложное «clean» (дефект в хвосте большого .gd просто
# не попадал в линтер). Лимит остаётся только как страховка от файлов
# размером с память, и при его срабатывании мост обязан сказать об этом
# явно, а не рапортовать частичную проверку как успешную.
CHECK_LINT_MAX_CHARS = 2 * 1024 * 1024
# Что именно `check` умеет проверять. `checked: false` для всего остального —
# честный отчёт, а не предложение расширять набор расширений.
CHECK_TEXT_EXTENSIONS = (".gd", ".tscn", ".py", ".json", ".cfg")
CHECK_HEADLESS_EXTENSIONS = (".gd", ".tscn", ".tres", ".gdshader", ".shader")
PLAN_TTL_SECONDS = 15 * 60
ACCESS_MODES = ("project", "addon", "agent-dev")
WRITE_EXTENSIONS = {".cfg", ".csv", ".gd", ".gdshader", ".import", ".json",
                    ".md", ".py", ".shader", ".txt", ".uid"}
PROTECTED_AGENT_PARTS = {"__pycache__", "dist", "minilich_brain",
                         "parser_corpus", ".godot"}
DEFAULT_ACCESS = "addon"

# tools/ лежит внутри python/: поднимаемся на уровень выше и подключаем
# стандартный bootstrap плагина (плоские импорты модулей из подпапок).
_PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)
import _bootstrap  # noqa: E402,F401

_TOKEN_FILE = "godot_agent_token.txt"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5000

def _say(kind, msg):
    """Единственная статусная строка в stderr. kind: ok/not-found/error/usage."""
    try:
        sys.stderr.write("bridge: %s: %s\n" % (kind, msg))
    except Exception:
        pass

def _finish(rc, msg):
    _say({RC_OK: "ok", RC_NOT_FOUND: "not-found",
          RC_ERROR: "error", RC_USAGE: "usage"}[rc], msg)
    return rc

def _out(text):
    try:
        sys.stdout.write(text + "\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Расположение проекта, user:// и токена
# ---------------------------------------------------------------------------

def _find_project_root(start):
    """Вверх от start ищем project.godot. None — если не нашли."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, "project.godot")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent

def _project_name(root):
    """config/name из project.godot (имя папки user:// в app_userdata)."""
    try:
        with open(os.path.join(root, "project.godot"), "r", encoding="utf-8",
                  errors="replace") as f:
            m = re.search(r'^\s*config/name\s*=\s*"([^"]*)"', f.read(), re.M)
        return m.group(1) if m else ""
    except Exception:
        return ""

def _appdata_base():
    """Корень app_userdata Godot на этой ОС."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or ""
        return os.path.join(base, "Godot") if base else ""
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Godot")
    return os.path.expanduser("~/.local/share/godot")

def _user_data_dir(root):
    name = _project_name(root)
    base = _appdata_base()
    if not name or not base:
        return ""
    return os.path.join(base, "app_userdata", name)

def _read_token(user_data_dir):
    """Токен панели из user:// или "" — его читает тот же пользователь ОС."""
    if not user_data_dir:
        return ""
    try:
        with open(os.path.join(user_data_dir, _TOKEN_FILE), "r",
                  encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

class BridgeRefused(ValueError):
    """Capability policy refused an otherwise valid request."""

class BridgeUsage(BridgeRefused):
    """The command line or the request file itself is malformed -> rc=4.

    Отдельный тип нужен, чтобы НЕ путать «плохо вызвали инструмент» с
    «запрошенного не существует». Раньше обе ошибки гасились в rc=2, и
    модель по контракту читала такой ответ как обычный отрицательный
    результат и искала несуществующий объект вместо того, чтобы исправить
    вызов.
    """

class BridgeInfra(BridgeRefused):
    """The bridge could not complete the operation for infrastructural reasons
    -> rc=3 (missing plan receipt, missing journal entry).

    Это не «объекта нет»: квитанция плана и журнал создаёт сам мост, и их
    отсутствие означает сбой его состояния, а не отрицательный ответ.
    """

def _discover_bridge_agent_dir(project_root):
    """Return the running source installation, never a model-supplied path."""
    import project_tools
    candidates = []
    try:
        import server_state
        candidates.append(server_state._discover_trusted_agent_dir(project_root))
    except Exception:
        pass
    # The bridge itself is source, so its parent is an independent second source
    # of truth. This also makes isolated tests possible without a client flag.
    try:
        candidates.append(_addon_dir())
    except Exception:
        pass
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return project_tools.validate_agent_addon_dir(project_root, candidate)
        except (OSError, TypeError, ValueError):
            continue
    return None

def _access_policy(opts, project_root, warn=None):
    """Resolve fixed CLI mode into the existing independent capability flags."""
    mode = str(opts.get("access") or DEFAULT_ACCESS)
    if mode not in ACCESS_MODES:
        raise BridgeUsage("unknown access mode: %s" % mode)
    if mode == "project":
        return {"mode": mode, "allow_addons": False, "allow_self_edit": False,
                "addon_dir": None}
    addon_dir = _discover_bridge_agent_dir(project_root)
    if not addon_dir:
        if mode == "agent-dev":
            raise BridgeInfra(
                "trusted running Godot Agent root is unavailable; agent-dev fails closed")
        # An offline bridge copy may be used from outside this project. Keep
        # ordinary project reads available, but fail closed for every add-on.
        # Молча деградировать нельзя: режим заявлен как «файлы + внешние
        # аддоны», а по факту стал бы project. Модель должна знать, что
        # поиск по аддонам ничего не найдёт НЕ потому, что совпадений нет.
        if warn is not None:
            warn("access mode 'addon' degraded to 'project': trusted Agent root "
                 "is unavailable, external add-ons are not searchable")
        return {"mode": mode, "allow_addons": False, "allow_self_edit": False,
                "addon_dir": None}
    return {"mode": mode, "allow_addons": True,
            "allow_self_edit": mode == "agent-dev", "addon_dir": addon_dir}

def _policy_warning_writer(stream_name="stdout"):
    """Возвращает функцию предупреждения, печатающую в заданный поток."""
    def _warn(message):
        if stream_name == "stderr":
            try:
                sys.stderr.write("bridge: warning: %s\n" % message)
            except Exception:
                pass
        else:
            _out("warning: %s" % message)
    return _warn

def _access_kwargs(policy):
    return {"allow_addons": bool(policy.get("allow_addons")),
            "allow_self_edit": bool(policy.get("allow_self_edit")),
            "addon_dir": policy.get("addon_dir")}

def _configure_history_storage(opts, project_root):
    """Use the same user:// history location as the editor server when known."""
    udd = str(opts.get("udd") or _user_data_dir(project_root) or "").strip()
    if not udd:
        return ""
    import history_manager
    history_manager.set_storage_dir(udd)
    try:
        history_manager.migrate_from_project(project_root)
    except Exception:
        pass
    return udd

def _addon_dir():
    """Корень аддона (родитель python/): там лежит встроенный кэш API."""
    return os.path.dirname(_PYTHON_DIR)

def _addon_arg(opts):
    """addon_dir для кэш-подсистем или None, если встроенный кэш отключён."""
    return _addon_dir() if opts.get("builtin") else None

# ---------------------------------------------------------------------------
# HTTP-канал (нужен только status; остальное — прямой импорт модулей)
# ---------------------------------------------------------------------------

def _http_post(opts, path, payload):
    """POST JSON на сервер панели. Возвращает (status_code, json|None, error|None).
    error — строка при транспортной проблеме; HTTPError даёт (код, None, None)."""
    import urllib.request
    import urllib.error
    url = "http://%s:%d%s" % (opts["host"], int(opts["port"]), path)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json",
                                          "X-Agent-Token": opts.get("token") or ""})
    try:
        with urllib.request.urlopen(req, timeout=float(opts["timeout"])) as resp:
            try:
                return resp.status, json.loads(resp.read().decode("utf-8", "replace")), None
            except Exception:
                return resp.status, None, None
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except Exception as e:
        return 0, None, "%s: %s" % (type(e).__name__, e)

def _engine_line(root, opts):
    """Строка о кэше API для status/engine. Возвращает True, если кэш есть."""
    import gd_api_cache
    addon = _addon_arg(opts)
    if not gd_api_cache.has_cache(root, addon):
        _out("api_cache: MISSING (сервер ещё не выгружал классы; спросите "
             "пользователя открыть агента в редакторе)")
        return False
    version = gd_api_cache.get_cached_version(root, addon) or "?"
    # Источник кэша: свой файл проекта или встроенный в аддон справочник.
    # _cache_path — внутренняя функция того же репозитория; оборачиваем,
    # чтобы косметика статуса не могла уронить команду.
    try:
        own = os.path.isfile(gd_api_cache._cache_path(root))
    except Exception:
        own = False
    _out("api_cache: Godot %s (%s)" % (version,
         "project export" if own else "builtin addon cache"))
    return True

def cmd_status(opts, args):
    """Сервер жив и принимает наш токен? Плюс локальное состояние кэшей."""
    root = _find_project_root(opts.get("root"))
    udd = opts.get("udd") or (_user_data_dir(root) if root else "")
    if not opts.get("token"):
        opts["token"] = _read_token(udd)
    code, data, err = _http_post(opts, "/browser/status", {"user_data_dir": udd})
    if err:
        _out("server: DOWN (%s)" % err)
        _out("offline: engine/api/ask/search/read/paths preview/write работают "
             "и без сервера — напрямую с файлами проекта и кэшами.")
        return _finish(RC_ERROR, "server unreachable; offline commands still available")
    if code in (401, 403):
        _out("server: UP, но отклонил наш токен/user_data_dir (HTTP %d) — "
             "вероятно, привязан к другому проекту или редактор перезапущен." % code)
        return _finish(RC_ERROR, "server rejected auth (HTTP %d)" % code)
    if code != 200:
        return _finish(RC_ERROR, "unexpected HTTP %s from server" % code)
    _out("server: UP (http://%s:%d)" % (opts["host"], int(opts["port"])))
    _out("browser: %s" % json.dumps(data or {}, ensure_ascii=False))
    if root:
        _out("project_root: %s" % root)
        _engine_line(root, opts)
    return _finish(RC_OK, "server is up")

def cmd_engine(opts, args):
    """Версия Godot по кэшу API — актуальная информация о движке проекта."""
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    if not _engine_line(root, opts):
        return _finish(RC_ERROR, "no API cache available")
    return _finish(RC_OK, "engine info from API cache")

def cmd_read(opts, args):
    """Read one policy-authorized project file, including add-ons in dev modes."""
    max_chars = 50000
    if args and args[0] == "--max-chars":
        if len(args) < 2:
            return _finish(RC_USAGE, "--max-chars requires a value")
        try:
            max_chars = int(args[1])
        except ValueError:
            return _finish(RC_USAGE, "--max-chars requires an integer")
        args = args[2:]
        if not 1 <= max_chars <= 200000:
            return _finish(RC_USAGE, "--max-chars must be between 1 and 200000")
    if len(args) != 1 or not args[0].startswith("res://"):
        return _finish(RC_USAGE, "usage: read [--max-chars N] <res://path>")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import project_tools
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
        project_tools.assert_can_read_project_path(
            args[0], root, **_access_kwargs(policy))
        content, truncated = project_tools.read_project_file(
            root, args[0], max_chars=max_chars)
    except (BridgeRefused, FileNotFoundError, ValueError) as exc:
        _out("refused: %s" % exc)
        return _finish(RC_NOT_FOUND, str(exc))
    _out("path: %s" % args[0])
    _out("access: %s" % policy["mode"])
    _out("truncated: %s" % str(truncated).lower())
    _out("--- content ---")
    _out(content)
    return _finish(RC_OK, "file read")

def cmd_api(opts, args):
    """Методы/свойства/сигналы класса с учётом цепочки наследования."""
    if not args:
        return _finish(RC_USAGE, "api requires a class name")
    class_name = args[0]
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import gd_api_cache
    addon = _addon_arg(opts)
    if not gd_api_cache.has_cache(root, addon):
        return _finish(RC_ERROR, "no API cache available")
    info = gd_api_cache.get_class(root, class_name, addon)
    version = gd_api_cache.get_cached_version(root, addon) or "?"
    if not info:
        # Класса нет в кэше — это ОТВЕТ («такого нет»), а не сбой моста.
        _out("class %s: NOT IN CACHE (Godot %s cache). Скорее всего, такого "
             "класса нет в этой версии движка; проверь имя через 'search' "
             "или спроси 'api' у базового класса." % (class_name, version))
        return _finish(RC_NOT_FOUND, "class %s not in API cache" % class_name)
    methods, props, signals = gd_api_cache.collect_members(root, class_name, addon)
    chain = gd_api_cache.resolve_chain(root, class_name, addon_dir=addon)
    _out("%s [cache Godot %s]" % (class_name, version))
    _out("inherits: %s" % " -> ".join(chain))

    def _fmt_method(name, arity):
        try:
            lo, hi = int(arity[0]), int(arity[1])
            return "%s(%d..%d)" % (name, lo, hi) if hi else "%s()" % name
        except Exception:
            return name
    # Полные сигнатуры (новый формат кэша) печатаем по одной на строку —
    # это и есть защита от выдуманных параметров; старый кэш без signatures
    # деградирует до прежней компактной строки арности.
    try:
        sigs = gd_api_cache.collect_signatures(root, class_name, addon)
    except Exception:
        sigs = {}
    if sigs:
        _out("methods (%d):" % len(methods))
        for n in sorted(methods):
            _out("  %s" % (sigs.get(n) or _fmt_method(n, methods[n])))
    else:
        _out("methods (%d): %s" % (len(methods),
             " ".join(sorted(_fmt_method(n, a) for n, a in methods.items()))))
    _out("properties (%d): %s" % (len(props), " ".join(sorted(props))))
    _out("signals (%d): %s" % (len(signals), " ".join(sorted(signals))))
    return _finish(RC_OK, "class %s from API cache" % class_name)

# FOOTER Librarian mentions server-only read_function/patch_file tools. Replace
# it with commands this bridge actually provides.
_BRIDGE_FOOTER = ("Next (bridge): read exact file bodies with `read <res://path>`; "
                  "for a code change use `write preview --request FILE`, then apply "
                  "the returned plan_id only after checking the diff. "
                  "Explore: ask with other English terms; verify signatures: api <Class>.")

def cmd_ask(opts, args):
    """Компактная справка Библиотекаря о проекте (индекс строится на лету)."""
    if not args:
        return _finish(RC_USAGE, "ask requires a query")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import librarian
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
    except BridgeRefused as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))
    text = librarian.answer(root, " ".join(args), addon_dir=policy["addon_dir"],
                            allow_addons=policy["allow_addons"],
                            allow_self_edit=policy["allow_self_edit"])
    text = text.replace(librarian.FOOTER, _BRIDGE_FOOTER)
    # В ветке «nothing matches» Библиотекарь тоже называет серверные
    # действия — переводим на реальные эквиваленты моста.
    text = text.replace("search_project", "search")
    text = text.replace("list_files", "your own file listing")
    _out(text)
    # Тот же критерий наполненности, что у самого Библиотекаря (has_content):
    # если данных нет — это «по запросу ничего не нашлось» (ОТВЕТ, rc 2),
    # а не успех и не сбой. Модель по rc 2 поймёт: не долбить тем же запросом.
    has_content = any(str(ln).startswith(("- ", "  ", "res://"))
                      for ln in text.splitlines())
    if not has_content:
        return _finish(RC_NOT_FOUND, "nothing relevant found")
    return _finish(RC_OK, "librarian answer")

def cmd_search(opts, args):
    """Поиск подстроки по проекту с доступом текущего CLI-режима."""
    max_results = 30
    query_args = []
    i = 0
    while i < len(args):
        if args[i] != "--max":
            query_args.append(args[i])
            i += 1
            continue
        if i + 1 >= len(args):
            return _finish(RC_USAGE, "--max requires a value")
        if max_results != 30:
            return _finish(RC_USAGE, "duplicate option: --max")
        try:
            max_results = int(args[i + 1])
        except (TypeError, ValueError):
            return _finish(RC_USAGE, "--max requires an integer")
        if max_results <= 0:
            return _finish(RC_USAGE, "--max must be positive")
        i += 2
    query = " ".join(query_args)
    if not query.strip():
        return _finish(RC_USAGE, "search requires a query")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import project_tools
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
    except BridgeRefused as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))
    results, truncated = project_tools.search_project_text(
        root, query, max_results=max_results, **_access_kwargs(policy))
    if not results:
        _out("no matches in access=%s" % policy["mode"])
        return _finish(RC_NOT_FOUND, "no matches")
    for row in results:
        _out("%s:%d" % (row.get("path", "?"), int(row.get("line", 0))))
        _out(row.get("snippet", ""))
        _out("---")
    if truncated:
        _out("(results truncated at %d; уточни запрос)" % max_results)
    return _finish(RC_OK, "%d match groups" % len(results))

def cmd_paths(opts, args):
    """paths preview <old> <new> — предпросмотр переименования/перемещения.

    ТОЛЬКО чтение: prepare_file_rename ничего не пишет на диск. Применения
    через мост НЕТ специально — apply делает пользователь кнопкой в панели,
    где есть журнал, откат и post_move_sync с редактором.
    """
    if len(args) < 3 or args[0] != "preview":
        return _finish(RC_USAGE, "usage: paths preview <res://old> <res://new>")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    old_path, new_path = args[1], args[2]
    import file_refactor
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
        prepared = file_refactor.prepare_file_rename(
            root, old_path, new_path, update_references=True,
            **_access_kwargs(policy))
    except (FileNotFoundError, ValueError, OSError) as e:
        # Обоснованный отказ движка рефакторинга (нет источника, занято
        # назначение, самовложение) — это ОТВЕТ, а не сбой моста.
        _out("refused: %s" % e)
        return _finish(RC_NOT_FOUND, "preview refused: %s" % e)
    _out("preview: %s -> %s" % (prepared.get("old_path"), prepared.get("new_path")))
    _out("is_directory: %s" % bool(prepared.get("is_directory")))
    moved = prepared.get("moved_files") or {}
    # Перемещение папки может тащить тысячи файлов — не затапливаем контекст
    # нейросети: первые 50 пар + счётчик остатка. Полный список всё равно
    # покажет карточка подтверждения в панели при реальном применении.
    _MOVED_CAP = 50
    for old, new in list(moved.items())[:_MOVED_CAP]:
        _out("moved: %s -> %s" % (old, new))
    if len(moved) > _MOVED_CAP:
        _out("moved: ... and %d more" % (len(moved) - _MOVED_CAP))
    _out("reference_count: %d" % int(prepared.get("reference_count", 0)))
    _out("file_count: %d" % len(prepared.get("files") or []))
    affected = prepared.get("affected_paths") or []
    if affected:
        _out("affected_paths: %s" % ", ".join(affected))
    if prepared.get("companion_script"):
        _out("companion_script: %s" % prepared["companion_script"])
    _out("note: это предпросмотр; apply безопасного переименования выполняйте "
         "через панель агента (там синхронизация с открытым редактором).")
    return _finish(RC_OK, "preview computed")

# ---------------------------------------------------------------------------
# Write alpha: preview -> single-use apply -> journaled rollback
# ---------------------------------------------------------------------------

def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def _json_request_option(args, option="--request"):
    if not args or args[0] != option:
        return None
    if len(args) < 2:
        raise BridgeUsage("%s requires a file path or -" % option)
    if len(args) > 2:
        raise BridgeUsage("unexpected arguments after %s" % option)
    return args[1]


def cmd_context(opts, args):
    """Collect the same bounded local context package as the panel agent."""
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    try:
        source = _json_request_option(args)
        if not source:
            return _finish(RC_USAGE, "usage: context --request FILE")
        request = _read_request(source)
        policy = _access_policy(opts, root, _policy_warning_writer())
        import gather_context
        result = gather_context.gather(
            root, request, editor_snapshot=None, **_access_kwargs(policy))
    except (OSError, ValueError, RuntimeError) as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))
    _out(gather_context.format_result(result))
    if result.get("errors"):
        return _finish(RC_NOT_FOUND, "context request invalid")
    if not result.get("sections") and not result.get("sources"):
        return _finish(RC_NOT_FOUND, "context is empty")
    return _finish(RC_OK, "context collected")




def _file_char_count(root, path):
    """Полное число символов файла — чтобы предупреждение об усечении было
    конкретным («проверено 200000 из 621032»), а не абстрактным."""
    import project_tools
    try:
        absolute = project_tools._resolve_safe_path(root, path)
        with open(absolute, "r", encoding="utf-8-sig", errors="replace") as handle:
            return len(handle.read())
    except OSError:
        return 0


def _check_one_path(root, path, policy, opts):
    import project_tools
    project_tools.assert_can_read_project_path(
        path, root, **_access_kwargs(policy))
    text, truncated = project_tools.read_project_file(
        root, path, max_chars=CHECK_LINT_MAX_CHARS)
    result = {"path": path, "problems": [], "auto_fixable": False}
    if truncated:
        # Частичная проверка — это НЕ чистая проверка. Молчаливый хвост раньше
        # давал ложное «clean»: дефект за лимитом просто не видел линтер.
        result["truncated"] = True
        result["problems"].append(
            "частичная проверка: линтер получил только первые %d символов из "
            "%d, остаток файла НЕ проверен — не считай файл чистым"
            % (CHECK_LINT_MAX_CHARS, _file_char_count(root, path)))
    extension = os.path.splitext(path)[1].lower()
    # Честный учёт того, ЧТО ИМЕННО проверено. Раньше для .md/.png/project.godot
    # не выполнялось ни одной проверки, но итог всё равно звучал «N files clean»
    # с rc=0 — модель принимала это за успешную проверку.
    #
    # `checked` означает «проверка РЕАЛЬНО ВЫПОЛНИЛАСЬ», а НЕ «расширение входит
    # в какой-то список». Проверка принадлежности к списку давала дыру шире
    # одного расширения: .tres/.gdshader/.shader умеет проверять только
    # настоящий Godot, поэтому при `--validation auto` без движка они получали
    # `checked: true`, хотя не выполнилось НИ ОДНОЙ проверки, и мост рапортовал
    # «clean». Поэтому итог вычисляется в конце, по факту.
    text_linted = extension in CHECK_TEXT_EXTENSIONS
    headless_planned = extension in CHECK_HEADLESS_EXTENSIONS
    if text_linted and extension == ".gd":
        import gd_api_check
        import gd_lint
        result["problems"].extend(gd_lint.lint_gdscript(text))
        result["problems"].extend(gd_api_check.check_api_usage(
            root, text, path, policy.get("addon_dir")))
    elif text_linted and extension == ".tscn":
        import tscn_lint
        fixed, problems = tscn_lint.lint_and_fix_tscn(
            text, root, policy.get("addon_dir"))
        result["problems"].extend(problems)
        result["auto_fixable"] = fixed != text
    elif text_linted and extension == ".py":
        try:
            compile(text, path, "exec")
        except Exception as exc:
            result["problems"].append("python syntax: %s" % exc)
    elif text_linted and extension == ".json":
        try:
            json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
        except Exception as exc:
            result["problems"].append("json syntax: %s" % exc)
    elif text_linted and extension == ".cfg":
        import configparser
        try:
            configparser.ConfigParser(strict=True, interpolation=None).read_string(text)
        except Exception as exc:
            result["problems"].append("cfg syntax: %s" % exc)
    if headless_planned:
        import godot_headless_validation
        absolute = project_tools._resolve_safe_path(root, path)
        with open(absolute, "rb") as handle:
            source_hash = hashlib.sha256(handle.read()).hexdigest()
        batch = godot_headless_validation.make_batch(
            "check", [], [path], {path: source_hash})
        receipt = godot_headless_validation.validate_batch(
            root, batch, executable=opts.get("godot"),
            mode=opts.get("validation"))
        report = receipt.get("report") or {}
        result["headless"] = report
        for problem in (report.get("new_diagnostics") or []):
            result["problems"].append("godot: %s" % problem.get("message", ""))
        # Блокировка headless-проверки — это тоже результат проверки: раньше она
        # молча терялась, и `check` рапортовал «clean» там, где `write apply`
        # отказывался. Формулировку берём из того же источника, что и apply.
        if report.get("blocking"):
            result["headless_blocking"] = True
            result["headless_infrastructure"] = _headless_infrastructure_failure(report)
            result["problems"].append(
                godot_headless_validation.blocking_message(receipt)
                or "godot: изолированная проверка настоящим Godot заблокирована "
                   "(blocking, status=%s)" % report.get("status"))
    else:
        result["headless"] = None
    # Итог `checked` — по факту выполненных проверок, а не по принадлежности
    # расширения к списку. `passed`/`failed` означают, что настоящий Godot
    # отработал и вердикт получен; `skipped` (--validation off), `unavailable`
    # (движка нет) и `inconclusive` (инфраструктурный сбой) — не означают.
    report = result.get("headless") or {}
    headless_ran = (report.get("status") or "") in ("passed", "failed")
    result["checked"] = bool(text_linted or headless_ran)
    if not result["checked"]:
        result["unchecked_reason"] = _unchecked_reason(extension, text_linted, report)
    return result


def _unchecked_reason(extension, text_linted, report):
    """Почему файл НЕ проверен — с указанием, что именно не сработало."""
    if not text_linted and extension in CHECK_HEADLESS_EXTENSIONS:
        status = report.get("status") or "unknown"
        if status == "skipped":
            return ("%s проверяется только настоящим Godot, а проверка отключена "
                    "(--validation off) — файл НЕ проверен" % extension)
        return ("%s проверяется только настоящим Godot, а он не дал вердикта "
                "(headless: %s) — файл НЕ проверен" % (extension, status))
    return ("расширение %s не проверяется этим каналом (проверяются: %s)"
            % (extension or "без расширения",
               ", ".join(sorted(set(CHECK_TEXT_EXTENSIONS)
                                | set(CHECK_HEADLESS_EXTENSIONS)))))


def _headless_infrastructure_failure(report):
    """Блокировка из-за сбоя самой проверки (а не из-за ошибок кандидата).

    Инфраструктурный сбой — это «инструмент НЕ СМОГ ответить» (код 3), а не
    «запрошенного не существует» (код 2): файл может быть полностью корректен,
    но честно сказать «чисто» мост не может.
    """
    if not report.get("blocking"):
        return False
    if report.get("status") in ("unavailable", "inconclusive"):
        return True
    if report.get("timed_out"):
        return True
    for key in ("baseline_status", "candidate_status"):
        if report.get(key) in ("timeout", "crashed"):
            return True
    return False


def cmd_check(opts, args):
    """Run deterministic linters and, when configured, real headless Godot."""
    if not args:
        return _finish(RC_USAGE, "usage: check <res://path...>")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
        results = [_check_one_path(root, path, policy, opts) for path in args]
    except (OSError, ValueError, RuntimeError) as exc:
        _out("refused: %s" % exc)
        return _finish(RC_NOT_FOUND, str(exc))
    for result in results:
        _out("path: %s" % result["path"])
        _out("auto_fixable: %s" % str(result["auto_fixable"]).lower())
        _out("truncated: %s" % str(bool(result.get("truncated"))).lower())
        _out("checked: %s" % str(bool(result.get("checked"))).lower())
        if result.get("unchecked_reason"):
            _out("check_skipped: %s" % result["unchecked_reason"])
        headless = result.get("headless")
        if headless is None:
            _out("headless: not-applicable")
        else:
            _out("headless: %s" % (headless.get("status") or "unknown"))
        for problem in result["problems"]:
            _out("problem: %s" % problem)
    checked_count = sum(1 for result in results if result.get("checked"))
    _out("checked: %d/%d" % (checked_count, len(results)))
    # Сначала считаем КОНКРЕТНЫЕ замечания по файлам. Пока они есть, код 2 —
    # модель читает stdout и видит и проблемы, и честный статус headless.
    problems = sum(len(result["problems"]) for result in results)
    blockers = sum(1 for result in results if result.get("headless_blocking"))
    # Сообщение о блокировке само попало в problems, но замечанием по файлу
    # оно не является — иначе «инструмент не смог ответить» никогда бы не
    # выдавался, а ложное «clean» маскировалось бы под not-found.
    file_problems = max(0, problems - blockers)
    if file_problems or any(result.get("truncated") for result in results):
        # Усечение — тоже не-чистый вердикт: это «ответ с оговоркой» (2), а не
        # 0. Частичная проверка не должна выглядеть как успешная.
        return _finish(RC_NOT_FOUND, "%d problems" % file_problems)
    # Ни одного замечания по файлам, но обязательная headless-проверка не
    # выполнена: честно сказать «чисто» нельзя. Это код 3 («инструмент НЕ СМОГ
    # ответить»), а не 0 и не 2.
    if any(result.get("headless_infrastructure") for result in results):
        return _finish(RC_ERROR, "headless Godot validation could not complete")
    # Ничего не нашли, но часть файлов вообще не проверялась этим каналом.
    # «N files clean» здесь было бы прямой ложью: clean относится к тем k
    # файлам, которые проверялись, а не к остальным.
    if checked_count < len(results):
        return _finish(RC_NOT_FOUND, "%d of %d files checked, %d not checkable"
                       % (checked_count, len(results), len(results) - checked_count))
    return _finish(RC_OK, "%d files clean" % len(results))

def cmd_check_action(opts, args):
    """Judge one model action locally; never writes and never calls a model."""
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    try:
        source = _json_request_option(args)
        if not source:
            return _finish(RC_USAGE, "usage: check_action --request FILE")
        request = _read_request(source)
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise BridgeRefused("request requires a non-empty 'text' field")
        policy = _access_policy(opts, root, _policy_warning_writer())
        import answer_judge
        result = answer_judge.judge_answer(
            root, text, addon_dir=policy.get("addon_dir"),
            allow_addons=policy["allow_addons"],
            allow_self_edit=policy["allow_self_edit"])
    except (OSError, ValueError, RuntimeError) as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))
    _out(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return (_finish(RC_OK, "action accepted") if result.get("acceptable")
            else _finish(RC_NOT_FOUND, "action rejected by local judge"))






def _read_request(path):
    if path == "-":
        data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    else:
        try:
            with open(path, "rb") as handle:
                data = handle.read(MAX_REQUEST_BYTES + 1)
        except OSError as exc:
            # Нечитаемый файл запроса — это ошибка ВЫЗОВА (путь неверен), а не
            # «объекта нет»: модель должна исправить путь, а не искать файл.
            raise BridgeUsage("cannot read request file %s: %s" % (path, exc))
    if len(data) > MAX_REQUEST_BYTES:
        raise BridgeUsage("request exceeds %d bytes" % MAX_REQUEST_BYTES)
    if not data.strip():
        raise BridgeUsage("request is empty")
    try:
        value = json.loads(data.decode("utf-8-sig"),
                           object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BridgeUsage("request is not valid JSON: %s" % exc)
    if not isinstance(value, dict):
        raise BridgeUsage("request root must be a JSON object")
    return value

def _as_transaction(request):
    if request.get("action") == "transaction":
        return request
    if request.get("action") in ("create_file", "patch_file", "move_file"):
        return {"action": "transaction", "operations": [request],
                "summary": str(request.get("summary") or "MCP Alpha write")}
    raise ValueError("write request must be create_file, patch_file, move_file, or transaction")

def _plan_dir(project_root, opts):
    _configure_history_storage(opts, project_root)
    import history_manager
    return os.path.join(history_manager.get_storage_dir(project_root), "bridge_plans")

def _prune_plan_receipts(project_root, opts):
    """Best-effort уборка старых квитанций планов. Никогда не бросает.

    Квитанция одноразовая: при apply она переименовывается в
    `<plan>.json.applying-<pid>`. Если процесс в этот момент падает, файл
    остаётся навсегда и блокирует повторный apply с тем же plan_id, а
    каталог `bridge_plans` растёт монотонно. Удаляем:

      * `.json` старше TTL (время берём из самой квитанции, а не из mtime —
        mtime может врать после копирования, а `created` проставил мост);
      * `.applying-<pid>` — ТОЛЬКО если процесс доказанно мёртв.

    Про `.applying-<pid>` важно: это маркер «apply шёл», а не источник правды.
    Одноразовость плана держится на том, что `<plan>.json` уже переименован
    и повторный apply всё равно получает код 3 «plan receipt not found».
    Поэтому утечка одного маркера безопасна, а вот удаление маркера ЖИВОГО
    apply — нет. Отсюда правило: живой процесс, текущий процесс ИЛИ
    неопределённое состояние (нет прав на проверку) — файл не трогаем.
    Никакого «запасного TTL» для этой ветки намеренно нет: любой порог
    рано или поздно удалит чужую живую работу, а пользы от него нулевая.
    """
    try:
        plan_dir = _plan_dir(project_root, opts)
        names = os.listdir(plan_dir)
    except OSError:
        return 0
    now = time.time()
    current_pid = os.getpid()
    removed = 0
    for name in names:
        path = os.path.join(plan_dir, name)
        if name.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    created = float(json.load(handle).get("created") or 0)
            except (OSError, ValueError, TypeError):
                # Битая квитанция — тоже мусор, но удалять её не будем:
                # возможно, её пишет прямо сейчас другой процесс.
                continue
            if created and now - created > PLAN_TTL_SECONDS:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
            continue
        if ".json.applying-" not in name:
            continue
        suffix = name.rsplit(".applying-", 1)[-1]
        try:
            owner_pid = int(suffix)
        except ValueError:
            continue
        if owner_pid == current_pid:
            continue  # наш собственный активный apply
        alive = True
        if os.name == "nt":
            # На Windows os.kill(pid, 0) бросает ошибку и на живой процесс
            # только при отсутствии прав; надёжнее проверить открытый файл.
            alive = _windows_process_alive(owner_pid)
        else:
            try:
                os.kill(owner_pid, 0)
            except ProcessLookupError:
                alive = False
            except OSError:
                alive = True
        # Удаляем ТОЛЬКО при доказанной смерти процесса. Никакого запасного
        # TTL: живой apply нельзя трогать даже если его квитанция старая, а
        # неопределённость (нет прав на проверку) трактуем как «жив».
        if not alive:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed

def _windows_process_alive(pid):
    """Есть ли процесс с таким pid (Windows) — без запуска внешних утилит.

    ВАЖНО: `OpenProcess` может не сработать по двум разным причинам —
    «процесса нет» (безопасно считать мёртвым) и «процесс есть, но нет
    прав» (ЖИВОЙ, трогать нельзя). Путать их нельзя: иначе уборка снесёт
    квитанцию активного apply, запущенного другим пользователем или с
    повышенными правами. Поэтому при неоднозначности возвращаем True
    (считаем живым) и файл оставляем — утечка одного файла безопаснее
    удаления чужой активной работы.
    """
    if pid <= 0:
        return False
    if os.name != "nt":
        return True
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_INVALID_PARAMETER = 87   # процесса с таким PID не существует
    ERROR_ACCESS_DENIED = 5        # процесс есть, но нам не дали к нему доступ
    kernel32 = ctypes.windll.kernel32
    kernel32.GetLastError.restype = ctypes.c_ulong
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        error = kernel32.GetLastError()
        if error == ERROR_INVALID_PARAMETER:
            return False        # процесса действительно нет
        if error == ERROR_ACCESS_DENIED:
            return True         # процесс жив, просто нет доступа
        return True             # не знаем — считаем живым, файл не трогаем
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return True              # не смогли узнать — считаем живым
    finally:
        kernel32.CloseHandle(handle)

def _write_json_atomic(path, value):
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".bridge-plan-", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass

def _normalized_addon_dir(policy):
    """Канонический путь addon_dir для digest — БЕЗ зависимости от cwd.

    Раньше здесь было `os.path.normcase(os.path.realpath(addon_dir or ""))`,
    а `os.path.realpath("")` возвращает текущий рабочий каталог. В режиме
    `--access project` (addon_dir=None) это означало, что одинаковый запрос
    из разных папок давал разные plan_id, а preview в одной папке и apply
    в другой падал с «stale plan» — хотя запрос, режим и исходник не
    менялись. Пустой путь должен давать стабильную пустую строку.
    """
    raw = str(policy.get("addon_dir") or "").strip()
    if not raw:
        return ""
    return os.path.normcase(os.path.realpath(raw))

def _plan_digest(action, policy, before_hashes):
    payload = {
        "schema": 1,
        "action": action,
        "access": policy["mode"],
        "policy": {"allow_addons": policy["allow_addons"],
                   "allow_self_edit": policy["allow_self_edit"],
                   "addon_dir": _normalized_addon_dir(policy)},
        "before_hashes": before_hashes,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def _prepared_plan_id(prepared, policy):
    before = {item["path"]: item.get("before_hash")
              for item in prepared.get("files") or []}
    return _plan_digest(prepared["action"], policy, before)[:24]

def _assert_agent_path_writable(project_root, path, policy):
    """Запретить запись в сгенерированные/замороженные каталоги агента.

    Раньше этот фильтр жил только в `_validate_bridge_candidate` (транзакции)
    и в ветке move_file, поэтому `repair_scene` и `rename_symbol` проходили
    в `dist/`, `__pycache__`, `parser_corpus`. Теперь проверка общая.

    Путь канонизируется через `_resolve_safe_path`, а не склеивается вручную
    из `project_root` и `path[6:]`: только так симлинк внутри `addons/` не
    даёт обойти проверку.
    """
    if not (policy.get("allow_self_edit") and policy.get("addon_dir")):
        return
    import project_tools
    if not project_tools.is_agent_path(path, project_root, policy["addon_dir"]):
        return
    absolute = project_tools._resolve_safe_path(project_root, path)
    rel = os.path.relpath(
        absolute, os.path.realpath(policy["addon_dir"])).replace(os.sep, "/").split("/")
    if any(part in PROTECTED_AGENT_PARTS for part in rel):
        raise BridgeRefused(
            "generated/frozen Agent path is not writable: %s" % path)

def _assert_prepared_access(project_root, prepared, policy):
    import project_tools
    for item in prepared.get("files") or []:
        path = item.get("path") or ""
        if not path:
            continue
        if item.get("action") == "move_file":
            candidates = [path, item.get("dest") or ""]
            for candidate in candidates:
                if not candidate:
                    continue
                project_tools.assert_can_write_project_path(
                    candidate, project_root, **_access_kwargs(policy))
                _assert_agent_path_writable(project_root, candidate, policy)
        elif prepared.get("kind") in ("scene_repair", "symbol_rename"):
            project_tools.assert_can_write_project_path(
                path, project_root, **_access_kwargs(policy))
            _assert_agent_path_writable(project_root, path, policy)
        else:
            # Safe file refactor may update concrete references in project.godot
            # and resources; this is not a generic text write of that file.
            project_tools.assert_can_reference_project_path(
                path, project_root, **_access_kwargs(policy))
            _assert_agent_path_writable(project_root, path, policy)

def _print_write_preview(prepared, plan_id, policy):
    _out("plan_id: %s" % plan_id)
    _out("access: %s" % policy["mode"])
    _out("already_satisfied: %s" % str(prepared.get("already_satisfied", False)).lower())
    _out("paths: %s" % ", ".join(prepared.get("paths") or []))
    if prepared.get("affected_paths"):
        _out("affected_paths: %s" % ", ".join(prepared["affected_paths"]))
    if prepared.get("kind") == "refactor":
        _out("reference_count: %d" % int(
            prepared.get("refactor", {}).get("reference_count", 0)))
    if prepared.get("kind") == "symbol_rename":
        _out("reference_count: %d" % int(
            prepared.get("symbol", {}).get("reference_count", 0)))
    for problem in prepared.get("problems") or []:
        _out("remaining_problem: %s" % problem)
    for diff in prepared.get("diffs") or []:
        _out("diff: %s" % json.dumps(diff, ensure_ascii=False,
                                      separators=(",", ":")))

def _validate_bridge_candidate(project_root, prepared):
    """Local syntax checks complement the existing GDScript/Godot barriers.

    Параметра `policy` здесь больше нет намеренно: раньше он требовался только
    для дублирующей проверки PROTECTED_AGENT_PARTS, которая удалена.

    Здесь НЕТ проверки PROTECTED_AGENT_PARTS — единственный источник правды
    `_assert_agent_path_writable`, который вызывается из `_assert_prepared_access`
    сразу после этой функции (см. `_make_prepared`). Дублировать её второй раз
    нельзя: старая копия считала `relpath` от `policy["addon_dir"]` и склеивала
    путь через `os.path.join(project_root, path[6:])` без канонизации, то есть
    не видела симлинк. Мёртвый небезопасный код однажды мог стать единственным
    — при перестановке вызовов он бы тихо заработал.
    """
    import configparser
    direct_paths = {
        operation.get("path") for operation in prepared.get("action", {}).get("operations", [])
        if operation.get("action") in ("create_file", "patch_file")
    }
    for item in prepared.get("files") or []:
        path = item["path"]
        extension = os.path.splitext(path)[1].lower()
        if extension not in WRITE_EXTENSIONS:
            raise BridgeRefused("write supports text source extensions only: %s" % path)
        if path in direct_paths and extension in (".uid", ".import"):
            raise BridgeRefused("write cannot address Godot-managed sidecars directly: %s" % path)
        # Защищённые каталоги агента здесь намеренно не проверяются — см.
        # docstring функции: единственный источник правды `_assert_agent_path_writable`.
        data = item.get("after_bytes")
        if data is None or extension not in (".py", ".json", ".cfg"):
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BridgeRefused("%s is not UTF-8: %s" % (path, exc))
        try:
            if extension == ".py":
                compile(text, path, "exec")
            elif extension == ".json":
                json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
            else:
                configparser.ConfigParser(strict=True, interpolation=None).read_string(text)
        except Exception as exc:
            raise BridgeRefused("%s failed local syntax validation: %s" % (path, exc))


def _make_scene_repair_prepared(root, request, policy):
    import project_tools
    import tscn_lint
    path = str(request.get("path") or "")
    if not path.startswith("res://") or not path.lower().endswith(".tscn"):
        raise BridgeRefused("repair_scene supports only an existing res://*.tscn path")
    project_tools.assert_can_write_project_path(
        path, root, **_access_kwargs(policy))
    absolute = project_tools._resolve_safe_path(root, path)
    if not os.path.isfile(absolute):
        raise BridgeRefused("scene not found: %s" % path)
    with open(absolute, "rb") as handle:
        before = handle.read()
    text = before.decode("utf-8-sig").replace("\r\n", "\n")
    fixed, problems = tscn_lint.lint_and_fix_tscn(
        text, root, policy.get("addon_dir"))
    if fixed == text:
        if problems:
            raise BridgeRefused(
                "tscn_lint has no deterministic repair; remaining problems: %s"
                % " | ".join(problems[:8]))
        return {"kind": "scene_repair", "action": {"action": "repair_scene", "path": path},
                "files": [], "paths": [path], "diffs": [],
                "problems": problems, "already_satisfied": True}
    after = fixed.encode("utf-8")
    diff = project_tools.build_diff_preview(text, fixed)
    diff.update({"path": path, "action": "repair_scene"})
    item = {"action": "repair_scene", "path": path, "absolute": absolute,
            "before_hash": hashlib.sha256(before).hexdigest(),
            "before_bytes": before, "after_bytes": after, "diff": diff}
    import godot_headless_validation
    batch = godot_headless_validation.make_batch(
        "repair_scene", [{"op": "write", "path": path, "content": after}],
        [path], {path: item["before_hash"]},
        required_targets=[path] if request.get("require_godot") else ())
    return {"kind": "scene_repair", "action": {"action": "repair_scene", "path": path},
            "files": [item], "paths": [path], "diffs": [diff],
            "problems": problems, "batch": batch, "already_satisfied": False}


def _rename_target_path(request):
    """res://-путь из declaration запроса rename_symbol (без :line:column)."""
    raw = str(request.get("declaration") or "").strip().replace("\\", "/")
    return raw.rsplit(":", 2)[0] if raw.startswith("res://") else ""

def _make_symbol_rename_prepared(root, request, policy):
    import godot_headless_validation
    import symbol_refactor
    # Защищённый каталог агента отсекаем ДО prepare_rename: иначе отказ
    # приходит от внутреннего парсера («объявлений не найдено») и выглядит
    # как обычная неудача поиска, а фильтр защиты остаётся невидимым.
    target = _rename_target_path(request)
    if target:
        _assert_agent_path_writable(root, target, policy)
    prepared = symbol_refactor.prepare_rename(
        root, request, **_access_kwargs(policy))
    action = {"action": "rename_symbol", "kind": prepared["kind"],
              "declaration": prepared.get("declaration"),
              "old_name": prepared["old_name"], "new_name": prepared["new_name"]}
    return {"kind": "symbol_rename", "action": action, "symbol": prepared,
            "files": prepared.get("files") or [],
            "paths": [item["path"] for item in prepared.get("files") or []],
            "diffs": symbol_refactor.prepared_diffs(prepared),
            "batch": godot_headless_validation.batch_from_rename(root, prepared),
            "already_satisfied": False}


def _make_prepared(root, request, policy):
    if request.get("action") == "repair_scene":
        prepared = _make_scene_repair_prepared(root, request, policy)
        _assert_prepared_access(root, prepared, policy)
        return prepared
    if request.get("action") == "rename_symbol":
        prepared = _make_symbol_rename_prepared(root, request, policy)
        _assert_prepared_access(root, prepared, policy)
        return prepared
    if request.get("action") == "move_file":
        import file_refactor
        import godot_headless_validation
        refactor = file_refactor.prepare_file_rename(
            root, request.get("path"), request.get("dest"),
            update_references=True, **_access_kwargs(policy))
        bridge_action = {"action": "rename_file",
                         "path": refactor["old_path"],
                         "dest": refactor["new_path"]}
        prepared = {
            "kind": "refactor",
            "action": bridge_action,
            "refactor": refactor,
            "files": refactor.get("files") or [],
            "paths": [refactor["old_path"], refactor["new_path"]],
            "affected_paths": refactor.get("affected_paths") or [],
            "diffs": [item["diff"] for item in refactor.get("files") or []
                      if item.get("diff")],
            "batch": godot_headless_validation.batch_from_rename(root, refactor),
            "already_satisfied": False,
        }
        _assert_prepared_access(root, prepared, policy)
        return prepared

    import transaction_actions
    action = _as_transaction(request)
    if any(operation.get("action") == "move_file"
           for operation in action.get("operations") or []):
        raise BridgeRefused(
            "transaction с move_file не поддерживается: отправь отдельный "
            "move_file, чтобы применить безопасное обновление всех ссылок")
    prepared = transaction_actions.prepare(root, action, **_access_kwargs(policy))
    prepared["kind"] = "transaction"
    # Сначала синтаксис/расширения, затем единый фильтр защищённых путей.
    _validate_bridge_candidate(root, prepared)
    prepared["diffs"] = transaction_actions.prepared_diffs(prepared)
    _assert_prepared_access(root, prepared, policy)
    return prepared

def _validation_receipt(root, prepared, opts):
    """Validate candidate in isolated project; explicit checks require Godot."""
    if prepared.get("already_satisfied"):
        return None
    import godot_headless_validation
    return godot_headless_validation.validate_batch(
        root, prepared["batch"], executable=opts.get("godot"),
        mode=opts.get("validation"))

def _parse_write_options(args, allowed):
    values = {}
    index = 0
    while index < len(args):
        key = args[index]
        if key not in allowed or index + 1 >= len(args):
            raise BridgeUsage("unknown or incomplete option: %s" % key)
        if key in values:
            raise BridgeUsage("duplicate option: %s" % key)
        values[key] = args[index + 1]
        index += 2
    return values

def _claim_plan_receipt(root, opts, plan_id):
    """Atomically claim a single-use preview receipt before rebuilding/apply."""
    if not re.fullmatch(r"[0-9a-f]{24}", plan_id):
        raise BridgeUsage("plan_id must be 24 lowercase hex characters")
    # Уборка осиротевших квитанций перед чтением: она не должна помешать
    # этому вызову и никогда не бросает исключений наружу.
    _prune_plan_receipts(root, opts)
    plan_path = os.path.join(_plan_dir(root, opts), plan_id + ".json")
    # Отсутствующая/битая квитанция — сбой состояния моста, поэтому FileNotFoundError
    # и ошибки разбора JSON переводятся в BridgeInfra, а не пробрасываются как OSError
    # (их гасили в rc=2 «объекта нет», хотя квитанцию создаёт сам мост).
    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except FileNotFoundError:
        # Квитанция одноразовая: её отсутствие означает «уже применена, идёт
        # применение или истёк TTL». Формулировку сохраняем прежней, чтобы
        # модель понимала причину, но код теперь 3, а не 2: квитанцию создаёт
        # сам мост, и её отсутствие — сбой его состояния, а не «объекта нет».
        raise BridgeInfra("plan receipt not found (already applied, in progress, "
                          "or expired): %s" % plan_id)
    except (OSError, ValueError) as exc:
        raise BridgeInfra("plan receipt is unreadable: %s" % exc)
    if (not isinstance(plan, dict) or plan.get("schema") != 1
            or plan.get("plan_id") != plan_id
            or time.time() - float(plan.get("created") or 0) > PLAN_TTL_SECONDS):
        raise BridgeInfra("plan receipt is invalid or expired")
    claimed = "%s.applying-%d" % (plan_path, os.getpid())
    try:
        os.rename(plan_path, claimed)
    except FileNotFoundError:
        raise BridgeInfra("plan receipt not found")
    return claimed, plan

def _rollback_bridge_write(root, opts, policy, rest):
    force = rest.count("--force")
    if force > 1:
        raise BridgeUsage("duplicate option: --force")
    filtered = [arg for arg in rest if arg != "--force"]
    values = _parse_write_options(filtered, ("--entry-id",))
    entry_id = str(values.get("--entry-id") or "")
    if not re.fullmatch(r"[0-9a-f]{12}", entry_id):
        raise BridgeUsage("entry-id must be a 12-character journal id")
    _configure_history_storage(opts, root)
    import history_manager
    import project_tools
    info = history_manager.entry_info(root, entry_id)
    if not info:
        # Журнал ведёт сам мост: отсутствие записи — сбой его состояния, а не
        # «такого объекта нет». Модели нужен код 3, чтобы не искать причину
        # в несуществующей записи.
        raise BridgeInfra("journal entry not found")
    for path in info.get("paths") or []:
        if (info.get("type") == "rename_file"
                and project_tools.classify_project_path(
                    path, root, policy.get("addon_dir")).get("is_project_settings")):
            project_tools.assert_can_reference_project_path(
                path, root, **_access_kwargs(policy))
        else:
            project_tools.assert_can_write_project_path(
                path, root, **_access_kwargs(policy))
    return entry_id, history_manager.rollback_entry(
        root, entry_id, force=bool(force))

def _read_write_from_args(command, rest):
    allowed = ("--request", "--plan-id") if command == "apply" else ("--request",)
    values = _parse_write_options(rest, allowed)
    request_path = values.get("--request")
    if not request_path:
        raise BridgeUsage("--request is required")
    return values, _read_request(request_path)

def _apply_scene_repair(root, prepared, policy):
    import history_manager
    import librarian
    from minilich import ml_project_index
    item = prepared["files"][0]
    absolute = item["absolute"]
    with open(absolute, "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != item["before_hash"]:
            raise BridgeRefused("scene changed after preview: %s" % item["path"])
    state = {"path": item["path"], "before_bytes": item["before_bytes"],
             "after_bytes": item["after_bytes"]}
    entry_id = history_manager.record_batch_change(
        root, "repair_scene", [item["path"]], "mcp-alpha", "MCP Alpha",
        states=[state])
    descriptor, temporary = tempfile.mkstemp(
        prefix=".agent_scene_repair_", dir=os.path.dirname(absolute))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(item["after_bytes"])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, absolute)
        history_manager.commit_change(root, entry_id)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        with open(absolute, "wb") as handle:
            handle.write(item["before_bytes"])
        history_manager.abort_change(root, entry_id)
        raise
    try:
        librarian.note_files_changed(root, [item["path"]])
        ml_project_index.update_entries(root, changed_rels=[item["path"]])
    except Exception:
        pass
    return {"entry_id": entry_id, "changed_paths": [item["path"]],
            "file_count": 1, "reference_count": 0,
            "remaining_problems": prepared.get("problems") or []}


def _refusal_code(exc):
    """Отказ -> код возврата по документированному контракту.

    BridgeUsage (плохой вызов) -> 4, BridgeInfra (сбой состояния моста) -> 3,
    BridgeRefused (отказ политики по существу) -> 2. Раньше все три гасились
    в 2, и модель читала «инструмент не смог» как «объекта не существует».
    """
    if isinstance(exc, BridgeUsage):
        return RC_USAGE
    if isinstance(exc, BridgeInfra):
        return RC_ERROR
    return RC_NOT_FOUND

def _apply_write_plan(root, opts, policy, values, request):
    claimed_path = None
    try:
        expected = str(values.get("--plan-id") or "")
        claimed_path, plan = _claim_plan_receipt(root, opts, expected)
        prepared = _make_prepared(root, request, policy)
        actual_plan_id = _prepared_plan_id(prepared, policy)
    except BridgeRefused as exc:
        if claimed_path and os.path.exists(claimed_path):
            os.remove(claimed_path)
        _out("refused: %s" % exc)
        return _refusal_code(exc), str(exc)
    except (OSError, ValueError, RuntimeError) as exc:
        if claimed_path and os.path.exists(claimed_path):
            os.remove(claimed_path)
        _out("refused: %s" % exc)
        return _refusal_code(exc), str(exc)
    if (not hmac.compare_digest(str(plan.get("plan_id") or ""), actual_plan_id)
            or plan.get("mode") != policy["mode"]):
        os.remove(claimed_path)
        _out("refused: stale plan; request, access mode, or source changed")
        return RC_NOT_FOUND, "stale plan"
    if prepared.get("already_satisfied"):
        try:
            os.remove(claimed_path)
        except OSError:
            pass
        _out("plan_id: %s" % expected)
        _out("already_satisfied: true")
        return RC_OK, "nothing to apply"

    import godot_headless_validation
    import transaction_actions
    try:
        receipt = _validation_receipt(root, prepared, opts)
        blocking = godot_headless_validation.blocking_message(receipt)
        if blocking:
            os.remove(claimed_path)
            _out(blocking)
            return RC_NOT_FOUND, "candidate blocked by Godot validation"
        if prepared.get("kind") == "refactor":
            import file_refactor
            result = file_refactor.apply_prepared_file_rename(
                root, prepared["refactor"], "mcp-alpha", "MCP Alpha",
                **_access_kwargs(policy))
        elif prepared.get("kind") == "scene_repair":
            result = _apply_scene_repair(root, prepared, policy)
        elif prepared.get("kind") == "symbol_rename":
            import symbol_refactor
            result = symbol_refactor.apply_prepared_rename(
                root, prepared["symbol"], "mcp-alpha", "MCP Alpha")
        else:
            transaction_actions.attach_validation(prepared, receipt)
            result = transaction_actions.apply_prepared(
                root, prepared, "mcp-alpha", "MCP Alpha")
    except Exception as exc:
        if os.path.exists(claimed_path):
            os.remove(claimed_path)
        _out("apply failed: %s" % exc)
        return RC_ERROR, "write apply failed"
    try:
        os.remove(claimed_path)
    except OSError:
        pass
    _out("plan_id: %s" % expected)
    _out("entry_id: %s" % result["entry_id"])
    _out("changed_paths: %s" % ", ".join(result.get("changed_paths") or []))
    if result.get("reference_count") is not None:
        _out("reference_count: %d" % int(result["reference_count"]))
    return RC_OK, "write applied and journaled"

def cmd_write(opts, args):
    if not args:
        return _finish(RC_USAGE, "write requires preview, apply, or rollback")
    command, rest = args[0], args[1:]
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    try:
        policy = _access_policy(opts, root, _policy_warning_writer())
    except BridgeRefused as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))

    if command == "rollback":
        try:
            entry_id, result = _rollback_bridge_write(root, opts, policy, rest)
        except (OSError, ValueError, RuntimeError) as exc:
            _out("refused: %s" % exc)
            return _finish(_refusal_code(exc), str(exc))
        ok, message, needs_force, paths, diff = result
        _out("entry_id: %s" % entry_id)
        _out("success: %s" % str(ok).lower())
        _out("message: %s" % message)
        _out("needs_force: %s" % str(needs_force).lower())
        _out("paths: %s" % ", ".join(paths or []))
        if diff:
            _out("diff: %s" % json.dumps(diff, ensure_ascii=False,
                                          separators=(",", ":")))
        return (_finish(RC_OK, "rollback complete") if ok
                else _finish(RC_NOT_FOUND, "rollback refused"))

    if command not in ("preview", "apply"):
        return _finish(RC_USAGE, "unknown write command: %s" % command)
    try:
        values, request = _read_write_from_args(command, rest)
    except (OSError, ValueError, RuntimeError) as exc:
        _out("refused: %s" % exc)
        return _finish(_refusal_code(exc), str(exc))
    if command == "preview":
        try:
            prepared = _make_prepared(root, request, policy)
            actual_plan_id = _prepared_plan_id(prepared, policy)
        except (OSError, ValueError, RuntimeError) as exc:
            _out("refused: %s" % exc)
            return _finish(_refusal_code(exc), str(exc))
        record = {"schema": 1, "plan_id": actual_plan_id, "created": time.time(),
                  "mode": policy["mode"], "paths": prepared.get("paths") or []}
        try:
            _prune_plan_receipts(root, opts)
            _write_json_atomic(os.path.join(
                _plan_dir(root, opts), actual_plan_id + ".json"), record)
        except OSError as exc:
            _out("preview prepared, but plan receipt could not be saved: %s" % exc)
            return _finish(RC_ERROR, "plan receipt persistence failed")
        _print_write_preview(prepared, actual_plan_id, policy)
        return _finish(RC_OK, "write preview ready; source unchanged")
    code, message = _apply_write_plan(
        root, opts, policy, values, request)
    return _finish(code, message)

# ---------------------------------------------------------------------------
# Разбор аргументов и входная точка
# ---------------------------------------------------------------------------

_COMMANDS = {
    "status": cmd_status,
    "engine": cmd_engine,
    "api": cmd_api,
    "ask": cmd_ask,
    "search": cmd_search,
    "read": cmd_read,
    "context": cmd_context,
    "check": cmd_check,
    "check_action": cmd_check_action,
    "paths": cmd_paths,
    "write": cmd_write,
}

_USAGE = ("usage: agent_bridge.py [--root PATH] [--udd PATH] [--token T] "
          "[--host H] [--port N] [--timeout SEC] [--no-builtin-cache] "
          "[--access project|addon|agent-dev] [--godot PATH] "
          "[--validation off|auto|required] "
          "<status|engine|api|ask|search|read|context|check|check_action|paths|write> "
          "[args...]")

def main(argv):
    """CLI-вход. Возвращает код завершения; исключений наружу не бросает."""
    # Консоль Windows может быть не в UTF-8 — заменяем непечатаемое,
    # а не падаем (см. test_godot_live.py: та же страховка).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    opts = {"root": None, "udd": None, "token": os.environ.get("GODOT_AGENT_TOKEN"),
            "host": _DEFAULT_HOST, "port": _DEFAULT_PORT, "timeout": 3.0,
            "builtin": True, "access": DEFAULT_ACCESS, "godot": None,
            "validation": "auto"}
    args = list(argv)
    cmd_args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--root", "--udd", "--token", "--host", "--port", "--timeout",
                 "--access", "--godot", "--validation"):
            if i + 1 >= len(args):
                return _finish(RC_USAGE, "%s requires a value" % a)
            key = a[2:].replace("-", "_")
            opts[key] = args[i + 1]
            i += 2
        elif a == "--no-builtin-cache":
            opts["builtin"] = False
            i += 1
        elif a.startswith("--"):
            return _finish(RC_USAGE, "unknown option %s\n%s" % (a, _USAGE))
        else:
            cmd_args = args[i:]
            break
    if not cmd_args:
        return _finish(RC_USAGE, "no command\n" + _USAGE)
    try:
        opts["port"] = int(opts["port"])
        opts["timeout"] = float(opts["timeout"])
    except (TypeError, ValueError):
        return _finish(RC_USAGE, "--port and --timeout must be numeric")
    if opts["access"] not in ACCESS_MODES:
        return _finish(RC_USAGE, "--access must be project, addon, or agent-dev")
    if opts["validation"] not in ("off", "auto", "required"):
        return _finish(RC_USAGE, "--validation must be off, auto, or required")
    fn = _COMMANDS.get(cmd_args[0])
    if fn is None:
        return _finish(RC_USAGE, "unknown command %s\n%s" % (cmd_args[0], _USAGE))
    try:
        return fn(opts, cmd_args[1:])
    except Exception as e:
        # Последний рубеж: команда не смогла ответить — честный error,
        # а не traceback в чужой контекст.
        _out("internal failure: %s: %s" % (type(e).__name__, e))
        return _finish(RC_ERROR, "unexpected %s" % type(e).__name__)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
