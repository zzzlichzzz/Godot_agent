"""Fresh K1 test generation only: restore aliases AND cached package children."""
import ast
from pathlib import Path
import sys
from types import ModuleType
import pytest

@pytest.fixture(autouse=True)
def isolated_chat_native_generation():
    source=Path(__file__).resolve().parents[3]/'python/substrate/llm/runtime_bindings.py'
    tree=ast.parse(source.read_text('utf-8'))
    bindings=next(n.value for n in tree.body if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='BINDINGS' for t in n.targets))
    aliases={row[0] for row in ast.literal_eval(bindings)}
    def managed(name):
        return name in aliases or name=='minilich' or name.startswith('minilich.') or name=='python.substrate' or name.startswith('python.substrate.')
    def attributes(module):
        return {key:value for key,value in vars(module).items() if isinstance(value,ModuleType) and managed(value.__name__)}
    saved={name:value for name,value in sys.modules.items() if managed(name)}
    parents={module:attributes(module) for module in set(sys.modules.values()) if isinstance(module,ModuleType)}
    for parent,values in parents.items():
        for key in values: vars(parent).pop(key,None)
    for name in saved: sys.modules.pop(name,None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if managed(name): sys.modules.pop(name,None)
        sys.modules.update(saved)
        for parent,values in parents.items():
            for key in attributes(parent): vars(parent).pop(key,None)
            vars(parent).update(values)
