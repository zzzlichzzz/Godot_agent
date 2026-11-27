import importlib
import sys
from types import ModuleType
from unittest.mock import patch
import pytest
from tests.py.engine_cache.observations import ROOT,TARGETS,references

NAMES=tuple(TARGETS)
def test_identity_idempotence_and_old29_order(tmp_path):
    with references(tmp_path/'binding') as (subjects,_):
        binding=importlib.import_module('python.substrate.llm.runtime_bindings')
        assert len(binding.BINDINGS)==50 and binding.BINDINGS[29:33]==tuple(TARGETS.items())
        assert tuple(name for name,_ in binding.BINDINGS[:29])==('cdp_ws','net_monitor','sites','browser_manager','ai_studio_net','qwen_net','text_sanitize','parser_base','kimi_parser','ai_parser','qwen_parser','deepseek_parser','project_tools','project_settings_actions','server_state','api_keys','openai_compat','providers','model_cache','catalog','anthropic_compat','agent_prompts','rate_limit','md_to_bbcode','chat_store','api_history','runtime_debug','editor_context','api_backend')
        modules,paths,hooks=(dict(sys.modules),list(sys.path),(list(sys.meta_path),list(sys.path_hooks)))
        binding.register();binding.register()
        assert sys.modules==modules and sys.path==paths and (sys.meta_path,sys.path_hooks)==hooks
        for name,target in TARGETS.items():
            assert sys.modules[name] is subjects[name] is importlib.import_module(target)
        assert subjects['history_manager']._resolve_safe_path is sys.modules['project_tools']._resolve_safe_path
        assert subjects['gd_api_cache'].history is subjects['history_manager']
        assert subjects['gd_api_check'].gd_api_cache is subjects['gd_api_cache']

@pytest.mark.parametrize('name',NAMES)
def test_foreign_alias_refused_and_retained(name,tmp_path):
    with references(tmp_path/'foreign'):
        binding=importlib.import_module('python.substrate.llm.runtime_bindings')
        foreign=ModuleType('foreign_'+name)
        with patch.dict(sys.modules,{name:foreign}):
            with pytest.raises(RuntimeError,match='legacy alias already bound: '+name):
                binding.register()
            assert sys.modules[name] is foreign

@pytest.mark.parametrize('error',[ImportError,KeyboardInterrupt])
def test_late_failure_rolls_back_only_new_aliases(error,tmp_path):
    with references(tmp_path/'late'):
        binding=importlib.import_module('python.substrate.llm.runtime_bindings')
        originals={name:sys.modules[name] for name,_ in binding.BINDINGS[:29]}
        for name in NAMES:
            sys.modules.pop(name)
        original=binding.import_module
        def failing(target):
            if target==TARGETS['gd_lint']:
                raise error('synthetic last import failure')
            return original(target)
        with patch.object(binding,'import_module',failing),pytest.raises(error):
            binding.register()
        assert all(name not in sys.modules for name in NAMES)
        assert all(sys.modules[name] is module for name,module in originals.items())

def test_replaced_new_alias_is_not_deleted(tmp_path):
    with references(tmp_path/'replacement'):
        binding=importlib.import_module('python.substrate.llm.runtime_bindings')
        for name in NAMES:
            sys.modules.pop(name)
        replacement=ModuleType('replacement')
        original=binding.import_module
        def failing(target):
            if target==TARGETS['gd_api_check']:
                sys.modules['history_manager']=replacement
                raise ImportError('synthetic replacement before failure')
            return original(target)
        with patch.object(binding,'import_module',failing),pytest.raises(ImportError):
            binding.register()
        assert sys.modules['history_manager'] is replacement
        assert 'gd_api_cache' not in sys.modules

def test_no_production_bootstrap_wiring():
    for folder in (ROOT/'python/runtime',):
        for path in folder.rglob('*.py'):
            assert 'runtime_bindings' not in path.read_text(encoding='utf-8')
