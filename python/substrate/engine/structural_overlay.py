"""Owned native editor preparation; only the B funnel writes the real project."""
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy, normalize_rel

SKIP = {'.godot', '.git', 'addons', '.agent_history', 'node_modules', '__pycache__', '_t1_overlay'}
CODES = ('.gd', '.gdc', '.cs', '.res', '.scn', '.gdextension', '.pck')
ASSETS = {'.godot', '.tscn', '.tres', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.wav', '.ogg', '.mp3', '.ttf', '.otf', '.gdshader'}
CODE = re.compile(rb'(?i)script|\\')
TIMEOUT = 120
MAX_BYTES = 32 * 1024 * 1024

def plain(path):
    for current in (path, *path.parents):
        if not current.exists() and not current.is_symlink(): continue
        value = current.lstat()
        if stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
            raise AppError('denied', 'linked overlay storage запрещён')

def contains(root, path):
    try: path.relative_to(root); return True
    except ValueError: return False

def walk_values(value):
    if isinstance(value, dict):
        for item in value.values(): yield from walk_values(item)
    elif isinstance(value, list):
        for item in value: yield from walk_values(item)
    else: yield value

class EngineOverlay:
    def __init__(self, project, state, addon, *, godot_bin=None, runner=None):
        self.project = Path(os.path.abspath(project)); self.state = Path(os.path.abspath(state))
        self.addon = Path(os.path.abspath(addon))
        self.godot_bin = godot_bin if godot_bin is not None else os.environ.get('GODOT_AGENT_GODOT_BIN', '')
        self.runner = runner or subprocess.run
        self.last_report = None

    def _target(self, action):
        kind = action.get('action'); key = 'resource' if kind == 'edit_resource' else 'scene'
        target = 'res://project.godot' if kind == 'edit_project_settings' else action.get(key)
        rel = target[6:] if isinstance(target, str) and target.startswith('res://') else ''
        if not rel or not PathPolicy(self.project).can_read(rel) or any(p in SKIP for p in Path(rel).parts) or ':' in rel or '\\' in rel:
            raise AppError('denied', 'structural target вне разрешённого проекта')
        if kind not in ('create_scene', 'edit_scene', 'edit_resource', 'edit_project_settings'):
            raise AppError('invalid_input', 'неизвестное structural действие')
        for value in walk_values(action):
            if isinstance(value, str) and value.lower().endswith(CODES):
                raise AppError('denied', 'executable/binary structural dependency не изолирована')
        return rel

    def _capture(self):
        captured = {}; total = 0; policy = PathPolicy(self.project); plain(self.project)
        for directory, dirs, files in os.walk(self.project, followlinks=False):
            parent = Path(directory); dirs[:] = sorted(name for name in dirs if name not in SKIP)
            for name in dirs: plain(parent / name)
            for name in sorted(files):
                path = parent / name; rel = path.relative_to(self.project).as_posix()
                if not policy.can_read(rel) or path.suffix.lower() not in ASSETS: continue
                plain(path)
                if not stat.S_ISREG(path.lstat().st_mode): raise AppError('denied', 'необычный structural asset')
                if path.stat().st_size > MAX_BYTES: raise AppError('invalid_input', 'structural asset превышает лимит')
                raw = path.read_bytes(); total += len(raw)
                if total > MAX_BYTES or len(captured) >= 4096: raise AppError('invalid_input', 'structural snapshot превышает лимит')
                if path.suffix.lower() in ('.tscn', '.tres') and CODE.search(raw):
                    raise AppError('denied', 'script-bearing structural asset не изолирован')
                if path.suffix.lower() in ('.tscn', '.tres', '.godot', '.gdshader'):
                    for token in re.findall(rb'"([^"\r\n]*)"', raw):
                        value = token.decode('utf-8', 'strict')
                        if path.suffix.lower() == '.gdshader':
                            if '\\' in value: raise AppError('denied', 'encoded shader reference запрещён')
                            if '://' not in value and not value.startswith('/') and not re.match(r'^[A-Za-z]:', value):
                                relative = normalize_rel((Path(rel).parent / value).as_posix())
                                if not relative: raise AppError('denied', 'traversal shader reference запрещён')
                                value = 'res://' + relative
                        if value.startswith('uid://') and path.suffix.lower() != '.gdshader': continue
                        relative_unsafe = value == '..' or value.startswith(('./', '../')) or '\\' in value or value.lower().endswith(('.cfg', *CODES))
                        if '://' in value or value.startswith('/') or re.match(r'^[A-Za-z]:[/\\]', value) or relative_unsafe:
                            relative = value[6:] if value.startswith('res://') else ''
                            if not relative or normalize_rel(relative) != relative or not policy.can_read(relative) or '\\' in relative or ':' in relative:
                                raise AppError('denied', 'external/encoded engine reference запрещён')
                            if relative.lower().endswith(CODES):
                                raise AppError('denied', 'executable engine reference запрещён')
                if rel == 'project.godot' and re.search(rb'(?im)^\s*\[autoload\]', raw):
                    raise AppError('denied', 'autoload structural проект не изолирован')
                captured[rel] = raw
        return captured

    def _run(self, argv, env):
        try:
            result = self.runner([str(self.godot_bin), *map(str, argv)], shell=False, timeout=TIMEOUT,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError('unavailable', 'Godot structural preparation недоступна') from None
        if result.returncode != 0: raise AppError('unavailable', 'Godot structural preparation не завершена')

    def prepare(self, action):
        rel = self._target(action); plain(self.state)
        if any(contains(root, other) or contains(other, root) for root, other in ((self.project, self.state), (self.addon, self.state))):
            raise AppError('denied', 'overlay state должен быть внешним')
        if not self.godot_bin or not Path(self.godot_bin).is_absolute():
            raise AppError('unavailable', 'задайте абсолютный GODOT_AGENT_GODOT_BIN')
        before = self._capture()
        if 'project.godot' not in before: raise AppError('invalid_input', 'project.godot отсутствует')
        if action['action'] != 'create_scene' and rel not in before: raise AppError('invalid_input', 'structural target отсутствует')
        target = self.project / rel; plain(target)
        if action['action'] == 'create_scene' and target.exists(): raise AppError('conflict', 'create_scene target уже существует')
        self.state.mkdir(parents=True, exist_ok=True); plain(self.state); self.last_report = None
        with tempfile.TemporaryDirectory(prefix='structural-', dir=self.state) as folder:
            scratch = Path(folder); project = scratch / 'project'; project.mkdir()
            for name, raw in before.items():
                copied = project / name; copied.parent.mkdir(parents=True, exist_ok=True); copied.write_bytes(raw)
            internal = project / '_t1_overlay'; internal.mkdir()
            for name in ('agent_scene_executor.gd', 'agent_resource_executor.gd', 'agent_project_settings_executor.gd'):
                (internal / name).write_bytes((self.addon / 'editor/native' / name).read_bytes())
            for name, destination in (('structural_overlay.gd', 'harness.gd'), ('resource_publication_observer.gd', 'resource_observer.gd')):
                (internal / destination).write_bytes((self.addon / 'editor/core' / name).read_bytes())
            request, response = scratch / 'action.json', scratch / 'response.json'; native = dict(action)
            if native['action'] == 'create_scene': native['_create_action_id'] = uuid.uuid4().hex
            request.write_text(json.dumps(native, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            env = dict(os.environ, GODOT_AGENT_OVERLAY_ROOT=str(project))
            self._run(['--headless', '--editor', '--import', '--path', project], env)
            self._run(['--headless', '--editor', '--path', project, '--script', 'res://_t1_overlay/harness.gd', '--', request, response], env)
            if self._capture() != before or (target.exists() and rel not in before):
                raise AppError('conflict', 'проект изменился во время structural prepare')
            if not response.is_file() or response.stat().st_size > MAX_BYTES: raise AppError('unavailable', 'нет ограниченного structural response')
            try: report = json.loads(response.read_bytes())
            except (ValueError, UnicodeError): raise AppError('unavailable', 'некорректный structural response') from None
            self.last_report = report
            if not isinstance(report, dict) or not isinstance(report.get('preview'), dict) or not isinstance(report.get('result'), dict):
                raise AppError('unavailable', 'некорректная structural envelope')
            preview, result = report['preview'], report['result']
            for name, raw in before.items():
                if name != rel and (not (project / name).is_file() or (project / name).read_bytes() != raw):
                    raise AppError('conflict', 'неожиданный structural asset effect')
            if preview.get('ok') is not True or result.get('ok') is not True:
                code = str((preview if preview.get('ok') is not True else result).get('code', 'native_refusal'))
                if re.fullmatch(r'[a-z_]{1,64}', code) is None: code = 'native_refusal'
                raise AppError('invalid_input', 'native structural preparation отказала', details={'native_code': code})
            output = project / rel; plain(output)
            if not output.is_file() or output.stat().st_size > MAX_BYTES: raise AppError('unavailable', 'нет ограниченного native target')
            after = output.read_bytes(); digest = hashlib.sha256(after).hexdigest()
            key = 'resource_hash' if native['action'] == 'edit_resource' else 'project_hash' if native['action'] == 'edit_project_settings' else 'scene_hash'
            if result.get(key) != digest: raise AppError('conflict', 'native target hash не подтверждён')
            files = [] if before.get(rel) == after else [dict(path='res://' + rel, before_bytes=before.get(rel), after_bytes=after)]
            return files, []
