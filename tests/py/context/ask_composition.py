"""Headless public-ask integration composition; never a production module edge."""
from contextlib import contextmanager
import sys
from types import ModuleType


@contextmanager
def isolated_activation():
    """Fresh native modules and exact registry/package restoration per public test."""
    saved = dict(sys.modules)
    packages = [(module, {name: value for name, value in vars(module).items()
                          if isinstance(value, ModuleType)})
                for module in saved.values() if isinstance(module, ModuleType)
                and '__path__' in vars(module)]
    for name, module in list(sys.modules.items()):
        target = getattr(module, '__name__', '')
        if name == 'python.substrate' or name.startswith('python.substrate.') or \
                target.startswith('python.substrate.') or name == 'minilich' or name.startswith('minilich.'):
            sys.modules.pop(name, None)
    for module, attributes in packages:
        for name, value in attributes.items():
            target = getattr(value, '__name__', '')
            if target == 'python.substrate' or target.startswith('python.substrate.'):
                vars(module).pop(name, None)
    try:
        yield
    finally:
        sys.modules.clear()
        sys.modules.update(saved)
        for module, attributes in packages:
            for name, value in list(vars(module).items()):
                if isinstance(value, ModuleType) and name not in attributes:
                    vars(module).pop(name, None)
            vars(module).update(attributes)


def adapter_for(project, state_dir, addon_dir):
    from python.substrate.context.librarian_read import LibrarianRead
    return LibrarianRead(project, state_dir, addon_dir)


def headless_ports(project, state_dir, addon_dir=None):
    from python.runtime.bootstrap import default_ports
    ports = default_ports(project, "headless", state_dir)
    if addon_dir is not None:
        ports["librarian"] = adapter_for(project, state_dir, addon_dir)
    return ports


def headless_agent(project, state_dir, ports=None):
    from python.runtime.bootstrap import build_agent
    return build_agent(project, profile="headless", state_dir=state_dir, ports=ports)
