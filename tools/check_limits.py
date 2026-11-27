# tools/check_limits.py - счётчик лимитов (R-06).
# Использование: python tools/check_limits.py [--json]
# Жёстко: файл <= 400 строк, module.py/tools.py <= 150, app.py <= 80,
# модуль <= 3000, область <= 8400. Мягко: область (8000,8400] и папка 5-9
# элементов (R-06/D18: documented cohesion в docs/deviations.md).
# Контракт проверки: последняя строка - JSON {"status": ..., "detail": ...}.

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
MODULES = PYTHON / "modules"

FILE_MAX = 400
# D29: verbatim-эталоны substrate/llm/browser/ — R-08 против R-06: сплочённый
# класс резать запрещено (D24-прецедент), байтовый паритет важнее FILE_MAX.
# Правило классовое — по каталогу verbatim-эталонов, не по одному файлу.
VERBATIM_DIRS = ("python/substrate/llm/browser",)
VERBATIM_FILE_MAX = 600
# D32/B.1: byte-exact parser class (parser_base 3352); browser/default caps unchanged.
PARSER_VERBATIM_DIR = "python/substrate/llm/parsers"
PARSER_VERBATIM_FILE_MAX = 3400
# D35/API-core: byte-exact API references; entry/default/browser caps unchanged.
API_VERBATIM_DIR = "python/substrate/llm/api"
API_VERBATIM_FILE_MAX = 3400
# D38/routing-runtime: dedicated reference directories, not editor transport.
ROUTING_VERBATIM_DIRS = ("python/substrate/editor/references", "python/substrate/llm/backends")
ROUTING_VERBATIM_FILE_MAX = 3400
# D39/project-core: byte-exact project class; entry and all other caps unchanged.
PROJECT_VERBATIM_DIR = "python/substrate/project"
PROJECT_VERBATIM_FILE_MAX = 2000
# D42: narrow byte-exact engine/history/verification reference directories.
ENGINE_CACHE_VERBATIM_DIRS = ("python/substrate/engine", "python/substrate/store", "python/substrate/verification")
ENGINE_CACHE_VERBATIM_FILE_MAX = 3400
# D47: byte-exact context references; descendants only, entry caps still win.
CONTEXT_VERBATIM_DIR = "python/substrate/context"
CONTEXT_VERBATIM_FILE_MAX = 3400
# D60: measured J1 native references, exact paths only; no directory exemption.
J1_NATIVE_CAPS = {
    "python/substrate/editing/file_refactor.py": 1457,
    "python/substrate/code_intel/symbol_refactor_part1.py": 824,
    "python/substrate/code_intel/symbol_refactor_part2.py": 718,
    "python/substrate/code_intel/symbol_refactor_part3.py": 714,
    "python/substrate/assistant/answer_judge.py": 492,
    "python/substrate/scene/scene_deps.py": 412,
}
ENTRY_MAX = {"module.py": 150, "tools.py": 150, "app.py": 80}
T1_NATIVE_CAPS = {
    'python/substrate/editing/arch_map.py': 454,
    'python/substrate/editing/node_refactor.py': 1095,
    'python/substrate/editing/split_gd.py': 1333,
    'python/substrate/editing/split_refactor.py': 872,
    'python/substrate/code_intel/function_card.py': 751,
}
SERVER_NATIVE_CAPS = {
    "python/substrate/assistant/server/chat_routes.py": (1080, "f09f5fecd8c753d5820067545fa342955292e4e915f25caa6885ecf04661b395"),
    "python/substrate/assistant/server/server_state.py": (832, "efecb557b45c4a6e0ea4a4b806027cab20f07af8bda6a6e72f3e297575300c1e"),
}
MODULE_MAX = 3000
AREA_MAX = 8000
AREA_COHESION_MAX = 8400
FOLDER_MIN, FOLDER_MAX = 5, 9


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return {"ok": 0, "fail": 1}.get(status, 1)


def line_count(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def python_files():
    return sorted(path for path in PYTHON.rglob("*.py")
                  if "__pycache__" not in path.parts)


def check_files():
    violations = []
    for path in python_files():
        lines = line_count(path)
        rel = path.relative_to(ROOT).as_posix()
        limit = ENTRY_MAX.get(path.name, FILE_MAX)
        if any(rel.startswith(vdir + "/") for vdir in VERBATIM_DIRS):
            limit = VERBATIM_FILE_MAX
        if rel.startswith(PARSER_VERBATIM_DIR + "/"):
            limit = PARSER_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and rel.startswith(API_VERBATIM_DIR + "/"):
            limit = API_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and any(rel.startswith(d + "/") for d in ROUTING_VERBATIM_DIRS):
            limit = ROUTING_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and rel.startswith(PROJECT_VERBATIM_DIR + "/"):
            limit = PROJECT_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and any(rel.startswith(folder + "/") for folder in ENGINE_CACHE_VERBATIM_DIRS):
            limit = ENGINE_CACHE_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and rel.startswith(CONTEXT_VERBATIM_DIR + "/"):
            limit = CONTEXT_VERBATIM_FILE_MAX
        if path.name not in ENTRY_MAX and rel in J1_NATIVE_CAPS:
            limit = J1_NATIVE_CAPS[rel]
        if path.name not in ENTRY_MAX and rel in T1_NATIVE_CAPS:
            limit = T1_NATIVE_CAPS[rel]
        if path.name not in ENTRY_MAX and rel in SERVER_NATIVE_CAPS:
            cap, digest = SERVER_NATIVE_CAPS[rel]
            if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                limit = cap
        if lines > limit:
            violations.append("%s: %d строк (лимит %d)" % (rel, lines, limit))
    return violations


def module_dirs():
    return sorted(path.parent for path in MODULES.glob("*/*/module.py"))


def check_totals():
    violations, warnings = [], []
    for folder in module_dirs():
        total = sum(line_count(path) for path in folder.rglob("*.py"))
        if total > MODULE_MAX:
            violations.append("%s: модуль %d строк (лимит %d)"
                              % (folder.relative_to(ROOT).as_posix(), total, MODULE_MAX))
        items = [item for item in folder.iterdir() if item.name != "__pycache__"]
        if not FOLDER_MIN <= len(items) <= FOLDER_MAX:
            warnings.append("%s: %d элементов (норма %d-%d)"
                            % (folder.relative_to(ROOT).as_posix(), len(items),
                               FOLDER_MIN, FOLDER_MAX))
    for area in sorted(path for path in MODULES.glob("*") if path.is_dir()):
        total = sum(line_count(path) for path in area.rglob("*.py"))
        if total > AREA_COHESION_MAX:
            violations.append("%s: область %d строк (cohesion-потолок %d, база %d)"
                               % (area.relative_to(ROOT).as_posix(), total, AREA_COHESION_MAX, AREA_MAX))
        elif total > AREA_MAX:
            warnings.append("%s: область %d строк (база %d, cohesion-потолок %d, R-06/D18)"
                            % (area.relative_to(ROOT).as_posix(), total, AREA_MAX, AREA_COHESION_MAX))
    return violations, warnings


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    parser.parse_args(argv[1:])
    violations = check_files()
    total_violations, warnings = check_totals()
    violations.extend(total_violations)
    if "--json" in argv:
        print(json.dumps({"violations": violations, "warnings": warnings},
                         ensure_ascii=False))
    for item in warnings:
        print("warning: %s" % item)
    if violations:
        for item in violations:
            print("fail: %s" % item)
        return verdict("fail", "; ".join(violations[:3]))
    return verdict("ok", "файлов %d, предупреждений %d"
                   % (len(python_files()), len(warnings)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
