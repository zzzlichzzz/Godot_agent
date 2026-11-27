"""Remember the editor used by this deployment for subsequent standalone EXE launches."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

ENGINE_ENV = 'GODOT_AGENT_GODOT_BIN'


def ordinary(path):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Deployment and userdata must not traverse links')


def _external(path, project):
    if not path.is_absolute() or '..' in path.parts or path.drive.startswith('\\\\'):
        raise ValueError('Expected an absolute local path')
    ordinary(path)
    if path.resolve().is_relative_to(project.resolve()):
        raise ValueError('Launcher settings and editor must be outside the project')
    return path


def _record(project, env):
    key = hashlib.sha256(os.fsencode(os.path.normcase(project.resolve()))).hexdigest()
    return _external(Path(env.get('LOCALAPPDATA', '')) / 'GodotAgent/launchers' / (key + '.json'), project)


def editor_identity(raw, project):
    path = _external(Path(raw), project)
    info = path.stat()
    if path.suffix.lower() != '.exe' or not stat.S_ISREG(info.st_mode):
        raise ValueError('Expected an editor executable')
    return {'path': str(path), 'identity': [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]}


def restore(project, env):
    if env.get(ENGINE_ENV):
        return
    try:
        record = _record(project, env)
        info = record.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16384:
            return
        saved = json.loads(record.read_text('utf-8'))
        if saved == editor_identity(saved['path'], project):
            env[ENGINE_ENV] = saved['path']
            return True
    except (OSError, ValueError, KeyError, TypeError):
        pass  # First use, unavailable profile or stale binding: normal engine discovery applies.


def remember(project, env):
    """Only called after FileAccess successfully read the bound project configuration."""
    if not env.get(ENGINE_ENV):
        return
    try:
        value = editor_identity(env[ENGINE_ENV], project)
        record = _record(project, env)
        record.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=record.parent, delete=False, mode='w', encoding='utf-8') as output:
                tmp = Path(output.name)
                json.dump(value, output, ensure_ascii=True)
            os.replace(tmp, record)
        finally:
            if tmp is not None: tmp.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        pass  # An optional convenience; never prevent a launch with a working editor.
