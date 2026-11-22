"""Owned synthetic parent hook for explicit D46 reference registration only."""
from importlib import import_module
import sys
from types import ModuleType

_PARENT, _ABSENT = ModuleType('minilich'), object()


def bind_parent(added):
    """Called under runtime_bindings lock/try; its original rollback owns additions."""
    previous = sys.modules.get('minilich', _ABSENT)
    if previous is not _ABSENT and previous is not _PARENT:
        raise RuntimeError('legacy parent already bound: minilich')
    data = import_module('python.substrate.context.ml_data')
    index = import_module('python.substrate.context.ml_project_index')
    _PARENT.ml_data, _PARENT.ml_project_index = data, index
    if previous is _ABSENT:
        sys.modules['minilich'] = _PARENT
        added.append(('minilich', _PARENT))
    for name, module in (('minilich.ml_data', data), ('minilich.ml_project_index', index)):
        previous = sys.modules.get(name, _ABSENT)
        if previous is not _ABSENT and previous is not module:
            raise RuntimeError('legacy child already bound: ' + name)
        if previous is _ABSENT:
            sys.modules[name] = module
            added.append((name, module))
