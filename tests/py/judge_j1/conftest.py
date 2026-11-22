"""Own B fixtures restore package-child attributes as well as sys.modules."""
import sys
from types import ModuleType
import pytest


def children(package):
    return {key: value for key, value in vars(package).items()
            if isinstance(value, ModuleType) and
            value.__name__ == package.__name__ + '.' + key}


@pytest.fixture(autouse=True)
def isolated_import_generations():
    before = dict(sys.modules)
    packages = {module: children(module) for module in set(before.values())
                if isinstance(module, ModuleType) and hasattr(module, '__path__')}
    for package, attributes in packages.items():
        for key, cached in attributes.items():
            current = before.get(cached.__name__)
            if current is None:
                delattr(package, key)
            else:
                setattr(package, key, current)
    try:
        yield
    finally:
        sys.modules.clear()
        sys.modules.update(before)
        for package, attributes in packages.items():
            for key in children(package).keys() - attributes.keys():
                delattr(package, key)
            vars(package).update(attributes)
