# tools/selfcheck.py - вердикт по одной механике (R-18).
# Использование: python tools/selfcheck.py <module_id> [--json]
# Коды возврата: 0 - всё зелёное, 1 - есть провал, 2 - проверка невыполнима
#                (нет кода, нет тестов модуля, нет корпуса, нужен живой Godot).
# Контракт проверки: инструмент печатает последней строкой JSON
#   {"status": "ok" | "fail" | "not_implemented" | "needs_live", "detail": "..."}
# Нет валидного вердикта - считаем "not_implemented": пустой скрипт не зелёный.
#
# Проверки адресованы модулю, а не проекту (правка аудита среза 2): `module`
# поднимает реальную сборку и смотрит реестр, `unit` собирает и гоняет тесты
# ЭТОГО модуля (плюс его contract-тесты), `corpus` требует корпус именно этой
# механики. Иначе пустая заготовка получала `ok` на одних общих проверках.

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Проверка не оставляет за собой мусора: импорты проекта идут уже после этой
#: строки, а `-B` дочерним процессам добавляет `run_device`.
sys.dont_write_bytecode = True
MODULES = ROOT / "python" / "modules"
REPORTS = ROOT / "reports" / "selfcheck"
FIXTURE_PROJECT = ROOT / "fixtures" / "projects" / "minimal"
CONTRACTS = ROOT / "tests" / "py" / "contract"

#: Общие проверки проекта: одинаковы для любой механики.
STATIC_CHECKS = [
    ("layers", ["tools/lint_arch.py"]),
    ("limits", ["tools/check_limits.py"]),
    ("contract", ["tools/gen_contract.py", "--check"]),
    ("security", ["tools/security_audit.py"]),
]

_COUNT_RE = re.compile(r":\s*(\d+)\s*$")


def module_dir(module_id):
    area, _, feature = module_id.partition(".")
    return MODULES / area / feature.replace(".", "_")


def rel(path):
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def run_device(argv, timeout=900):
    # Дочерние процессы обязаны писать в UTF-8: иначе на Windows их вердикт
    # приходит в cp1251 и в отчёт попадает мусор. PYTHONDONTWRITEBYTECODE —
    # чтобы проверка не оставляла `__pycache__` в дереве.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    argv = list(argv)
    if argv and argv[0] == sys.executable:
        # `-B` важен отдельно: pytest смотрит на sys.flags.dont_write_bytecode,
        # а не на переменную окружения, и иначе пишет `__pycache__` в дерево.
        argv.insert(1, "-B")
    return subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env=env)


def run_check(name, cmd):
    if cmd[0].startswith("tools/"):
        path = ROOT / cmd[0]
        if not path.exists():
            return "not_implemented", "нет файла %s" % cmd[0]
        argv = [sys.executable, str(path)] + cmd[1:]
    else:
        argv = [sys.executable] + cmd
    try:
        done = run_device(argv)
    except OSError as exc:
        return "not_implemented", "не запускается: %s" % exc
    except subprocess.TimeoutExpired:
        return "fail", "таймаут"
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    if lines:
        try:
            verdict = json.loads(lines[-1])
        except ValueError:
            verdict = None
        if isinstance(verdict, dict) and verdict.get("status"):
            return verdict["status"], verdict.get("detail", "")
    if done.returncode == 0:
        return "not_implemented", "нет вердикта (пустая заготовка)"
    if "No module named" in (done.stderr or ""):
        return "not_implemented", "нет зависимости: %s" % done.stderr.strip().splitlines()[-1]
    return "fail", "код %d" % done.returncode



def _catalogue():
    """Все загруженные модули и причины отказов (один импорт на прогон)."""
    if not hasattr(_catalogue, "cache"):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from python.runtime.module_loader import discover

        _catalogue.cache = discover()
    return _catalogue.cache


def _spec(module_id):
    loaded, failed = _catalogue()
    spec = next((item.spec for item in loaded if item.spec.id == module_id), None)
    reason = next((item.get("reason", "") for item in failed
                   if item.get("module") == module_id), "")
    return spec, reason


