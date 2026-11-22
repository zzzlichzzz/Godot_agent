"""Offline native/new observations on copies of synthetic fixture projects."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
from importlib import import_module, util
import json
import os
from pathlib import Path
import shutil
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/project'
FIXTURES = CORPUS / 'fixtures'
TARGETS = {
    'project_tools': 'python.substrate.project.project_tools',
    'project_settings_actions': 'python.substrate.project.project_settings_actions',
}


def normalize(value, sandbox):
    if isinstance(value, BaseException):
        result = {'error': type(value).__name__, 'message': normalize(str(value), sandbox)}
        for key in ('errno', 'winerror'):
            if getattr(value, key, None) is not None:
                result[key] = getattr(value, key)
        return result
    if isinstance(value, str):
        return (value.replace(str(sandbox).replace('\\', '\\\\'), '<sandbox>')
                .replace(str(sandbox), '<sandbox>').replace(sandbox.as_posix(), '<sandbox>'))
    if isinstance(value, dict):
        return {str(key): normalize(item, sandbox) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item, sandbox) for item in value]
    return value


def snapshot(folder):
    """No timestamps or traversal through reparse points; exact contents/casing."""
    files, dirs, links = {}, [], []
    for current, children, names in os.walk(folder, followlinks=False):
        current = Path(current)
        for name in list(children):
            path = current / name
            relative = path.relative_to(folder).as_posix()
            if path.is_symlink() or path.is_junction():
                links.append(relative)
                children.remove(name)
            else:
                dirs.append(relative)
        for name in names:
            path = current / name
            relative = path.relative_to(folder).as_posix()
            if path.is_symlink():
                links.append(relative)
            else:
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'files': dict(sorted(files.items())), 'dirs': sorted(dirs), 'links': sorted(links)}


@contextmanager
def references(sandbox, native=None):
    sandbox = Path(sandbox).resolve()
    assert ROOT != sandbox and ROOT not in sandbox.parents
    sandbox.mkdir(parents=True, exist_ok=True)

    def denied(*args, **kwargs):
        raise PermissionError('project reference network denied')

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {'GODOT_AGENT_CONFIG_DIR': str(sandbox / 'config')}, clear=True))
        stack.enter_context(patch.dict(sys.modules))
        for owner, attribute in ((socket, 'getaddrinfo'), (socket.socket, 'connect'),
                                 (socket.socket, 'connect_ex')):
            stack.enter_context(patch.object(owner, attribute, denied))
        for name, target in TARGETS.items():
            sys.modules.pop(name, None)
            sys.modules.pop(target, None)
        if native is None:
            sys.modules.pop('python.substrate.llm.runtime_bindings', None)
            import_module('python.substrate.llm.runtime_bindings').register()
            modules = {name: sys.modules[name] for name in TARGETS}
        else:
            sanitizer = import_module('python.substrate.llm.parsers.text_sanitize')
            sys.modules['text_sanitize'] = sanitizer
            modules = {}
            for name in TARGETS:
                spec = util.spec_from_file_location('capture_' + name,
                                                   Path(native) / 'godot_tools' / (name + '.py'))
                module = util.module_from_spec(spec)
                spec.loader.exec_module(module)
                modules[name] = sys.modules[name] = module
        assert modules['project_tools'].sanitize_llm_text is sys.modules['text_sanitize'].sanitize_llm_text
        assert modules['project_settings_actions']._resolve_safe_path is modules['project_tools']._resolve_safe_path
        stack.enter_context(patch.object(modules['project_settings_actions'], 'uuid',
                                        SimpleNamespace(uuid4=lambda: SimpleNamespace(hex='0123456789abcdef' * 2))))
        yield modules


def attempt(call):
    try:
        return call()
    except Exception as error:
        return error


def expand(value, sandbox, root):
    if isinstance(value, str):
        return value.replace('<root>', str(root)).replace('<sandbox>', str(sandbox))
    if isinstance(value, dict):
        if set(value) == {'$float'}:
            return {'nan': float('nan'), 'inf': float('inf'), '-inf': float('-inf')}[value['$float']]
        return {key: expand(item, sandbox, root) for key, item in value.items()}
    if isinstance(value, list):
        return [expand(item, sandbox, root) for item in value]
    return value


def observe(case, sandbox, native=None):
    from tests.py.project.operations import run_operation
    original = deepcopy(case)
    sandbox = Path(sandbox).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / 'config').mkdir()
    root = sandbox / 'project'
    shutil.copytree(FIXTURES / case.get('fixture', 'core'), root)
    outside = sandbox / 'outside'
    outside.mkdir()
    (outside / 'private.gd').write_text('OUTSIDE_MARKER\n', encoding='utf-8', newline='\n')
    extra = sandbox / 'project-extra'
    extra.mkdir()
    (extra / 'leak.gd').write_text('PREFIX_MARKER\n', encoding='utf-8', newline='\n')
    setup = case.get('setup', '')
    if setup == 'no_project_file':
        (root / 'project.godot').unlink()
    if setup in ('bom', 'invalid_utf8'):
        with (root / 'sample.txt').open('xb') as stream:
            stream.write(b'\xef\xbb\xbfhello\r\nworld\n' if setup == 'bom' else b'hello\xffworld\n')
    if setup == 'protected_metadata':
        (root / 'project.godot').write_text(
            '[application]\nrun/main_scene="res://Addons/RenamedWrapper/core/agent.tscn"\n'
            '[autoload]\nAgent="*res://Addons/RenamedWrapper/core/agent.gd"\n'
            'Game="*res://src/state.gd"\nOutside="*res://../outside/private.gd"\n',
            encoding='utf-8', newline='\n')
    if setup == 'long_line':
        (root / 'long.txt').write_text('PUBLIC_MARKER' * 100 + '\n', encoding='utf-8', newline='\n')
    if setup == 'junction':
        import _winapi
        _winapi.CreateJunction(str(outside), str(root / 'outside_link'))
        _winapi.CreateJunction(str(root / 'Addons'), str(root / 'addon_link'))
        _winapi.CreateJunction(str(root / 'Addons/RenamedWrapper/core'), str(root / 'agent_link'))
    if setup == 'casing':
        leaf = root / 'CaseDir/InnerDir/item.txt'
        leaf.parent.mkdir(parents=True)
        leaf.write_text('CASE_MARKER\n', encoding='utf-8', newline='\n')
    for folder, children, names in os.walk(root, followlinks=False):
        children[:] = [name for name in children if not (Path(folder) / name).is_junction()]
        for name in names:
            os.utime(Path(folder) / name, (1000, 1000))
    before = snapshot(sandbox)
    with references(sandbox, native) as modules, ExitStack() as stack:
        if case.get('unc_seam'):
            # Avoid Windows SMB/DNS at GetFinalPathNameByHandle, not a relaxed denial.
            realpath = os.path.realpath
            def local_only(path, *args, **kwargs):
                if str(path).startswith('\\\\fixture-host.invalid\\fixture-share'):
                    return str(path)
                return realpath(path, *args, **kwargs)
            stack.enter_context(patch.object(os.path, 'realpath', local_only))
        result = attempt(lambda: run_operation(modules, expand(case, sandbox, root), root, sandbox))
    after = snapshot(sandbox)
    assert case == original, 'observer changed input'
    return normalize({'result': result, 'before': before, 'after': after}, sandbox)


def cases(group):
    manifest = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
    return [row for row in manifest['cases'] if row['group'] == group]


def load(row):
    raw = (CORPUS / row['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    return json.loads(raw)
