"""New explicit aliases preserve the sealed D33 registration invariants."""
from importlib import import_module
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from tests.py.llm.api_cases import references
from tests.py.llm.routing_context_cases import CONTEXT_SOURCES, ROOT


def test_context_alias_identity_idempotent_and_no_path_hooks(tmp_path):
    paths = list(sys.path), list(sys.meta_path), list(sys.path_hooks)
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        for _ in range(2):
            binding.register()
            for name, (_, target) in CONTEXT_SOURCES.items():
                assert sys.modules[name] is import_module(target)
        assert (sys.path, sys.meta_path, sys.path_hooks) == paths


@pytest.mark.parametrize('name', CONTEXT_SOURCES)
def test_new_foreign_alias_refused_without_replacement(tmp_path, name):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        foreign = ModuleType(name)
        with patch.dict(sys.modules, {name: foreign}):
            with pytest.raises(RuntimeError, match='legacy alias already bound: ' + name):
                binding.register()
            assert sys.modules[name] is foreign


def test_new_alias_rollback_keeps_preexisting_modules(tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        previous = sys.modules['api_keys']
        for name in CONTEXT_SOURCES:
            sys.modules.pop(name, None)
        original = binding.import_module

        def importing(name):
            if name == CONTEXT_SOURCES['editor_context'][1]:
                raise ModuleNotFoundError('synthetic late failure')
            return original(name)

        with patch.object(binding, 'import_module', importing):
            with pytest.raises(ModuleNotFoundError, match='synthetic late failure'):
                binding.register()
        assert sys.modules['api_keys'] is previous
        assert not set(CONTEXT_SOURCES) & set(sys.modules)


def test_production_bootstrap_still_does_not_bind_legacy_references():
    for path in (ROOT / 'python/runtime').rglob('*.py'):
        assert 'runtime_bindings' not in path.read_text(encoding='utf-8')


def test_backend_alias_identity_and_idempotence(tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        binding.register()
        assert sys.modules['api_backend'] is import_module('python.substrate.llm.backends.api_backend')


def test_backend_foreign_alias_refused(tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        foreign = ModuleType('api_backend')
        with patch.dict(sys.modules, {'api_backend': foreign}):
            with pytest.raises(RuntimeError, match='legacy alias already bound: api_backend'):
                binding.register()
            assert sys.modules['api_backend'] is foreign


def test_backend_late_failure_rolls_back_only_new_aliases(tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        existing = {name: sys.modules[name] for name in ('api_keys', 'runtime_debug', 'editor_context')}
        for name in ('api_backend', 'api_history'):
            sys.modules.pop(name, None)
        original = binding.import_module

        def importing(name):
            if name == 'python.substrate.llm.backends.api_backend':
                raise ModuleNotFoundError('synthetic backend closure failure')
            return original(name)

        with patch.object(binding, 'import_module', importing):
            with pytest.raises(ModuleNotFoundError, match='synthetic backend closure failure'):
                binding.register()
        assert 'api_history' not in sys.modules and 'api_backend' not in sys.modules
        assert all(sys.modules[name] is module for name, module in existing.items())
