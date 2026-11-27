"""Explicit alias identity/rollback; no global import-time runtime registration."""
import ast
import importlib
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from tests.py.browser import runtime_cases as runtime


def test_no_binding_import_means_no_aliases():
    names = (*runtime.NAMES, 'server_state', 'arena_parser', 'answer_judge')
    with patch.dict(sys.modules):
        for name in names:
            sys.modules.pop(name, None)
        importlib.import_module('python.substrate.llm.parsers')
        importlib.import_module('python.substrate.llm.browser')
        assert not any(name in sys.modules for name in names)


def test_binding_aliases_are_actual_modules_and_repeat_is_idempotent():
    with runtime.references() as modules:
        binding = importlib.import_module('python.substrate.llm.runtime_bindings')
        old_path, old_meta, old_hooks = list(sys.path), list(sys.meta_path), list(sys.path_hooks)
        before = {name: sys.modules[name] for name, _ in binding.BINDINGS}
        binding.register()
        for name, target in binding.BINDINGS:
            assert sys.modules[name] is importlib.import_module(target) is before[name]
        assert modules['parser_base'] is sys.modules['parser_base']
        assert sys.path == old_path and sys.meta_path == old_meta and sys.path_hooks == old_hooks
        assert len(Path(binding.__file__).read_text(encoding='utf-8').splitlines()) == 84


def test_conflicting_alias_is_not_overwritten_and_prior_additions_roll_back():
    with runtime.references():
        binding = importlib.import_module('python.substrate.llm.runtime_bindings')
        for name, _ in binding.BINDINGS:
            sys.modules.pop(name, None)
        foreign = ModuleType('foreign parser')
        sys.modules['parser_base'] = foreign
        with pytest.raises(RuntimeError, match='legacy alias already bound: parser_base'):
            binding.register()
        assert sys.modules['parser_base'] is foreign
        assert not any(name in sys.modules for name, _ in binding.BINDINGS if name != 'parser_base')


def test_missing_reference_is_explicit_and_new_aliases_roll_back(monkeypatch):
    with runtime.references():
        binding = importlib.import_module('python.substrate.llm.runtime_bindings')
        for name, _ in binding.BINDINGS:
            sys.modules.pop(name, None)
        real_import = binding.import_module
        def missing(name):
            if name == 'python.substrate.llm.parsers.parser_base':
                raise ModuleNotFoundError('missing pinned parser_base', name=name)
            return real_import(name)
        monkeypatch.setattr(binding, 'import_module', missing)
        with pytest.raises(ModuleNotFoundError, match='missing pinned parser_base'):
            binding.register()
        assert not any(name in sys.modules for name, _ in binding.BINDINGS)


def test_working_sites_resolve_real_parser_modules_not_stubs():
    with runtime.references() as modules:
        for site, name in [('aistudio', 'ai_parser'), ('qwen', 'qwen_parser'),
                           ('kimi', 'kimi_parser'), ('deepseek', 'deepseek_parser')]:
            assert modules['sites'].get_parser_module(site) is modules[name]


def test_arena_import_is_honestly_deferred_without_fake_judge():
    # Native line19 is unconditional: inert Arena import is NOT claimed complete.
    with runtime.references():
        sys.modules.pop('answer_judge', None)
        with pytest.raises(ModuleNotFoundError) as caught:
            importlib.import_module('python.substrate.llm.parsers.arena_parser')
        assert caught.value.name == 'answer_judge'
        assert 'answer_judge' not in sys.modules and 'arena_parser' not in sys.modules
        assert not hasattr(sys.modules['server_state'], 'STATE')


def test_production_bootstrap_and_profiles_do_not_import_binding(tmp_path):
    offenders = []
    for path in (runtime.ROOT / 'python').rglob('*.py'):
        if path.name == 'runtime_bindings.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        allowed = []
        scoped = {'python/substrate/context/librarian_read.py': ('LibrarianRead', 'answer'),
                  'python/substrate/assistant/judge_read.py': ('JudgeRead', 'judge'),
                  'python/substrate/assistant/chat_gateway.py': ('ChatGateway', 'send'),
                  'python/substrate/assistant/native_bindings.py': ('NativeBindings', 'register')}
        if path.relative_to(runtime.ROOT).as_posix() in scoped:
            class_name, method_name = scoped[path.relative_to(runtime.ROOT).as_posix()]
            owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
            answer = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == method_name)
            allowed = [node for node in ast.walk(answer) if isinstance(node, ast.ImportFrom)
                       and node.module == 'python.substrate.llm'
                       and [(item.name, item.asname) for item in node.names] == [('runtime_bindings', None)]]
            assert len(allowed) == 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or '', *[item.name for item in node.names]]
            else:
                continue
            if any(name.endswith('runtime_bindings') for name in imports):
                if node not in allowed:
                    offenders.append(str(path.relative_to(runtime.ROOT)))
    assert offenders == []
    names = ('python.substrate.llm.runtime_bindings', 'librarian', 'minilich')
    with patch.dict(sys.modules):
        for name in names:
            sys.modules.pop(name, None)
        bootstrap = importlib.import_module('python.runtime.bootstrap')
        ports = bootstrap.default_ports(tmp_path, 'headless', tmp_path / 'state')
        assert not any(name in sys.modules for name in names)
        agent = bootstrap.build_agent(tmp_path, profile='headless', state_dir=tmp_path / 'state', ports=ports)
        assert 'ask' in {tool['name'] for tool in agent.tools()}
        assert not any(name in sys.modules for name in names)
