"""Fixed native/new subjects, offline sandbox ownership and lossless observations."""
import ast
import base64
from contextlib import contextmanager
import copy
import hashlib
import functools
import inspect
from importlib import import_module, util
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/engine-cache'
OLD_API = ROOT / 'fixtures/corpus/verification/api_check'
TARGETS = {'history_manager':'python.substrate.store.history_manager',
           'gd_api_cache':'python.substrate.engine.gd_api_cache',
           'gd_api_check':'python.substrate.verification.gd_api_check',
           'gd_lint':'python.substrate.verification.gd_lint'}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def snapshot(root):
    files, dirs = {}, []
    for base, folders, names in os.walk(root, followlinks=False):
        for name in list(folders):
            path = Path(base)/name
            assert not path.is_symlink() and not path.is_junction()
            dirs.append(path.relative_to(root).as_posix())
        for name in sorted(names):
            path = Path(base)/name
            raw = path.read_bytes()
            relative=path.relative_to(root).as_posix()
            if re.fullmatch(r'\.agent_rollback_[A-Za-z0-9_-]+',name):
                relative=str(Path(relative).with_name('.agent_rollback_<owned>')).replace('\\','/')
            assert relative not in files,'owned tempfile normalization must not hide multiplicity'
            files[relative] = {'bytes':len(raw),'sha256':digest(raw)}
    return {'files':dict(sorted(files.items())),'dirs':sorted(dirs)}

def normalize(value, sandbox):
    if isinstance(value, BaseException):
        return {'error':type(value).__name__,'message':normalize(str(value),sandbox),
                'errno':getattr(value,'errno',None),'winerror':getattr(value,'winerror',None)}
    if isinstance(value,str):
        prefix = str(sandbox)
        value=value.replace(prefix.replace('\\','\\\\'),'<sandbox>').replace(prefix,'<sandbox>').replace(sandbox.as_posix(),'<sandbox>')
        return re.sub(r'\.journal-[A-Za-z0-9_-]+\.tmp','.journal-<owned>.tmp',value)
    if isinstance(value,bytes):
        return {'base64':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict):
        return {normalize(key,sandbox):normalize(item,sandbox) for key,item in value.items()}
    if isinstance(value,set):
        return sorted(normalize(item,sandbox) for item in value)
    if isinstance(value,(list,tuple)):
        return [normalize(item,sandbox) for item in value]
    return value

def attempt(function,*args,**kwargs):
    try:
        return function(*args,**kwargs)
    except Exception as error:
        return error

class CaptureInvocationError(BaseException):
    """A fixed harness call mismatch is not a native behavioral observation."""

def guarded(function):
    signature=inspect.signature(function)
    @functools.wraps(function)
    def call(*args,**kwargs):
        try:
            signature.bind(*args,**kwargs)
        except TypeError as error:
            raise CaptureInvocationError(str(error)) from error
        return function(*args,**kwargs)
    return call

