"""tools/lint_arch.py: граница модуля внутри области (R-11).

R-11 разрешает модулю свой пакет и общий код своей области (`shared/`), а чужую
область — нет. Ветка `shared` была недостижима (сравнение шло по четырём частям),
поэтому первый же вклад-владелец (`context.gather` → `context/shared`) получал
`fail`. Здесь закреплено поведение, на которое опираются эти вклады.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    path = ROOT / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location("tool_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lint = _load("lint_arch")
HERE = "python.modules.context.gather"


def test_own_area_shared_is_allowed():
    assert lint._same_feature(HERE, "python.modules.context.shared.context_section")


def test_own_package_is_allowed():
    assert lint._same_feature(HERE, "python.modules.context.gather.domain.core")
    assert lint._same_feature(HERE, "python.modules.context.gather.app")


def test_foreign_area_is_refused():
    assert not lint._same_feature(HERE, "python.modules.editing.shared.operation_compiler")
    assert not lint._same_feature(HERE, "python.modules.code_intel.usages.app")
