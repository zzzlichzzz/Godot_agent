"""Actual six-source read/prepare replay; the public judge is still absent."""
import ast
import base64
from contextlib import contextmanager, ExitStack
from importlib import import_module, util
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT/'fixtures/corpus/assistant/judge/reference/A2'
TARGETS = {name: 'python.substrate.'+area+'.'+name for name, area in (
    ('scene_deps', 'scene'), ('scene_actions', 'editing'), ('file_refactor', 'editing'),
    ('resource_actions', 'editing'), ('transaction_actions', 'editing'),
    ('high_level_actions', 'assistant'))}


class HarnessInvocationError(BaseException):
    """A setup, identity or invocation defect is never an oracle result."""


def call(function, *args, **kwargs):
    try:
        inspect.signature(function).bind(*args, **kwargs)
    except TypeError as error:
        raise HarnessInvocationError(str(error)) from error
    try:
        return function(*args, **kwargs)
    except AssertionError as error:
        raise HarnessInvocationError(str(error)) from error
    except Exception as error:
        return error


def normalize(value, sandbox, key=None):
    if isinstance(value, BaseException):
        return {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
    if isinstance(value, str):
        if key in ('action_id', 'transaction_id'):
            assert re.fullmatch('[0-9a-f]{32}', value)
            return '<'+key+':uuid4hex>'
        return value.replace(str(sandbox).replace('\\', '\\\\'), '<sandbox>').replace(
            str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>')
    if isinstance(value, bytes):
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict):
        return {k: normalize(v, sandbox, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item, sandbox) for item in value]
    return value


def snapshot(folder):
    result = {'files': {}, 'dirs': []}
    for base, dirs, names in os.walk(folder, followlinks=False):
        for name in dirs:
            path = Path(base)/name
            assert not path.is_symlink() and not path.is_junction()
            result['dirs'].append(path.relative_to(folder).as_posix())
        for name in sorted(names):
            path = Path(base)/name
            assert not path.is_symlink()
            result['files'][path.relative_to(folder).as_posix()] = path.read_bytes()
    result['dirs'].sort()
    return result


@contextmanager
def subjects(sandbox, native=None):
    """Real registration plus scoped stage aliases; no production +15 aliases yet."""
    saved = dict(sys.modules)
    tree = ast.parse((ROOT/'python/substrate/llm/runtime_bindings.py').read_text('utf-8'))
    bindings = ast.literal_eval(next(node.value for node in tree.body if
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
        t.id == 'BINDINGS' for t in node.targets)))
    aliases = {name for name, _ in bindings} | set(TARGETS) | {'minilich',
        'minilich.ml_data', 'minilich.ml_project_index', 'godot_headless_validation'}
    canonical = {target for _, target in bindings} | set(TARGETS.values()) | {
        'python.substrate.context.runtime_parent', 'python.substrate.context.ml_data',
        'python.substrate.context.ml_project_index',
        'python.substrate.verification.godot_headless_validation'}
    for name in list(sys.modules):
        if name in aliases or name in canonical or name == 'python.substrate.llm.runtime_bindings':
            sys.modules.pop(name, None)

    def forbidden(*args, **kwargs):
        raise AssertionError('A2 read/prepare replay forbids network and process launch')

    def load(name, source):
        spec = util.spec_from_file_location('a2_native_'+name, source)
        module = util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        assert Path(module.__file__).resolve() == source.resolve()
        return module

    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                'GODOT_AGENT_CONFIG_DIR': str(sandbox/'config')}, clear=True))
            for owner, attr in ((socket, 'getaddrinfo'), (socket.socket, 'connect'),
                (socket.socket, 'connect_ex'), (subprocess, 'Popen'), (subprocess, 'run')):
                stack.enter_context(patch.object(owner, attr, forbidden))
            import_module('python.substrate.llm.runtime_bindings').register()
            canonical_history = sys.modules['history_manager']
            # The accepted corrected-native quartet is the common pinned dependency.
            data = import_module('python.substrate.context.ml_data')
            index = import_module('python.substrate.context.ml_project_index')
            assert sys.modules['minilich'].ml_data is data
            assert sys.modules['minilich'].ml_project_index is index
            if native is not None:
                load('text_sanitize', native/'parsers/text_sanitize.py')
                for name in ('project_tools', 'history_manager', 'gd_api_cache', 'gd_api_check',
                             'gd_lint', 'project_settings_actions', 'godot_headless_validation'):
                    load(name, native/'godot_tools'/(name+'.py'))
                modules = {name: load(name, native/'godot_tools'/(name+'.py')) for name in TARGETS}
                api_source = native.parent/'agent_api_cache/default_api_cache.json'
            else:
                sys.modules['godot_headless_validation'] = import_module(
                    'python.substrate.verification.godot_headless_validation')
                modules = {}
                for name, target in TARGETS.items():
                    module = import_module(target)
                    assert Path(module.__file__).resolve() == (ROOT/(target.replace('.', '/')+'.py')).resolve()
                    modules[name] = sys.modules[name] = module
                api_source = ROOT/'agent_api_cache/default_api_cache.json'
            addon = sandbox/'project/addons/godot_agent'
            guard = sys.modules['project_tools']
            assert modules['file_refactor']._resolve_safe_path is guard._resolve_safe_path
            assert modules['file_refactor'].librarian is sys.modules['librarian']
            assert modules['file_refactor'].ml_project_index is index
            assert modules['transaction_actions'].godot_headless_validation is sys.modules['godot_headless_validation']
            assert modules['resource_actions'].normalize_variant is modules['scene_actions'].normalize_variant
            assert modules['high_level_actions'].scene_actions is modules['scene_actions']
            assert modules['high_level_actions'].project_settings_actions is sys.modules['project_settings_actions']
            state = sandbox/'state'
            state.mkdir()
            shutil.copyfile(api_source, state/'godot_api_cache.json')
            for history in {canonical_history, sys.modules['history_manager']}:
                stack.enter_context(patch.object(history, '_STORAGE_OVERRIDE', str(state)))
            stack.enter_context(patch.object(sys.modules['gd_api_cache'], '_migrate_legacy_addon_cache', lambda _: None))
            stack.enter_context(patch.object(data, '_BASE_OVERRIDE', str(state/'minilich_brain')))
            yield modules, addon
    finally:
        sys.modules.clear()
        sys.modules.update(saved)


def cases():
    return json.loads((CORPUS/'catalog.json').read_text('utf-8'))['cases']


def observe(case, sandbox, native=None):
    from .action_operations import run as run_action
    from .read_operations import run as run_read
    sandbox = sandbox.resolve()
    assert sandbox != ROOT and ROOT not in sandbox.parents
    sandbox.mkdir(parents=True, exist_ok=True)
    project = sandbox/'project'
    shutil.copytree(CORPUS/'fixtures/basic', project)
    for relative, content in case.get('files', {}).items():
        path = project/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(content['base64']) if isinstance(content, dict)
                         else content.encode('utf-8'))
    before = snapshot(project)
    with subjects(sandbox, native) as (modules, addon):
        runner = run_read if case['group'] in ('scene_deps', 'file_refactor') else run_action
        result = runner(modules[case['group']], project, addon, case)
    after = snapshot(project)
    assert before == after, 'unexpected project write during A2 read/prepare'
    return normalize({'before': before, 'result': result, 'after': after}, sandbox)
