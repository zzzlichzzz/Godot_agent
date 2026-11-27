#!/usr/bin/env python
"""tools/_reference_runner.py - единственная точка вызова ЭТАЛОНА (R-07).

Запускается только из `tools/snapshot_record.py` отдельным процессом с `-B`,
поэтому старый агент не оставляет `__pycache__` у себя в дереве (R-08: эталон
не правится ни на байт, включая мусор прогонов).

Использование (внутреннее):
    python -B tools/_reference_runner.py <старый python-каталог> <tool> <args-json>

`tool` — имя механики в корпусе, у каждой своя эталонная функция:
  search          -> godot_tools/project_tools.py:search_project_text
  functions       -> godot_tools/gd_functions.py:list_functions / extract_functions,
                     плюс те же проверки, что делал мост (`.gd`, политика путей,
                     существование файла, бюджет чтения).
  usages          -> godot_tools/symbol_refactor.py:find_references
  analyze_rename  -> godot_tools/symbol_refactor.py:analyze_rename (обёртка над
                     `find_references`), плюс проверка обязательных аргументов
                     моста `agent_bridge.py:cmd_analyze_rename` (declaration,
                     old-name, new-name) — иначе эталонный CLI отвечал RC_USAGE
                     (`invalid_input`).
  write_preview   -> godot_tools/symbol_refactor.py:prepare_rename
                     (`symbol_refactor_part3.py:61-615`) с нормализацией плана:
                     файлы с числом правок, счётчики, эхо входа, класс отказа.
                     `apply_prepared_rename` здесь НЕ вызывается: запись —
                     часть 2 (`editing.write_apply`).
  write_apply     -> `prepare_rename` + `apply_prepared_rename`
                     (`symbol_refactor_part3.py:628+`) на ВРЕМЕННОЙ копии
                     проекта; наружу — только sha256 сырых байтов `src/**/*.gd`
                     после записи (квитанции и тексты эталона не переносятся).
  write_rollback  -> тот же `prepare_rename`; ожидание — sha256 `before_bytes`
                     каждого файла плана, то есть байты ДО применения: своего
                     отката у эталона нет (`history_manager` не портируется, R-08).

Печатает в stdout JSON результата. Отказ старого агента печатается как
`{"ok": false, "kind": "..."}`: наружу переносится смысл отказа (`kind`), а не
текст (R-15). Ошибки запуска — в stderr, код возврата 2.

Файл не импортируется ни агентом (`python/`), ни тестами: кейсы берутся из
корпуса, старый код не переиспользуется (R-16).
"""

import hashlib
import json
import os
import re
import sys

#: Старый мост читал файл с бюджетом CHECK_LINT_MAX_CHARS и частичное чтение
#: считал отказом («file too large for function listing»). Бюджет тот же.
READ_BUDGET = 200000


def main(argv):
    if len(argv) < 4:
        sys.stderr.write(
            "usage: _reference_runner.py <reference_python_dir> <tool> <args_json>\n")
        return 2
    ref_root = os.path.abspath(argv[1])
    tool = argv[2]
    try:
        args = json.loads(argv[3])
    except ValueError as exc:
        sys.stderr.write("args не JSON: %s\n" % exc)
        return 2
    sys.dont_write_bytecode = True
    sys.path[:0] = [ref_root, os.path.join(ref_root, "parsers"),
                    os.path.join(ref_root, "godot_tools")]
    if tool == "search":
        return run_search(ref_root, args)
    if tool == "functions":
        return run_functions(ref_root, args)
    if tool == "usages":
        return run_usages(ref_root, args)
    if tool == "analyze_rename":
        return run_analyze_rename(ref_root, args)
    if tool == "write_preview":
        return run_write_preview(ref_root, args)
    if tool == "write_apply":
        return run_write_apply(ref_root, args)
    if tool == "write_rollback":
        return run_write_rollback(ref_root, args)
    sys.stderr.write("неизвестная механика: %r\n" % (tool,))
    return 2


def run_search(ref_root, args):
    if not _require(ref_root, "project_tools.py"):
        return 2
    from godot_tools import project_tools as pt  # noqa: E402 - путь задаётся argv

    matches, truncated = pt.search_project_text(**args)
    return emit({"matches": matches, "truncated": bool(truncated)})


