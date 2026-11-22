import errno
import hashlib
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import PathPolicy
from ..app import call


class FS:
    def __init__(self, files=None, dirs=(), fail=None):
        self.files = files if files is not None else {'plugin.cfg': b'', 'donor.gd': b'extends Node\nfunc alpha():\n\tpass\n'}
        self.dirs, self.fail, self.calls = set(dirs), fail, []

    def is_file(self, path):
        self.check('is_file', path)
        return path in self.files

    def read_raw(self, path):
        self.check('read_raw', path)
        return self.files[path]

    def exists(self, path):
        self.check('exists', path)
        return path in self.files or path in self.dirs

    def list_files(self):
        raise AssertionError('plan must not enumerate scan sources')

    def check(self, method, path):
        self.calls.append((method, path))
        if self.fail and self.fail[0] == method:
            raise self.fail[1]


class Cache:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {}, '4.6.3'

    def classes(self):
        raise AssertionError('plan must use only the fresh snapshot seam')

    def version(self):
        raise AssertionError('a separate version read is not a coherent snapshot')


def context(tmp_path, fs, cache=None):
    ports = {'fs': fs, 'api_cache': cache or Cache()}
    return SimpleNamespace(path_policy=PathPolicy(tmp_path), port=lambda name: ports[name])


@pytest.mark.parametrize('args', [{}, {'path': ''}, {'path': 1}, {'path': 'x.gd'},
    {'path': 'res://x.txt'}, {'path': 'res://x.gd', 'groups': {}},
    {'path': 'res://x.gd', 'groups': [{'module': 'part', 'funcs': 'alpha'}]},
    {'path': 'res://x.gd', 'target_lines': 99}, {'path': 'res://x.gd', 'target_lines': 5001},
    {'path': 'res://x.gd', 'target_lines': True}, {'path': 'res://x.gd', 'extra': 1}])
def test_invalid_plan_input_before_fs(tmp_path, args):
    fs, cache = FS(), Cache()
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', args, context(tmp_path, fs, cache))
    assert exc.value.kind == 'invalid_input'
    assert fs.calls == [] and cache.calls == 0


@pytest.mark.parametrize('value,message', [(99, 'target_lines must be between 100 and 5000'),
    (5001, 'target_lines must be between 100 and 5000'), ('100', 'укажите непустой path в формате res://…gd')])
def test_target_refusal_message_and_type_before_fs(tmp_path, value, message):
    fs, cache = FS(), Cache()
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd', 'target_lines': value}, context(tmp_path, fs, cache))
    assert exc.value.kind == 'invalid_input' and exc.value.message == message
    assert fs.calls == [] and cache.calls == 0


def test_empty_funcs_reaches_domain_after_read_before_snapshot(tmp_path):
    fs, cache = FS(), Cache()
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd', 'groups': [{'module': 'part_one', 'funcs': []}]}, context(tmp_path, fs, cache))
    assert exc.value.kind == 'invalid_input' and exc.value.message == 'группа part_one: пустой список funcs'
    assert ('read_raw', 'donor.gd') in fs.calls and cache.calls == 0


@pytest.mark.parametrize('newline', [b'\n', b'\r\n', b'\r'])
@pytest.mark.parametrize('bom', [b'', b'\xef\xbb\xbf'])
def test_factual_newline_but_normalized_donor_sha(tmp_path, newline, bom):
    normalized = b'extends Node\nfunc alpha():\n\tpass\n'
    raw = bom + normalized.replace(b'\n', newline)
    fs = FS({'plugin.cfg': b'', 'donor.gd': raw})
    answer = call('split_gd_plan', {'path': 'res://donor.gd'}, context(tmp_path, fs))
    assert answer['newline'] == newline.decode('ascii')
    assert answer['donor_sha256'] == hashlib.sha256(normalized).hexdigest()


@pytest.mark.parametrize('raw,expected', [(b'a\r\nb\rc\n', '\r\n'),
    (b'a\rb\n', '\r'), (b'a\nb', '\n'), (b'a', '\n')])
