# tools/lint_arch.py - проверка границ слоёв (R-11).
# Использование: python tools/lint_arch.py [--json]
# Направление: channels -> protocol -> modules -> formats -> kernel;
# substrate реализует порты и импортируется только runtime; runtime - композиционный
# корень. Модуль не импортирует чужой domain/, substrate, protocol, channels, editor.
# Контракт проверки: последняя строка - JSON {"status": ..., "detail": ...}.

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
PREFIX = "python."

LAYERS = ("kernel", "formats", "modules", "protocol", "channels", "substrate", "runtime")

ALLOWED = {
    "kernel": (),
    "formats": ("kernel",),
    "modules": ("kernel", "formats"),
    "protocol": ("kernel",),
    "substrate": ("kernel",),
    # Каналу разрешён композиционный корень: точка входа вызывает build_agent(),
    # не зная ни модулей, ни адаптеров (ADR-0003). Прямой импорт substrate запрещён.
    "channels": ("kernel", "protocol", "runtime"),
    "runtime": LAYERS,
}

#: Модули, которые в `domain/` запрещены (R-11: домен не выполняет IO).
#: Проверяются обе формы: `import X` и `from X import ...`; `kernel/` не покрыт —
#: там `paths.py` законно импортирует `os`, а `write_plan.py` — `json`.
IO_MODULES = ("os", "io", "pathlib", "shutil", "json", "subprocess", "socket",
              "tempfile", "sqlite3", "urllib", "http")


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return {"ok": 0, "fail": 1}.get(status, 1)


def package_of(name):
    """Пакет для импортированного имени: каталог, если он есть, иначе родитель."""
    parts = name.split(".")
    path = PYTHON.joinpath(*parts)
    if path.is_dir():
        return ".".join(parts)
    return ".".join(parts[:-1])


def layer_of(name):
    parts = name.split(".")
    if len(parts) < 2 or parts[0] != "python":
        return None
    return parts[1] if parts[1] in LAYERS else None


def imports_of(path):
    """Абсолютные имена импортов файла (относительные разворачиваются в пакет)."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                found.append(base + ("." + node.module if node.module else ""))
            elif node.module:
                found.append(node.module)
    return found


def io_imports_of(path):
    """IO-импорты файла: пары (строка, модуль) для `import X` и `from X import ...`."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in IO_MODULES:
                found.append((node.lineno, root))
    return sorted(found)


def files():
    return sorted(path for path in PYTHON.rglob("*.py")
                  if "__pycache__" not in path.parts)


def is_domain(path):
    """Домен модуля: `python/modules/<область>/<фича>/domain/**` (R-11)."""
    parts = path.relative_to(PYTHON).parts
    return len(parts) >= 5 and parts[0] == "modules" and parts[3] == "domain"


def check_domain_io(path):
    """В `domain/` нет IO: файл:строка и запрещённый модуль."""
    if not is_domain(path):
        return []
    rel = path.relative_to(ROOT).as_posix()
    return ["%s:%d: в domain/ запрещён IO-импорт %s" % (rel, line, name)
            for line, name in io_imports_of(path)]


def check_edges(path):
    violations = []
    rel = path.relative_to(ROOT).as_posix()
    source_layer = layer_of(".".join(path.relative_to(ROOT).with_suffix("").parts))
    if source_layer is None:
        return violations
    here = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    for name in imports_of(path):
        target_layer = layer_of(name)
        if target_layer is None:
            continue
        if target_layer == source_layer and source_layer != "modules":
            continue
        if target_layer == source_layer == "modules":
            # ADR-0010: one exact app edge; not foreign shared/domain in general.
            if (rel == "python/modules/verification/api_check/app.py"
                    and name == "python.modules.engine_kb.shared.inheritance"):
                continue
            # ADR-0016/D8: only the declared C.22 -> C.21 public package edge.
            if (rel.startswith("python/modules/editing/file_refactor/")
                    and name == "python.modules.editing.paths_preview"):
                continue
            if not _same_feature(here, name):
                violations.append("%s: модуль импортирует чужой модуль %s" % (rel, name))
            continue
        if source_layer == "modules" and target_layer in ("substrate", "protocol",
                                                          "channels", "runtime"):
            violations.append("%s: модуль импортирует слой %s (%s)"
                              % (rel, target_layer, name))
            continue
        if target_layer not in ALLOWED[source_layer]:
            violations.append("%s: %s не может импортировать %s (%s)"
                              % (rel, source_layer, target_layer, name))
    return violations


def _target_parts(name):
    """Части пакета импортированного имени: сам пакет, иначе его родитель.

    Имена импортов абсолютные (`python.modules...`), поэтому путь строится от
    `ROOT`: `package_of` отталкивается от `PYTHON` и для проектных имён всегда
    возвращает родителя, чего здесь мало (нужен и сам пакет: `from . import x`).
    """
    parts = name.split(".")
    if ROOT.joinpath(*parts).is_dir():
        return parts
    return parts[:-1]


def _same_feature(here, name):
    mine = here.split(".")
    theirs = _target_parts(name)
    # Сравнение идёт по `python.modules.<область>.<фича>`: импорт корня области
    # (`from python.modules import scene_model`) — это чужая фича, а не «короткое
    # имя», поэтому короткие имена больше не считаются своими (лазейка `len < 4`).
    if len(mine) < 4 or len(theirs) < 3:
        return False
    # Граница — область (python.modules.<область>): внутри неё модулю доступен
    # общий код области (`shared/`, R-11) и собственный пакет. Раньше сравнение
    # шло по четырём частям, из-за чего ветка `shared` была недостижима.
    if mine[:3] != theirs[:3]:
        return False
    if len(theirs) == 3:
        # Корень своей области: у него нет чужой фичи, только общий пакет.
        return True
    if theirs[3] == "shared":
        return True
    # Своя фича целиком (включая `tests/` и `domain/`) — своя, чужая — нет.
    return theirs[2:4] == mine[2:4]


def check_cycles():
    graph = {}
    for path in files():
        here = package_of(".".join(path.relative_to(ROOT).with_suffix("").parts))
        for name in imports_of(path):
            if layer_of(name) is None:
                continue
            target = package_of(name)
            if target == here:
                continue
            graph.setdefault(here, set()).add(target)
    violations = []
    for start in sorted(graph):
        stack = [(start, [start])]
        while stack:
            node, trail = stack.pop()
            for neighbour in sorted(graph.get(node, ())):
                if neighbour == start:
                    violations.append("цикл: %s" % " -> ".join(trail + [neighbour]))
                elif neighbour not in trail:
                    stack.append((neighbour, trail + [neighbour]))
    return sorted(set(violations))


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args(argv[1:])
    violations = []
    for path in files():
        violations.extend(check_edges(path))
        violations.extend(check_domain_io(path))
    violations.extend(check_cycles())
    if options.json:
        print(json.dumps({"violations": violations}, ensure_ascii=False))
    for item in violations:
        print("fail: %s" % item)
    if violations:
        return verdict("fail", "; ".join(violations[:3]))
    return verdict("ok", "файлов %d, нарушений нет" % len(files()))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