def run_functions(ref_root, args):
    """Повторить путь старого моста `functions`: проверки -> чтение -> gd_functions."""
    if not _require(ref_root, "gd_functions.py"):
        return 2
    from godot_tools import project_tools as pt  # noqa: E402
    import gd_functions  # noqa: E402

    project_root = str(args["project_root"])
    path = str(args.get("path") or "").strip()
    names = [str(name) for name in (args.get("names") or []) if str(name).strip()]
    if not path.lower().endswith(".gd"):
        # Мост: «functions works only for .gd scripts» -> отказ вызова.
        return emit({"ok": False, "kind": "invalid_input"})
    try:
        pt.assert_can_read_project_path(path, project_root)
    except Exception:  # noqa: BLE001 - отказ политики старого агента
        return emit({"ok": False, "kind": "denied"})
    try:
        content, truncated = pt.read_project_file(project_root, path,
                                                  max_chars=READ_BUDGET)
    except Exception:  # noqa: BLE001 - файла нет
        return emit({"ok": False, "kind": "not_found"})
    if truncated:
        # Мост: «file too large for function listing» -> файл прочитан не целиком.
        return emit({"ok": False, "kind": "unavailable"})
    rel = path[len("res://"):] if path.startswith("res://") else path
    if not names:
        return emit({"path": "res://" + rel,
                     "names": gd_functions.list_functions(content)})
    found, missing = gd_functions.extract_functions(content, names)
    return emit({"path": "res://" + rel, "functions": found, "missing": missing})


def run_usages(ref_root, args):
    """Эталонный `find_references`: те же отказы, но без текста наружу (R-15).

    Класс отказа определяется по типу и тексту исключения эталона:
    `LocatorError` — это и «кривой locator» (invalid_input), и «нет такого
    объявления» (not_found); различаем по сообщению, потому что код причины у
    обоих один (`locator`).
    """
    if not _require(ref_root, "symbol_refactor.py"):
        return 2
    from godot_tools import project_tools as pt  # noqa: E402
    import symbol_refactor  # noqa: E402

    project_root = str(args["project_root"])
    action = {key: value for key, value in args.items() if key != "project_root"}
    path = _locator_path(action.get("declaration"))
    if path:
        try:
            pt.assert_can_read_project_path(path, project_root)
            pt._resolve_safe_path(project_root, path)
        except Exception:  # noqa: BLE001 - отказ политики старого агента
            return emit({"ok": False, "kind": "denied"})
    try:
        result = symbol_refactor.find_references(project_root, action)
    except Exception as exc:  # noqa: BLE001 - отказ эталона, текст не переносим
        return emit({"ok": False, "kind": _usage_error_kind(exc)})
    return emit(_usage_result(result))


def _locator_path(value):
    """`res://path.gd:line[:col]` -> путь, если locator синтаксически цел."""
    match = re.match(r"^(res://.+\.gd):\d+(?::\d+)?$", str(value or "").strip())
    return match.group(1) if match else None


def _usage_error_kind(exc):
    message = str(exc)
    if "declaration должен" in message or "должны быть положительными" in message:
        return "invalid_input"
    if getattr(exc, "code", "") == "unsupported":
        return "invalid_input"
    if "kind должен" in message or "идентификатором GDScript" in message:
        return "invalid_input"
    return "not_found"


def _usage_result(result):
    """Ответ эталона -> форма нашего инструмента (без `action`, `note` всегда)."""
    usages = _usage_items(result.get("usages"))
    by_link = {}
    for place in usages:
        by_link[place["link"]] = by_link.get(place["link"], 0) + 1
    return {"kind": result.get("kind"), "old_name": result.get("old_name"),
            "new_name": result.get("new_name"),
            "declaration": result.get("declaration"), "usages": usages,
            "by_link": by_link,
            "proven_count": sum(1 for i in usages if i["confidence"] == "proven"),
            "probable_count": sum(1 for i in usages if i["confidence"] == "probable"),
            "dynamic_count": sum(1 for i in usages if i["confidence"] == "dynamic")}


