"""D46 ownership, closure and unchanged legacy registration behavior."""
from importlib import import_module
import sys
from types import ModuleType
from unittest.mock import patch
import pytest
from tests.py.context.observations import ROOT,TARGETS,references

def test_canonical_parent_identity_and_idempotence(tmp_path):
    with references(tmp_path/'binding') as subjects:
        binding=import_module('python.substrate.llm.runtime_bindings')
        assert len(binding.BINDINGS)==50
        assert [name for name,_ in binding.BINDINGS[29:35]]==[
            'history_manager','gd_api_cache','gd_api_check','gd_lint','gd_semantic_parser','librarian']
        parent=sys.modules['minilich']
        assert isinstance(parent,ModuleType) and not hasattr(parent,'__path__')
        assert parent.ml_data is import_module(TARGETS['ml_data'])
        assert parent.ml_project_index is import_module(TARGETS['ml_project_index'])
        assert subjects['lib'].ml_project_index is parent.ml_project_index
        assert subjects['index'].ml_data is parent.ml_data
        assert subjects['index'].gd_semantic_parser is subjects['parser']
        before=(dict(sys.modules),tuple(sys.path),tuple(sys.meta_path),tuple(sys.path_hooks))
        binding.register()
        binding.register()
        assert before==(dict(sys.modules),tuple(sys.path),tuple(sys.meta_path),tuple(sys.path_hooks))
        assert sys.modules['minilich.ml_data'] is parent.ml_data
        assert sys.modules['minilich.ml_project_index'] is parent.ml_project_index
        assert not any(name in sys.modules for name in ('ml_data','ml_project_index',
            'function_card','gd_functions','minilich.ml_train','minilich.ml_nn','torch'))

def test_foreign_parent_refusal_never_mutates_foreign(tmp_path):
    with references(tmp_path/'foreign'):
        binding=import_module('python.substrate.llm.runtime_bindings')
        foreign=ModuleType('minilich')
        foreign.owned_by_test=object()
        sys.modules['minilich']=foreign
        before=dict(vars(foreign))
        with pytest.raises(RuntimeError,match='minilich'):
            binding.register()
        assert sys.modules['minilich'] is foreign and vars(foreign)==before

@pytest.mark.parametrize('replace_parent',[False,True])
def test_baseexception_parent_rollback_owned_only(tmp_path,replace_parent):
    with references(tmp_path/'rollback'):
        binding=import_module('python.substrate.llm.runtime_bindings')
        for name,_ in binding.BINDINGS:
            del sys.modules[name]
        del sys.modules['minilich']
        del sys.modules['minilich.ml_data']
        del sys.modules['minilich.ml_project_index']
        foreign=ModuleType('foreign-minilich')
        real=binding.import_module
        class Interrupted(BaseException):
            pass
        def stopped(target):
            if target==TARGETS['librarian']:
                if replace_parent:
                    sys.modules['minilich']=foreign
                raise Interrupted()
            return real(target)
        with patch.object(binding,'import_module',side_effect=stopped),pytest.raises(Interrupted):
            binding.register()
        assert all(name not in sys.modules for name,_ in binding.BINDINGS)
        assert 'minilich.ml_data' not in sys.modules and 'minilich.ml_project_index' not in sys.modules
        if replace_parent:
            assert sys.modules['minilich'] is foreign
        else:
            assert 'minilich' not in sys.modules
