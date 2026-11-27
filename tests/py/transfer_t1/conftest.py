"""Keep T1 generations separate from the independently sealed K1 corpus."""
import sys
import pytest
from tests.py.chat_k1.isolation import isolated_chat_native_generation

@pytest.fixture(autouse=True)
def extra_aliases():
    names = ('arch_map', 'gd_functions', 'log_reader', 'node_refactor',
             'split_gd', 'split_refactor', 'function_card', 'gather_context')
    before = {name: sys.modules[name] for name in names if name in sys.modules}
    for name in names:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(before)