def run_analyze_rename(ref_root, args):
    """Эталонный `analyze_rename` — обёртка над `find_references` (part2:685-718).

    Отчёт тот же поиск плюс `affected_paths` (только `proven`, сортировка и
    дедупликация) и `risks` строками `path:line [link, confidence] — note`.

    Мост старого агента (`agent_bridge.cmd_analyze_rename`) требовал все три
    строки — `--declaration`, `--old-name`, `--new-name` — и отвечал RC_USAGE;
    здесь это повторяется, потому что сама `symbol_refactor.analyze_rename`
    отсутствие new_name молча пропускает, а клиентская поверхность — мост.
    """
    if not _require(ref_root, "symbol_refactor.py"):
        return 2
    from godot_tools import project_tools as pt  # noqa: E402
    import symbol_refactor  # noqa: E402

    project_root = str(args["project_root"])
    action = {key: value for key, value in args.items() if key != "project_root"}
    if not (str(action.get("declaration") or "").strip()
            and str(action.get("old_name") or "").strip()
            and str(action.get("new_name") or "").strip()):
        return emit({"ok": False, "kind": "invalid_input"})
    path = _locator_path(action.get("declaration"))
    if path:
        try:
            pt.assert_can_read_project_path(path, project_root)
            pt._resolve_safe_path(project_root, path)
        except Exception:  # noqa: BLE001 - отказ политики старого агента
            return emit({"ok": False, "kind": "denied"})
    try:
        result = symbol_refactor.analyze_rename(project_root, action)
    except Exception as exc:  # noqa: BLE001 - отказ эталона, текст не переносим
        return emit({"ok": False, "kind": _usage_error_kind(exc)})
    return emit(_analyze_result(result))


#: Поля эталонного отчёта, которые переносятся как есть (кроме собранных ниже).
ANALYZE_FIELDS = ("kind", "old_name", "new_name", "declaration",
                  "allow_unverified", "mode", "affected_paths", "risks",
                  "declaration_path", "declaration_line")


def _analyze_result(result):
    """Ответ эталона -> форма `analyze_rename` (без служебного `action`)."""
    usages = _usage_items(result.get("usages"))
    answer = {key: result.get(key) for key in ANALYZE_FIELDS}
    answer["usages"] = usages
    answer["by_link"] = {}
    for place in usages:
        answer["by_link"][place["link"]] = answer["by_link"].get(place["link"], 0) + 1
    answer["proven_count"] = sum(1 for i in usages if i["confidence"] == "proven")
    answer["probable_count"] = sum(1 for i in usages if i["confidence"] == "probable")
    answer["dynamic_count"] = sum(1 for i in usages if i["confidence"] == "dynamic")
    return answer


def _usage_items(raw):
    """Место использования в нашей форме: `note` есть всегда (None для proven)."""
    return [{"path": item.get("path"), "line": item.get("line"),
             "column": item.get("column") or 1, "link": item.get("link"),
             "confidence": item.get("confidence"), "note": item.get("note")}
            for item in raw or ()]


def run_write_preview(ref_root, args):
    """Эталонный `prepare_rename` (part3:61-615) -> нормализованный план.

    Переносится только сравнимое: файлы с числом правок, счётчики, эхо входа и
    класс отказа. Диффы, байты и абсолютные пути эталона отбрасываются, а
    смещения правок строит НАШ компилятор — чужие байтовые смещения в план не
    попадают.
    """
    if not _require(ref_root, "symbol_refactor.py"):
        return 2
    from godot_tools import project_tools as pt  # noqa: E402
    import symbol_refactor  # noqa: E402

    project_root = str(args["project_root"])
    action = {key: value for key, value in args.items() if key != "project_root"}
    path = _locator_path(action.get("declaration"))
    if path:
        try:
            pt.assert_can_read_project_path(path, project_root)
            pt._resolve_safe_path(project_root, path)
        except Exception:  # noqa: BLE001 - отказ политики старого агента
            return emit({"ok": False, "kind": "denied"})
    try:
        plan = symbol_refactor.prepare_rename(project_root, action)
    except Exception as exc:  # noqa: BLE001 - отказ эталона, текст не переносим
        return emit({"ok": False, "kind": _rename_error_kind(exc)})
    return emit(_write_preview_result(plan))


def _rename_error_kind(exc):
    """Класс эталонного отказа -> наш `kind` (тексты не переносятся, R-15)."""
    name = type(exc).__name__
    message = str(exc)
    if name == "UnsupportedRenameError":
        return "invalid_input"
    if name == "LocatorError":
        return "not_found"
    if name == "StaleRenameError":
        return "stale_plan"
    if name == "UnsafeRenameError":
        return "conflict"
    if "защищён" in message or "вне зоны записи" in message or "неполон" in message:
        return "denied"
    if name == "RenameError":
        return "conflict"
    return "invalid_input"


