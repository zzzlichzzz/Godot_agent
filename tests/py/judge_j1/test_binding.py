from importlib import import_module
import json
import sys
from types import ModuleType
from unittest.mock import patch
import pytest
from tests.py.context.observations import references
from .observations import CORPUS

def test_real_register_dotted_children(tmp_path):
    with references(tmp_path/'isolated') as subjects:
        binding=import_module('python.substrate.llm.runtime_bindings')
        binding.register()
        assert import_module('minilich.ml_data') is subjects['data']
        assert import_module('minilich.ml_project_index') is subjects['index']
        assert import_module('minilich.ml_project_index').search is subjects['index'].search

def test_append_only_fifteen_aliases_and_exact_budget(tmp_path):
    with references(tmp_path/'aliases'):
        binding=import_module('python.substrate.llm.runtime_bindings')
        old=json.loads((CORPUS/'inputs/old_bindings.json').read_text('utf-8'))
        assert [list(x) for x in binding.BINDINGS[:35]]==old
        assert len(binding.BINDINGS)==50
        assert open(binding.__file__,'rb').read().count(b'\n')==84
        for name,target in binding.BINDINGS:
            assert sys.modules[name] is import_module(target)

@pytest.mark.parametrize('replacement',[False,True])
def test_dotted_children_rollback_owned_only(tmp_path,replacement):
    with references(tmp_path/'rollback'):
        binding=import_module('python.substrate.llm.runtime_bindings')
        for name,_ in binding.BINDINGS:sys.modules.pop(name,None)
        for name in ('minilich','minilich.ml_data','minilich.ml_project_index'):sys.modules.pop(name,None)
        foreign=ModuleType('replacement-child');real=binding.import_module
        class Interrupted(BaseException):pass
        def interrupted(target):
            if target=='python.substrate.context.librarian':
                assert 'minilich.ml_data' in sys.modules and 'minilich.ml_project_index' in sys.modules
                if replacement:sys.modules['minilich.ml_project_index']=foreign
                raise Interrupted()
            return real(target)
        with patch.object(binding,'import_module',side_effect=interrupted),pytest.raises(Interrupted):binding.register()
        assert 'minilich' not in sys.modules and 'minilich.ml_data' not in sys.modules
        if replacement:assert sys.modules['minilich.ml_project_index'] is foreign
        else:assert 'minilich.ml_project_index' not in sys.modules

@pytest.mark.parametrize('child',['minilich.ml_data','minilich.ml_project_index'])
def test_foreign_child_refused_without_overwrite(tmp_path,child):
    with references(tmp_path/'foreign'):
        binding=import_module('python.substrate.llm.runtime_bindings');foreign=ModuleType('foreign-child')
        sys.modules[child]=foreign
        with pytest.raises(RuntimeError,match='legacy child already bound'):binding.register()
        assert sys.modules[child] is foreign
