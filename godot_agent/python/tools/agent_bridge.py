# -*- coding: utf-8 -*-
"""agent_bridge.py — «альфа MCP» (v0): командный мост между внешней нейросетью
и плагином Godot_agent.

ЗАЧЕМ. Нейросеть, запущенная снаружи редактора (Cline, Cursor, руки человека),
должна получать АКТУАЛЬНЫЕ данные о проекте и о Godot API из тех же источников,
что и встроенный агент, а не полагаться на свою обучающую выборку. Мост
работает напрямую с модулями плагина (без запущенного сервера), поэтому его
ответы всегда соответствуют коду, который реально лежит в аддоне.

КОМАНДЫ (все, кроме status, работают без сервера — read-only):
  status                          сервер жив? привязан к нашему проекту?
  engine                          версия Godot и состояние кэша API
  api <ClassName>                 методы/свойства/сигналы класса с наследованием
  ask <запрос...>                 компактная справка о проекте (Библиотекарь)
  search <текст...>               поиск подстроки по файлам проекта
  paths preview <old> <new>       предпросмотр переименования/перемещения
                                  (НИЧЕГО не применяет; apply — только кнопкой
                                  в панели агента, там журнал и откат)

КОНТРАКТ КОДОВ ВОЗВРАТА (это важно для нейросети-потребителя):
  0  ok        — данные в stdout;
  2  not-found — ЗАПРОШЕННОГО НЕ СУЩЕСТВУЕТ или операция обоснованно отклонена
                 (класс неизвестен кэшу, совпадений нет, файла-источника нет).
                 Это ОТВЕТ инструмента, а не его поломка: повторять тот же
                 запрос бессмысленно, надо переформулировать или признать,
                 что искомого нет;
  3  error     — инструмент НЕ СМОГ ответить (нет кэша, сервер недоступен,
                 внутреннее исключение). Ответу доверять нельзя — его нет;
  4  usage     — неверные аргументы командной строки.
В stderr всегда ровно одна строка «bridge: <kind>: <пояснение>».
Traceback наружу не утекает никогда — внешняя нейросеть не обязана разбирать
наши внутренности, ей нужен честный статус.
"""
import json
import os
import re
import sys

RC_OK = 0
RC_NOT_FOUND = 2
RC_ERROR = 3
RC_USAGE = 4

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
        _out("offline: команды engine/api/ask/search/paths preview работают "
             "и без сервера — они читают файлы проекта и кэши напрямую.")
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
    _out("methods (%d): %s" % (len(methods),
         " ".join(sorted(_fmt_method(n, a) for n, a in methods.items()))))
    _out("properties (%d): %s" % (len(props), " ".join(sorted(props))))
    _out("signals (%d): %s" % (len(signals), " ".join(sorted(signals))))
    return _finish(RC_OK, "class %s from API cache" % class_name)


# FOOTER Библиотекаря советует read_function/patch_file — это инструменты
# СЕРВЕРНОГО агента; через мост их нет, и внешняя нейросеть, послушавшись
# подсказки, получила бы rc 4. Заменяем хвост на честный мостовой.
_BRIDGE_FOOTER = ("Next (bridge): read function bodies with your own file tools "
                  "at the 1-based lines above — precise function-reading and "
                  "file-patching actions exist only in the editor panel agent, "
                  "NOT in this bridge. Explore: ask with other English terms; "
                  "verify signatures: api <Class>.")


def cmd_ask(opts, args):
    """Компактная справка Библиотекаря о проекте (индекс строится на лету)."""
    if not args:
        return _finish(RC_USAGE, "ask requires a query")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import librarian
    text = librarian.answer(root, " ".join(args), addon_dir=_addon_arg(opts))
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
    """Поиск подстроки по проекту; addons/ исключаются, как в Библиотекаре."""
    if not args:
        return _finish(RC_USAGE, "search requires a query")
    root = _find_project_root(opts.get("root"))
    if not root:
        return _finish(RC_ERROR, "project.godot not found (use --root)")
    import project_tools
    max_results = 30
    if "--max" in args:
        i = args.index("--max")
        try:
            max_results = int(args[i + 1])
        except Exception:
            return _finish(RC_USAGE, "--max requires an integer")
        args = args[:i] + args[i + 2:]
    results, truncated = project_tools.search_project_text(
        root, " ".join(args), max_results=max_results,
        exclude_rel_prefixes=("addons/",))
    if not results:
        _out("no matches (addons/ excluded)")
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
        prepared = file_refactor.prepare_file_rename(
            root, old_path, new_path, update_references=True)
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
    _out("note: это предпросмотр; применение — только через панель агента "
         "(там журнал и откат).")
    return _finish(RC_OK, "preview computed")


# ---------------------------------------------------------------------------
# Разбор аргументов и входная точка
# ---------------------------------------------------------------------------

_COMMANDS = {
    "status": cmd_status,
    "engine": cmd_engine,
    "api": cmd_api,
    "ask": cmd_ask,
    "search": cmd_search,
    "paths": cmd_paths,
}

_USAGE = ("usage: agent_bridge.py [--root PATH] [--udd PATH] [--token T] "
          "[--host H] [--port N] [--timeout SEC] [--no-builtin-cache] "
          "<status|engine|api|ask|search|paths> [args...]")


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
            "builtin": True}
    args = list(argv)
    cmd_args = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--root", "--udd", "--token", "--host", "--port", "--timeout"):
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
