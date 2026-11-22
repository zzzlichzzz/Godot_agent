"""Offline corrected-native/canonical replay; no native package initializer."""
import base64
from contextlib import contextmanager
from importlib import import_module, util
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/context/librarian'
TARGETS = {name: 'python.substrate.context.' + name for name in
           ('gd_semantic_parser', 'ml_data', 'ml_project_index', 'librarian')}

def normalize(value, sandbox):
    if isinstance(value, BaseException):
        return {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
    if isinstance(value, str):
        return value.replace(json.dumps(str(sandbox))[1:-1], '<sandbox>').replace(
            str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>')
    if isinstance(value, bytes):
        try:
            value = normalize(value.decode('utf-8'), sandbox).encode('utf-8')
        except UnicodeError:
            pass
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict):
        return {key: normalize(item, sandbox) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item, sandbox) for item in value]
    if isinstance(value, set):
        return sorted(normalize(item, sandbox) for item in value)
    return value

def state(folder, sandbox):
    files, dirs = {}, []
    for base, folders, names in os.walk(folder, followlinks=False):
        for name in folders[:]:
            path = Path(base) / name
            if path.is_junction() or path.is_symlink():
                folders.remove(name)
            else:
                dirs.append(path.relative_to(folder).as_posix())
        for name in sorted(names):
            path = Path(base) / name
            if not path.is_symlink():
                files[path.relative_to(folder).as_posix()] = normalize(path.read_bytes(), sandbox)
    return {'files': files, 'dirs': sorted(dirs)}

def attempt(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as error:
        return error

@contextmanager
def references(sandbox, native=None):
    sandbox = sandbox.resolve()
    assert ROOT != sandbox and ROOT not in sandbox.parents
    saved = dict(sys.modules)
    aliases = {'text_sanitize', 'project_tools', 'history_manager', 'gd_api_cache',
               'gd_api_check', 'gd_lint', 'gd_semantic_parser', 'librarian', 'minilich'}
    for name in list(sys.modules):
        if name in aliases or name.startswith(('minilich.', 'python.substrate.context.')) or name == 'python.substrate.llm.runtime_bindings':
            del sys.modules[name]
    def offline(*args, **kwargs):
        raise AssertionError('librarian replay forbids network')
    def native_module(name, relative):
        spec = util.spec_from_file_location(name, native / relative)
        module = util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    try:
        with patch.dict(os.environ, {'GODOT_AGENT_CONFIG_DIR': str(sandbox/'config')}, clear=True), \
             patch.object(socket, 'getaddrinfo', offline), patch.object(socket.socket, 'connect', offline), \
             patch.object(socket.socket, 'connect_ex', offline):
            if native is not None:
                native_module('text_sanitize', 'parsers/text_sanitize.py')
                guard = native_module('project_tools', 'godot_tools/project_tools.py')
                history = native_module('history_manager', 'godot_tools/history_manager.py')
                api = native_module('gd_api_cache', 'godot_tools/gd_api_cache.py')
                parser = native_module('gd_semantic_parser', 'godot_tools/gd_semantic_parser.py')
                mini = ModuleType('minilich')
                sys.modules['minilich'] = mini
                data = native_module('minilich.ml_data', 'minilich/ml_data.py')
                mini.ml_data = data
                index = native_module('minilich.ml_project_index', 'minilich/ml_project_index.py')
                mini.ml_project_index = index
                librarian = native_module('librarian', 'godot_tools/librarian.py')
                assert Path(guard.__file__).resolve() == (native/'godot_tools/project_tools.py').resolve()
            else:
                import_module('python.substrate.llm.runtime_bindings').register()
                guard, history, api = (sys.modules[name] for name in ('project_tools','history_manager','gd_api_cache'))
                parser, data, index, librarian = (import_module(TARGETS[name]) for name in TARGETS)
            history.set_storage_dir(str(sandbox/'history'))
            data.set_storage_base(str(sandbox/'addon'))
            assert librarian.can_read_project_path is index.can_read_project_path is guard.can_read_project_path
            assert not hasattr(sys.modules['minilich'], '__path__')
            assert sys.modules['minilich'].ml_data is data and sys.modules['minilich'].ml_project_index is index
            assert not any(name in sys.modules for name in ('function_card','ml_data','ml_project_index','ml_train','ml_model','ml_tokenizer','ml_github'))
            original_strftime = time.strftime
            with patch.object(time, 'time', lambda: 1000.0), \
                 patch.object(time, 'strftime', lambda fmt, when=None: original_strftime(fmt, time.gmtime(1000) if when is None else when)):
                yield {'guard':guard,'history':history,'api':api,'parser':parser,
                       'data':data,'index':index,'lib':librarian,'parent':sys.modules['minilich']}
    finally:
        sys.modules.clear()
        sys.modules.update(saved)

def setup(sandbox):
    sandbox = sandbox.resolve()
    assert ROOT != sandbox and ROOT not in sandbox.parents
    project = sandbox/'project'
    shutil.copytree(CORPUS/'fixtures/basic', project)
    for path in project.rglob('*'):
        if path.is_file():
            os.utime(path, (1000,1000))
    return project

def observe(case, sandbox, native=None):
    from tests.py.context.operations import run
    sandbox = sandbox.resolve()
    project = setup(sandbox)
    before = state(project, sandbox)
    with references(sandbox, native) as subjects:
        result = attempt(run, subjects, project, sandbox, case, native)
        storage = state(sandbox/'addon', sandbox)
        history = state(sandbox/'history', sandbox)
    after = state(project, sandbox)
    assert before == after or case['operation'] == 'invalidate', 'reference must not write project'
    return normalize({'before':before,'result':result,'project_after':after,
                      'addon_after':storage,'history_after':history}, sandbox)
