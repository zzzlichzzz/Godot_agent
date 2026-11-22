"""D47 narrow directory class; entry/default and adjacent classes remain frozen."""
from importlib import util
from pathlib import Path
from unittest.mock import patch
import pytest
from tests.py.context.observations import ROOT

@pytest.mark.parametrize('relative,lines,allowed',[
    ('python/substrate/context/librarian.py',1551,True),
    ('python/substrate/context/deep/ref.py',3400,True),
    ('python/substrate/context/deep/ref.py',3401,False),
    ('python/substrate/context/module.py',151,False),
    ('python/substrate/context/tools.py',151,False),
    ('python/substrate/context/app.py',81,False),
    ('python/substrate/contextual/ref.py',401,False),
    ('python/substrate/context.py',401,False),
    ('python/substrate/elsewhere/ref.py',401,False),
    ('python/substrate/context/app.py',80,True),
    ('python/substrate/context/deep/ref.py',400,True),
])
def test_context_class(relative,lines,allowed):
    spec=util.spec_from_file_location('librarian_limits',ROOT/'tools/check_limits.py')
    checker=util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    with patch.object(checker,'python_files',return_value=[ROOT/relative]), \
         patch.object(checker,'line_count',return_value=lines):
        assert (not checker.check_files()) is allowed
    assert checker.FILE_MAX==400 and checker.ENTRY_MAX=={'module.py':150,'tools.py':150,'app.py':80}
    assert checker.MODULE_MAX==3000 and checker.AREA_MAX==8000 and checker.AREA_COHESION_MAX==8400

def test_binding_source_budget():
    raw=(ROOT/'python/substrate/llm/runtime_bindings.py').read_bytes()
    assert raw.count(b'\n')==84
