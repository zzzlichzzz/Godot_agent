"""D33 exact identities, import-time sanitizer, conflict refusal and owned rollback."""
import builtins
from importlib import import_module
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.py.project.observations import ROOT, TARGETS, references


def test_project_alias_identity_idempotence_and_order(tmp_path):
    with references(tmp_path) as modules:
        binding = import_module('python.substrate.llm.runtime_bindings')
        assert len(binding.BINDINGS) == 50
        parser_end = next(index for index, pair in enumerate(binding.BINDINGS) if pair[0] == 'deepseek_parser')
        assert binding.BINDINGS[parser_end + 1:parser_end + 3] == tuple(TARGETS.items())
        before = dict(sys.modules)
        paths = (list(sys.path), list(sys.meta_path), list(sys.path_hooks))
        binding.register()
        binding.register()
        assert dict(sys.modules) == before
        assert (sys.path, sys.meta_path, sys.path_hooks) == paths
        for alias, target in TARGETS.items():
            assert modules[alias] is sys.modules[alias] is import_module(target)


def test_sanitizer_identity_at_real_project_tools_import(tmp_path):
    sanitizer = import_module('python.substrate.llm.parsers.text_sanitize')
    real_import, seen = builtins.__import__, []
    def traced(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'text_sanitize' and globals and globals.get('__name__') == TARGETS['project_tools']:
            assert sys.modules['text_sanitize'] is sanitizer
            seen.append(sys.modules['text_sanitize'])
        return real_import(name, globals, locals, fromlist, level)
    with patch.object(builtins, '__import__', traced), references(tmp_path) as modules:
        assert modules['project_tools'].sanitize_llm_text is sanitizer.sanitize_llm_text
    assert seen == [sanitizer], 'must observe the actual fresh source import once'


@pytest.mark.parametrize('alias', tuple(TARGETS))
def test_project_foreign_alias_refused_and_retained(alias, tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        foreign = SimpleNamespace(marker='foreign')
        with patch.dict(sys.modules, {alias: foreign}):
            before = {name: sys.modules[name] for name, _ in binding.BINDINGS}
            with pytest.raises(RuntimeError, match='legacy alias already bound: ' + alias):
                binding.register()
            assert {name: sys.modules[name] for name, _ in binding.BINDINGS} == before


@pytest.mark.parametrize('exception', (ImportError, KeyboardInterrupt))
def test_project_late_failure_rolls_back_only_new_aliases(exception, tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        real_import = binding.import_module
        for alias in TARGETS:
            sys.modules.pop(alias)
        before = {name: sys.modules[name] for name, _ in binding.BINDINGS if name not in TARGETS}
        def failed(target):
            if target == TARGETS['project_settings_actions']:
                raise exception('synthetic late project import failure')
            return real_import(target)
        with patch.object(binding, 'import_module', failed), pytest.raises(exception):
            binding.register()
        assert not any(alias in sys.modules for alias in TARGETS)
        assert {name: sys.modules[name] for name in before} == before


def test_project_rollback_preserves_replaced_new_alias(tmp_path):
    with references(tmp_path):
        binding = import_module('python.substrate.llm.runtime_bindings')
        real_import = binding.import_module
        for alias in TARGETS:
            sys.modules.pop(alias)
        foreign = SimpleNamespace(marker='replacement')
        def failed(target):
            if target == TARGETS['project_settings_actions']:
                sys.modules['project_tools'] = foreign
                raise ImportError('synthetic replacement before failure')
            return real_import(target)
        with patch.object(binding, 'import_module', failed), pytest.raises(ImportError):
            binding.register()
        assert sys.modules['project_tools'] is foreign
        assert 'project_settings_actions' not in sys.modules


def test_project_binding_not_wired_to_production_bootstrap():
    for base in (ROOT / 'python/runtime', ROOT / 'runtime'):
        for path in base.rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.gd'):
                assert 'runtime_bindings' not in path.read_text(encoding='utf-8'), path