def module_readiness(spec, has_tests, has_corpus, reason=""):
    """Готов ли модуль по манифесту и фактам дерева → `(status, detail)`.

    Чистая функция: каталоги смотрят вызывающие, решение принимается здесь. Иначе
    «вклад без собственных инструментов» остаётся непроверенным поведением: первый
    настоящий вклад (`context.editor_context`) показывал бы что угодно, и никто бы
    не заметил подмены `ok` на `fail`.

    Корпус не обязателен: у вклада его нет по природе (схемы и фейк вместо кейсов),
    у модуля с инструментами его проверяет отдельная строка `corpus` — здесь корпус
    только упоминается в `detail`, чтобы пропуск был виден.
    """
    if spec is None:
        return "not_implemented", "заготовка: %s" % (reason or "модуль не загрузился")
    tools = tuple(getattr(spec, "provides_tools", ()) or ())
    contributes = tuple(getattr(spec, "contributes_to", ()) or ())
    if not tools and not contributes:
        internal = (getattr(spec, "internal_services", ()) or getattr(spec, "entrypoints", {}))
        if not internal:
            return "fail", "ModuleSpec без provides_tools и contributes_to"
        if not has_tests:
            return "not_implemented", "нет tests у %s" % spec.id
        if not has_corpus:
            return "not_implemented", "нет корпуса механики: %s" % spec.id
        return "ok", "%s (internal-only)" % spec.id
    if not tools:
        if not has_tests:
            return "not_implemented", "у вклада в %s нет tests" % ", ".join(contributes)
        return "ok", "%s (вклад в %s)" % (spec.id, ", ".join(contributes))
    if not has_tests:
        return "not_implemented", "нет tests у %s" % spec.id
    detail = "%s (%s)" % (spec.id, ", ".join(tools))
    if not has_corpus:
        detail += ", корпуса нет: проверяется строкой corpus"
    return "ok", detail


def check_module(module_id, here):
    """Модуль собран по-настоящему: манифест, регистрация, инструменты в реестре."""
    if not here.exists():
        return "fail", "нет папки %s" % rel(here)
    spec, reason = _spec(module_id)
    status, detail = module_readiness(spec, (here / "tests").exists(),
                                      bool(corpus_folders(module_id)), reason)
    if status != "ok":
        return status, detail
    if not FIXTURE_PROJECT.is_dir():
        return "not_implemented", "нет %s" % rel(FIXTURE_PROJECT)
    from python.runtime.bootstrap import build_agent

    profile = "editor" if spec.environment == "editor" else "test"
    agent = build_agent(project_root=str(FIXTURE_PROJECT), profile=profile)
    disabled = agent.disabled()
    if module_id in disabled:
        return "fail", "модуль отключён: %s" % disabled[module_id]
    if not tuple(spec.provides_tools):
        return "ok", detail
    names = [tool.get("name") for tool in agent.tools()]
    missing = [name for name in spec.provides_tools if name not in names]
    if missing:
        return "fail", "инструментов нет в реестре: %s" % ", ".join(missing)
    return "ok", detail