def test_file_newline_precedence_from_bytes(raw, expected):
    from ..domain.text import file_newline
    assert file_newline(raw) == expected


@pytest.mark.parametrize('path', ['res://../outside.gd', 'res://addons/probe/donor.gd'])
def test_policy_denied_before_fs(tmp_path, path):
    fs = FS()
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': path}, context(tmp_path, fs))
    assert exc.value.kind == 'denied' and fs.calls == []


def test_snapshot_once_per_call_and_no_project_writes(tmp_path):
    fs, cache = FS(), Cache()
    args = {'path': 'res://donor.gd', 'target_lines': 0}
    before = dict(fs.files)
    answer = call('split_gd_plan', args, context(tmp_path, fs, cache))
    assert call('split_gd_plan', args, context(tmp_path, fs, cache)) == answer
    assert answer['target_lines'] == 1100 and cache.calls == 2 and fs.files == before
    assert [p for method, p in fs.calls if method == 'exists'] == ['donor_part1.gd'] * 2


@pytest.mark.parametrize('method', ['is_file', 'read_raw', 'exists'])
@pytest.mark.parametrize('error,kind', [(PermissionError('C:/secret'), 'denied'),
    (OSError(errno.EFBIG, 'C:/secret'), 'invalid_input'), (OSError(errno.EIO, 'C:/secret'), 'internal')])
def test_plan_io_classification_sanitized(tmp_path, method, error, kind):
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd'}, context(tmp_path, FS(fail=(method, error))))
    assert exc.value.kind == kind and 'secret' not in exc.value.message


@pytest.mark.parametrize('occupied', ['file', 'directory'])
def test_target_occupation_exact_native_text(tmp_path, occupied):
    fs = FS(dirs=('part_one.gd',) if occupied == 'directory' else ())
    if occupied == 'file':
        fs.files['part_one.gd'] = b''
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd', 'groups': [{'module': 'part_one', 'funcs': ['alpha']}]}, context(tmp_path, fs))
    assert exc.value.kind == 'invalid_input'
    assert exc.value.message == 'целевой модуль уже существует: part_one.gd'


def test_raw_byte_limit_before_snapshot(tmp_path):
    fs, cache = FS(), Cache()
    fs.files['donor.gd'] = b'x' * (READ_TEXT_MAX_BYTES + 1)
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd'}, context(tmp_path, fs, cache))
    assert exc.value.kind == 'invalid_input' and cache.calls == 0


def test_raw_byte_limit_is_inclusive(tmp_path):
    fs, cache = FS(), Cache()
    raw = fs.files['donor.gd'] + b'#'
    fs.files['donor.gd'] = raw + b'x' * (READ_TEXT_MAX_BYTES - len(raw))
    assert call('split_gd_plan', {'path': 'res://donor.gd'}, context(tmp_path, fs, cache))['stats']['moved'] == 1
    assert cache.calls == 1


def test_disappearing_donor_is_not_found(tmp_path):
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd'}, context(tmp_path, FS(fail=('read_raw', FileNotFoundError('C:/secret')))))
    assert exc.value.kind == 'not_found' and 'secret' not in exc.value.message


def test_native_group_refusal_precedes_snapshot(tmp_path):
    fs, cache = FS(), Cache()
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd', 'groups': [{'module': 'part', 'funcs': ['missing']}]}, context(tmp_path, fs, cache))
    assert exc.value.message == 'метод missing не найден в доноре' and cache.calls == 0


def test_existence_precedes_same_target_preload_conflict(tmp_path):
    fs = FS(dirs=('part_one.gd',))
    fs.files['donor.gd'] = b'extends Node\nconst PartOne = 1\nfunc alpha():\n\tpass\n'
    with pytest.raises(AppError) as exc:
        call('split_gd_plan', {'path': 'res://donor.gd', 'groups': [{'module': 'part_one', 'funcs': ['alpha']}]}, context(tmp_path, fs))
    assert exc.value.message == 'целевой модуль уже существует: part_one.gd'
