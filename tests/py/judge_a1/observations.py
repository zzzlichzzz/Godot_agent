"""A1 native/canonical function replay; no old bootstrap or copied old tests."""
import ast
import base64
from contextlib import contextmanager
from importlib import import_module, util
import inspect
import json
import os
from pathlib import Path
import shutil
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/assistant/judge/reference/A1'
TARGETS = {name: 'python.substrate.verification.' + name for name in
           ('tscn_lint', 'runtime_checks', 'godot_headless_validation')}


class HarnessInvocationError(BaseException):
    """A bad capture invocation must not turn into an oracle error."""


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


def normalize(value, sandbox):
    if isinstance(value, BaseException):
        return {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
    if isinstance(value, str):
        return value.replace(str(sandbox).replace('\\', '\\\\'), '<sandbox>').replace(
            str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>')
    if isinstance(value, bytes):
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ('device', 'inode') and item is not None:
                assert isinstance(item, int)
                result[key] = '<' + key + '>'
            elif key == 'duration_ms' and 'baseline_status' in value:
                assert isinstance(item, int) and item >= 0
                result[key] = '<elapsed_ms>'
            else:
                result[key] = normalize(item, sandbox)
        return result
    if isinstance(value, (list, tuple)):
        return [normalize(item, sandbox) for item in value]
    return value


def snapshot(folder):
    result = {'files': {}, 'dirs': []}
    for base, dirs, names in os.walk(folder, followlinks=False):
        for name in dirs:
            path = Path(base) / name
            assert not path.is_symlink() and not path.is_junction()
            result['dirs'].append(path.relative_to(folder).as_posix())
        for name in sorted(names):
            path = Path(base) / name
            assert not path.is_symlink()
            result['files'][path.relative_to(folder).as_posix()] = path.read_bytes()
    result['dirs'].sort()
    return result


@contextmanager
def subjects(sandbox, native=None):
    """Use real native dependencies, or the real accepted legacy registration."""
    saved = dict(sys.modules)
    aliases = {'text_sanitize', 'project_tools', 'history_manager', 'gd_api_cache',
               *TARGETS, 'minilich', 'minilich.ml_data', 'minilich.ml_project_index'}
    tree = ast.parse((ROOT/'python/substrate/llm/runtime_bindings.py').read_text('utf-8'))
    bindings = ast.literal_eval(next(node.value for node in tree.body if
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
        t.id == 'BINDINGS' for t in node.targets)))
    aliases.update(name for name, _ in bindings)
    canonical = {target for _, target in bindings} | set(TARGETS.values()) | {
        'python.substrate.context.runtime_parent', 'python.substrate.context.ml_data',
        'python.substrate.context.ml_project_index'}
    for name in list(sys.modules):
        if name in aliases or name in canonical or name == 'python.substrate.llm.runtime_bindings':
            sys.modules.pop(name, None)

    def offline(*args, **kwargs):
        raise AssertionError('A1 replay forbids network')

    def load(name, source):
        spec = util.spec_from_file_location('a1_native_' + name, source)
        module = util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        assert Path(module.__file__).resolve() == source.resolve()
        return module

    try:
        with patch.dict(os.environ, {'GODOT_AGENT_CONFIG_DIR': str(sandbox/'config')}, clear=True), \
             patch.object(socket, 'getaddrinfo', offline), \
             patch.object(socket.socket, 'connect', offline), \
             patch.object(socket.socket, 'connect_ex', offline):
            if native is not None:
                load('text_sanitize', native/'parsers/text_sanitize.py')
                for name in ('project_tools', 'history_manager', 'gd_api_cache'):
                    load(name, native/'godot_tools'/(name+'.py'))
                modules = {name: load(name, native/'godot_tools'/(name+'.py')) for name in TARGETS}
                api_source = native.parent/'agent_api_cache/default_api_cache.json'
            else:
                import_module('python.substrate.llm.runtime_bindings').register()
                modules = {name: import_module(target) for name, target in TARGETS.items()}
                api_source = ROOT/'agent_api_cache/default_api_cache.json'
            addon = sandbox/'addon'
            (addon/'agent_api_cache').mkdir(parents=True)
            shutil.copyfile(api_source, addon/'agent_api_cache/default_api_cache.json')
            sys.modules['history_manager'].set_storage_dir(str(sandbox/'history'))
            guard = sys.modules['project_tools']
            assert modules['runtime_checks']._resolve_safe_path is guard._resolve_safe_path
            assert modules['godot_headless_validation']._resolve_safe_path is guard._resolve_safe_path
            assert modules['tscn_lint'].gd_api_cache is sys.modules['gd_api_cache']
            # Non-secret deterministic fixtures. Never call the real entropy source.
            ids = iter(('a'*32, 'b'*48))
            runtime = modules['runtime_checks']
            with patch.object(runtime, 'secrets', SimpleNamespace(token_hex=lambda n: next(ids))), \
                 patch.object(runtime, 'time', SimpleNamespace(time=lambda: 1000.0)):
                yield modules, addon
    finally:
        sys.modules.clear()
        sys.modules.update(saved)


def cases(group=None):
    rows = json.loads((CORPUS/'catalog.json').read_text('utf-8'))['cases']
    return [row for row in rows if group is None or row['group'] == group]


def observe(case, sandbox, native=None):
    from tests.py.judge_a1.runtime_operations import run as run_runtime
    from tests.py.judge_a1.headless_operations import run as run_headless
    sandbox = sandbox.resolve()
    assert sandbox != ROOT and ROOT not in sandbox.parents
    sandbox.mkdir(parents=True, exist_ok=True)
    project = sandbox/'project'
    shutil.copytree(CORPUS/'fixtures/basic', project)
    for relative, content in case.get('files', {}).items():
        path = project/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode('utf-8'))
    if 'malformed' in case:
        (project/'.a1-protocol.json').write_text(json.dumps(case['malformed']), encoding='utf-8')
    before = snapshot(project)
    with subjects(sandbox, native) as (modules, addon):
        if case['group'] == 'scene':
            module = modules['tscn_lint']
            result = call(module.lint_and_fix_tscn, case['text'], str(project),
                          str(addon), case.get('planned_paths'))
            if not isinstance(result, BaseException):
                fixed, problems = result
                again = call(module.lint_and_fix_tscn, fixed, str(project),
                             str(addon), case.get('planned_paths'))
                result = {'lint': result, 'again': again,
                          'scene_path': module.is_scene_path(case.get('path', 'res://candidate.tscn'))}
        elif case['group'] == 'runtime':
            result = call(run_runtime, modules['runtime_checks'], project, sandbox, case)
        elif case['group'] == 'headless':
            result = call(run_headless, modules['godot_headless_validation'], project, sandbox, case)
        else:
            raise HarnessInvocationError('unknown case group')
    after = snapshot(project)
    assert before == after or case.get('mutate_after') in ('player', 'referencer') or case.get('stale_before'), 'unexpected project write'
    return normalize({'before': before, 'result': result, 'after': after}, sandbox)