#: Поля эталонного плана, которые переносятся как есть (остальное — производное).
WRITE_FIELDS = ("kind", "old_name", "new_name", "declaration", "mode",
                "allow_unverified")


def _write_preview_result(plan):
    """План эталона -> форма `write_preview` без смещений и диффов."""
    steps = [{"path": item.get("path"), "edits": int(item.get("occurrences") or 0)}
             for item in plan.get("files") or ()]
    steps.sort(key=lambda item: str(item["path"]))
    answer = {key: plan.get(key) for key in WRITE_FIELDS}
    answer["state"] = "PREPARED"
    answer["steps"] = steps
    answer["steps_count"] = len(steps)
    answer["affected_paths"] = [item["path"] for item in steps]
    answer["stats"] = {"files": len(steps),
                       "edits": sum(item["edits"] for item in steps),
                       "dynamic": len(plan.get("dynamic_references") or ())}
    answer["excluded"] = len(plan.get("skipped_usages") or ())
    return answer


def _apply_on_copy(ref_root, args, rollback=False):
    """Прогон эталонной записи на копии проекта: (`ok`, хеши) или (`error`, kind)."""
    if not _require(ref_root, "symbol_refactor.py"):
        return "error", "internal"
    import shutil
    import tempfile

    from godot_tools import project_tools as pt  # noqa: E402 - путь задаётся argv
    import symbol_refactor  # noqa: E402

    project_root = str(args["project_root"])
    action = {key: value for key, value in args.items() if key != "project_root"}
    work = tempfile.mkdtemp(prefix="godot_agent_ref_")
    copy = os.path.join(work, "project")
    try:
        shutil.copytree(project_root, copy)
        path = _locator_path(action.get("declaration"))
        if path:
            try:
                pt.assert_can_read_project_path(path, copy)
                pt._resolve_safe_path(copy, path)
            except Exception:  # noqa: BLE001 - отказ политики старого агента
                return "error", "denied"
        plan = symbol_refactor.prepare_rename(copy, action)
        if rollback:
            before = {}
            for item in plan.get("files") or ():
                raw = item.get("before_bytes") or b""
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                before[_rel_target(item.get("path"))] = hashlib.sha256(raw).hexdigest()
            return "ok", dict(sorted(before.items()))
        symbol_refactor.apply_prepared_rename(copy, plan)
        return "ok", _file_hashes(os.path.join(copy, "src"), copy)
    except Exception as exc:  # noqa: BLE001 - отказ эталона, текст не переносим
        return "error", _rename_error_kind(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _file_hashes(root, project_root):
    """sha256 сырых байтов `*.gd` под `root`; ключи — пути от корня проекта."""
    files = {}
    for base, _dirs, names in os.walk(root):
        for name in sorted(names):
            if not name.endswith(".gd"):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, project_root).replace("\\", "/")
            with open(full, "rb") as handle:
                files[rel] = hashlib.sha256(handle.read()).hexdigest()
    return dict(sorted(files.items()))


def _rel_target(path):
    """Путь эталона -> путь от корня проекта (`res://` снимается)."""
    value = str(path or "")
    return value[len("res://"):] if value.startswith("res://") else value


def run_write_apply(ref_root, args):
    """Эталонная запись: ожидание — байты файлов ПОСЛЕ `apply_prepared_rename`."""
    state, payload = _apply_on_copy(ref_root, args)
    if state == "error":
        return emit({"ok": False, "kind": payload})
    return emit({"files": payload})


def run_write_rollback(ref_root, args):
    """Ожидание отката — `before_bytes` плана: байты ДО применения."""
    state, payload = _apply_on_copy(ref_root, args, rollback=True)
    if state == "error":
        return emit({"ok": False, "kind": payload})
    return emit({"files": payload})


def _require(ref_root, file_name):
    module_file = os.path.join(ref_root, "godot_tools", file_name)
    if not os.path.isfile(module_file):
        sys.stderr.write("эталон не найден: %s\n" % module_file)
        return False
    return True


def emit(value):
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