@contextmanager
def references(sandbox,native=None):
    sandbox = sandbox.resolve()
    assert sandbox != ROOT and ROOT not in sandbox.parents
    saved = dict(sys.modules)
    tree = ast.parse((ROOT/'python/substrate/llm/runtime_bindings.py').read_text(encoding='utf-8'))
    bindings = ast.literal_eval(next(node.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='BINDINGS' for target in node.targets)))
    cleared = set(TARGETS.values()) | {'python.substrate.project.project_tools','python.substrate.project.project_settings_actions','python.substrate.llm.runtime_bindings'}
    for name in {*TARGETS, *(name for name,_ in bindings), *cleared}:
        sys.modules.pop(name,None)
    def denied(*args,**kwargs):
        raise AssertionError('engine-cache observation forbids all network')
    try:
        with patch.dict(os.environ,{'GODOT_AGENT_CONFIG_DIR':str(sandbox/'config')},clear=True), patch.object(socket,'getaddrinfo',denied), patch.object(socket.socket,'connect',denied), patch.object(socket.socket,'connect_ex',denied):
            if native is None:
                binding = import_module('python.substrate.llm.runtime_bindings')
                binding.register()
                modules = {name:import_module(target) for name,target in TARGETS.items()}
                data_source = ROOT/'agent_api_cache/default_api_cache.json'
            else:
                sanitizer = import_module('python.substrate.llm.parsers.text_sanitize')
                sys.modules['text_sanitize'] = sanitizer
                sys.modules['project_tools'] = import_module('python.substrate.project.project_tools')
                modules = {}
                for name in TARGETS:
                    spec = util.spec_from_file_location('engine_cache_native_'+name,native/'godot_tools'/(name+'.py'))
                    module = util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    sys.modules[name] = modules[name] = module
                data_source = native.parent/'agent_api_cache/default_api_cache.json'
            assert modules['history_manager']._resolve_safe_path is sys.modules['project_tools']._resolve_safe_path
            assert modules['gd_api_cache'].history is modules['history_manager']
            assert modules['gd_api_check'].gd_api_cache is modules['gd_api_cache']
            for module in modules.values():
                for name,function in list(vars(module).items()):
                    if inspect.isfunction(function) and function.__module__==module.__name__ and name not in ('_resolve_safe_path','begin_case_only_dir_casing'):
                        setattr(module,name,guarded(function))
            ids, ticks = itertools.count(1), itertools.count(1000)
            storage = modules['history_manager']
            with patch.object(storage,'uuid',SimpleNamespace(uuid4=lambda:SimpleNamespace(hex=f'{next(ids):012x}'+'0'*20))), patch.object(storage,'time',SimpleNamespace(time=lambda:next(ticks))):
                yield modules, data_source
    finally:
        sys.modules.clear()
        sys.modules.update(saved)

def observe(case,sandbox):
    from tests.py.engine_cache.history_operations import run_history
    from tests.py.engine_cache.cache_operations import run_cache
    sandbox = sandbox.resolve()
    sandbox.mkdir(parents=True,exist_ok=True)
    (sandbox/'config').mkdir()
    project = sandbox/'project'
    shutil.copytree(CORPUS/'fixtures/basic',project)
    original = copy.deepcopy(case)
    data = copy.deepcopy(case)
    if data['group']=='api' and 'old_case' in data:
        name = data['old_case']
        allowed = json.loads((OLD_API/'manifest.json').read_text(encoding='utf-8'))['cases']
        assert name in allowed
        old = json.loads((OLD_API/name).read_text(encoding='utf-8'))
        shutil.copytree(ROOT/'fixtures/projects'/old['fixture'],project,dirs_exist_ok=True)
        data['content'], data['path'] = old['args'].get('content'), old['args'].get('path','')
    if data.get('synthetic_fixture'):
        assert data['synthetic_fixture']=='corpus/verification/api_check/api'
        shutil.copytree(ROOT/'fixtures/projects'/data['synthetic_fixture'],project,dirs_exist_ok=True)
    before = snapshot(sandbox)
    with references(sandbox) as (modules,data_source):
        storage = modules['history_manager']
        if data.get('storage','project')=='user':
            storage.set_storage_dir(str(sandbox/'user'))
        if data['group']=='history':
            result = attempt(run_history,storage,project,data)
        elif data['group']=='cache':
            result = attempt(run_cache,modules['gd_api_cache'],storage,project,data,data_source,sandbox)
        elif data['group']=='api':
            result = attempt(modules['gd_api_check'].check_api_usage,str(project),data.get('content'),data.get('path',''))
        elif data['group']=='lint':
            result = attempt(modules['gd_lint'].lint_gdscript,data['content'])
        else:
            raise AssertionError('unlisted observation group')
    assert data['group']==case['group'] and case==original
    return normalize({'before':before,'result':result,'after':snapshot(sandbox)},sandbox)

def cases(group):
    manifest = json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    return [json.loads((CORPUS/row['file']).read_text(encoding='utf-8')) for row in manifest['cases'] if row['group']==group]
