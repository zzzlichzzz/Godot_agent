"""Actual native/canonical facade calls with real A1/A2 dependencies."""
import base64
from contextlib import contextmanager
from importlib import import_module, util
import json
from pathlib import Path
import shutil
import sys

from tests.py.judge_a2.observations import call, subjects as previous_subjects, snapshot

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT/'fixtures/corpus/assistant/judge/reference/A3'
TARGETS = {name: 'python.substrate.code_intel.'+name for name in (
    'symbol_refactor_data', 'symbol_refactor_part1', 'symbol_refactor_part2',
    'symbol_refactor_part3', 'symbol_refactor')}


def normalize(value, sandbox):
    if isinstance(value, BaseException):
        result = {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
        if hasattr(value, 'code'):
            result['code'] = value.code
        return result
    if isinstance(value, str):
        return value.replace(str(sandbox).replace('\\', '\\\\'), '<sandbox>').replace(
            str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>')
    if isinstance(value, bytes):
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict):
        return {k: normalize(v, sandbox) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(v, sandbox) for v in value]
    return value


@contextmanager
def subjects(sandbox, native=None):
    with previous_subjects(sandbox, native) as (previous, addon):
        for name, target in TARGETS.items():
            sys.modules.pop(name, None)
            sys.modules.pop(target, None)
        modules = {}
        for name, target in TARGETS.items():
            if native is not None:
                source = native/'godot_tools'/(name+'.py')
                spec = util.spec_from_file_location('a3_native_'+name, source)
                module = util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
            else:
                source = ROOT/(target.replace('.', '/')+'.py')
                module = import_module(target)
                sys.modules[name] = module
            assert Path(module.__file__).resolve() == source.resolve()
            modules[name] = module
        facade = modules['symbol_refactor']
        assert facade.prepare_rename is modules['symbol_refactor_part3'].prepare_rename
        assert facade.find_references is modules['symbol_refactor_part2'].find_references
        assert facade.scene_deps is previous['scene_deps']
        assert facade.file_refactor is previous['file_refactor']
        assert facade.ml_project_index is sys.modules['minilich'].ml_project_index
        yield facade, addon


def cases():
    return json.loads((CORPUS/'catalog.json').read_text('utf-8'))['cases']


def observe(case, sandbox, native=None):
    sandbox = sandbox.resolve()
    assert ROOT not in sandbox.parents and sandbox != ROOT
    sandbox.mkdir(parents=True, exist_ok=False)
    project = sandbox/'project'
    shutil.copytree(CORPUS/'fixtures/basic', project)
    for relative, value in case.get('files', {}).items():
        path = project/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(value['base64']) if isinstance(value, dict)
                         else value.encode('utf-8'))
    before = snapshot(project)
    with subjects(sandbox, native) as (facade, addon):
        operation = case.get('operation', 'bundle')
        assert operation in ('bundle', 'find_references', 'analyze_rename',
                             'prepare_rename', 'exclude_place', '_validate_action', '_parse_locator')
        if operation in ('exclude_place', '_validate_action', '_parse_locator'):
            result = call(getattr(facade, operation), case['input'])
        else:
            functions = ('find_references', 'analyze_rename', 'prepare_rename') if operation == 'bundle' else (operation,)
            result = {}
            for name in functions:
                function = getattr(facade, name)
                value = call(function, str(project), case['input'],
                    addon_dir=str(addon), **case.get('kwargs', {}))
                result[name] = value
                result[name+'_again'] = call(function, str(project), case['input'],
                    addon_dir=str(addon), **case.get('kwargs', {}))
                if name == 'prepare_rename' and not isinstance(value, BaseException):
                    result['public'] = facade.public_prepared(value)
                    result['diffs'] = facade.prepared_diffs(value)
    after = snapshot(project)
    assert before == after, 'A3 reference unexpectedly wrote project files'
    return normalize({'before': before, 'result': result, 'after': after}, sandbox)
