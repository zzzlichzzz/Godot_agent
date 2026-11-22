"""API extension retains D33 identity, conflicts, rollback and explicit loading."""
from importlib import import_module
import sys
from unittest.mock import patch
import pytest
from tests.py.llm.api_cases import ROOT, SOURCES, references


def test_api_alias_identity_and_idempotence(tmp_path):
    before = (list(sys.path), list(sys.meta_path), list(sys.path_hooks))
    with references(tmp_path) as modules:
        binding = import_module('python.substrate.llm.runtime_bindings')
        binding.register()
        for name, _, target in SOURCES:
            assert sys.modules[name] is modules[name]
            assert modules[name] is import_module('python.substrate.llm.api.' + target)
    assert (sys.path, sys.meta_path, sys.path_hooks) == before


@pytest.mark.parametrize('name', ['api_keys', 'openai_compat', 'api_history'])
def test_api_foreign_alias_rejected(tmp_path, name):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        foreign = object()
        with patch.dict(sys.modules, {name: foreign}):
            with pytest.raises(RuntimeError, match='legacy alias already bound: ' + name):
                binding.register()
            assert sys.modules[name] is foreign


def test_api_late_failure_rolls_back_only_new_aliases(tmp_path):
    with references(tmp_path) as modules:
        binding = import_module('python.substrate.llm.runtime_bindings')
        original = binding.import_module
        keep = modules['api_keys']
        with patch.dict(sys.modules):
            for name, _, _ in SOURCES:
                if name != 'api_keys':
                    sys.modules.pop(name)

            def fail_last(target):
                if target.endswith('.api_history'):
                    raise ModuleNotFoundError('injected missing approved reference')
                return original(target)

            with patch.object(binding, 'import_module', fail_last):
                with pytest.raises(ModuleNotFoundError):
                    binding.register()
            assert sys.modules['api_keys'] is keep
            assert all(name not in sys.modules for name, _, _ in SOURCES if name != 'api_keys')


def test_api_dns_is_honestly_deferred(tmp_path):
    with references(tmp_path) as modules:
        assert 'doh' not in sys.modules
        for function in (modules['api_keys'].set_dns, modules['api_keys'].apply_dns_settings):
            with pytest.raises(ModuleNotFoundError) as error:
                function()
            assert error.value.name == 'doh'
        assert not (tmp_path / 'config').exists()


def test_production_profiles_still_do_not_load_binding():
    for path in (ROOT / 'python/runtime').rglob('*.py'):
        assert 'runtime_bindings' not in path.read_text(encoding='utf-8')