def collect_count(targets):
    """Сколько тестов собирается в целях (None, если pytest не запускается)."""
    argv = [sys.executable, "-m", "pytest"] + [str(t) for t in targets] + [
        "-q", "--collect-only", "--import-mode=importlib"]
    try:
        done = run_device(argv, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = done.stdout or ""
    ids = sum(1 for line in text.splitlines() if "::" in line)
    if ids:
        return ids
    summary = 0
    for line in text.splitlines():
        match = _COUNT_RE.search(line.strip())
        if match:
            summary += int(match.group(1))
    return summary


def check_unit(module_id, here):
    """Тесты именно этого модуля (contract-тесты инструментов и интеграционные).

    Интеграционные тесты (`tests/py/integration/test_<фича>*.py`) проверяют
    модуль вместе с подложкой — стиль файла, BOM, реакции портов, — а не только
    домен. Без них `unit` оставался зелёным, пока интеграция падала: дыра того
    же вида, что «проверка по имени фичи» (R-18).
    """
    tests = here / "tests"
    if not tests.exists():
        return "not_implemented", "нет %s/tests" % rel(here)
    targets = [tests]
    spec, _reason = _spec(module_id)
    area, _, feature = module_id.partition(".")
    names = [feature.replace(".", "_")] + list(spec.provides_tools if spec else ())
    integration = ROOT / "tests" / "py" / "integration"
    for tool in (spec.provides_tools if spec else ()):
        contract = CONTRACTS / ("test_%s_contract.py" % tool)
        if contract.exists():
            targets.append(contract)
    tools = {t for item in _catalogue()[0] for t in item.spec.provides_tools}
    def _owner(stem):
        cands = [t for t in tools if stem == t or stem.startswith(t + "_")]
        return max(cands, key=len) if cands else None
    for name in dict.fromkeys(names):
        for extra in sorted(integration.glob("test_%s*.py" % name)):
            own = _owner(extra.stem[len("test_"):])
            if name in tools and own is not None and own != name:
                continue
            targets.append(extra)
    count = collect_count(targets)
    if count is None:
        return "not_implemented", "pytest не запускается"
    if count == 0:
        return "not_implemented", "тестов модуля нет: %s" % ", ".join(rel(t) for t in targets)
    return run_check("unit", ["tools/run_tests.py"] + [rel(t) for t in targets])


def corpus_folders(module_id):
    """Корпуса модуля: папка фичи и папки его инструментов.

    У модуля с двумя инструментами два корпуса (`usages`, `analyze_rename`) со
    своими манифестами; selfcheck обязан видеть оба, иначе кейсы второго
    инструмента никем не проверяются.
    """
    area, _, feature = module_id.partition(".")
    base = ROOT / "fixtures" / "corpus" / area
    spec, _reason = _spec(module_id)
    names = [feature.replace(".", "_")] + list(spec.provides_tools if spec else ())
    folders = []
    for name in dict.fromkeys(names):
        folder = base / name
        if (folder / "manifest.json").exists():
            folders.append(folder)
    for manifest in sorted(base.glob("*/manifest.json")):
        if manifest.parent not in folders and json.loads(manifest.read_text(encoding="utf-8")).get("module") == module_id:
            folders.append(manifest.parent)
    return folders


#: Живые тесты: по упоминанию `module_id` в `tests/py/live/*.py` (R-18).
LIVE_DIR = ROOT / "tests" / "py" / "live"


def live_tests(module_id):
    """Файлы живых тестов этой механики: в них назван `module_id`."""
    if not LIVE_DIR.is_dir():
        return []
    return sorted(path for path in LIVE_DIR.glob("*.py")
                  if module_id in path.read_text(encoding="utf-8", errors="replace"))


def corpus_readiness(policy, module_id, folders, live):
    """Судьба корпуса: `ok` / `not_implemented` / `corpus` (идти в snapshot_diff).

    `corpus` - снапшоты эталона (`tools/snapshot_record.py`), `live` - механика
    исполняется в GDScript, эталонной Python-функции нет, поэтому доказательство -
    живой тест. Флаг без живого теста - `not_implemented`, а не «зелено».
    """
    if str(policy or "corpus") == "live":
        if live:
            return "ok", "корпус live: исполнение в GDScript, доказательство - %s" % (
                ", ".join(rel(item) for item in live))
        return "not_implemented", ("корпус live без живого теста: нужен файл "
                                   "tests/py/live/*.py с упоминанием %s" % module_id)
    if not folders:
        return "not_implemented", "нет корпуса механики: %s" % rel(
            ROOT / "fixtures" / "corpus" / module_id.replace(".", "/"))
    return "corpus", ""


def check_corpus(module_id):
    """Корпус именно этой механики (все её инструменты), а не «общий корпус»."""
    spec, _reason = _spec(module_id)
    folders = corpus_folders(module_id)
    if spec is not None and not tuple(spec.provides_tools) and not folders:
        return "ok", "корпуса нет: вклад в %s (схемы и фейк вместо корпуса)" % (
            ", ".join(getattr(spec, "contributes_to", ())) or "?")
    if spec is not None:
        status, detail = corpus_readiness(str(getattr(spec, "corpus", "corpus")),
                                          module_id, folders, live_tests(module_id))
        if status != "corpus":
            return status, detail
    if not folders:
        return "not_implemented", "нет корпуса механики: %s" % rel(
            ROOT / "fixtures" / "corpus" / module_id.replace(".", "/"))
    status, detail = run_check("corpus", ["tools/snapshot_diff.py", module_id])
    if status == "ok" and "кейсов 0" in detail:
        return "not_implemented", "корпус пуст: %s" % ", ".join(rel(f) for f in folders)
    return status, detail


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: selfcheck.py <module_id> [--json]\n")
        return 2
    module_id = argv[1]
    here = module_dir(module_id)
    rows = [("module",) + check_module(module_id, here)]
    for name, cmd in STATIC_CHECKS:
        rows.append((name,) + run_check(name, cmd))
    rows.append(("unit",) + check_unit(module_id, here))
    rows.append(("corpus",) + check_corpus(module_id))
    worst = "ok"
    for _name, status, _detail in rows:
        if status == "fail":
            worst = "fail"
            break
        if status in ("not_implemented", "needs_live"):
            worst = "blocked"
    report = {"module": module_id, "verdict": worst,
              "checks": [{"check": n, "status": s, "detail": d} for n, s, d in rows]}
    if "--json" in argv:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print("selfcheck %s" % module_id)
        for name, status, detail in rows:
            print("  %-14s %-15s %s" % (name, status, detail))
        print("вердикт: %s" % worst)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / ("%s.json" % module_id)).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if worst == "fail":
        return 1
    if worst == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
