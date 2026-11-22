"""runtime/module_loader.py - обнаружение модулей сканированием (R-03, R-05).

Модуль подключается наличием папки `modules/<область>/<фича>/module.py`, а не
импортом из общего файла. Ошибка импорта одного модуля не мешает остальным:
она попадает в `failed` и превращается в `disabled` с причиной.
"""

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = Path(__file__).resolve().parents[1] / "modules"


@dataclass(frozen=True)
class LoadedModule:
    """Модуль глазами композиционного корня: манифест, дескрипторы, вклады."""

    spec: object
    tools: tuple
    module: object
    contributions: tuple = ()


def module_paths(base=None):
    return sorted(Path(base or MODULES_DIR).glob("*/*/module.py"))


def package_name(path):
    return ".".join(Path(path).relative_to(ROOT).with_suffix("").parts)


def _short_name(path):
    path = Path(path)
    return "%s.%s" % (path.parent.parent.name, path.parent.name)


def load_one(path):
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    package = package_name(path)
    module = importlib.import_module(package)
    spec = getattr(module, "MODULE", None)
    if spec is None:
        raise RuntimeError("%s: нет MODULE (R-05)" % package)
    tools_module = importlib.import_module(package.rsplit(".", 1)[0] + ".tools")
    tools = tuple(getattr(tools_module, "TOOLS", ()) or ())
    if not (spec.provides_tools or spec.internal_services or spec.entrypoints):
        raise RuntimeError("%s: нет TOOLS (ADR-0006)" % package)
    names = tuple(tool.name for tool in tools)
    if tuple(spec.provides_tools) != names:
        raise RuntimeError("%s: provides_tools %s != TOOLS %s"
                           % (package, tuple(spec.provides_tools), names))
    contributions = tuple(getattr(tools_module, "CONTRIBUTIONS", ()) or ())
    return LoadedModule(spec, tools, module, contributions)



def discover(base=None):
    """Все модули проекта: `(loaded, failed)`; ни один отказ не прерывает обход."""
    loaded, failed = [], []
    for path in module_paths(base):
        try:
            loaded.append(load_one(path))
        except Exception as exc:  # noqa: BLE001 - изоляция отказов модулей (R-03)
            failed.append({"module": _short_name(path),
                           "reason": "%s: %s" % (type(exc).__name__, exc)})
    return loaded, failed

