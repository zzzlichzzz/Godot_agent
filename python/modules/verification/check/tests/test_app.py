"""Preflight before IO; one source read; no execution; typed failures."""
import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import PathPolicy


class FS:
    def __init__(self, raw=b'{}', exists=True, error=None):
        self.raw, self.exists, self.error = raw, exists, error
        self.calls = []

    def is_file(self, path):
        self.calls.append(('is_file', path))
        return self.exists

    def read_raw(self, path):
        self.calls.append(('read_raw', path))
        if self.error:
            raise self.error
        return self.raw


def context(fs, contributions=()):
    def port(name):
        assert name == 'fs'
        return fs
    return SimpleNamespace(port=port, path_policy=PathPolicy(),
        registry=SimpleNamespace(contributions=lambda name: contributions if name == 'verify' else ()))


def call(args, fs, contributions=()):
    from python.modules.verification.check import app
    return app.call('verify', args, context(fs, contributions))


@pytest.mark.parametrize('args,kind', [({}, 'invalid_input'), ({'path': ''}, 'invalid_input'),
    ({'path': 'x.json'}, 'invalid_input'), ({'path': 'res://../x.json'}, 'denied'),
    ({'path': 'res://addons/x.json'}, 'denied'), ({'path': 'res://x.json', 'kinds': []}, 'invalid_input'),
    ({'path': 'res://x.json', 'kinds': ['oops']}, 'invalid_input'),
    ({'path': 'res://x.json', 'unknown': True}, 'invalid_input')])
def test_invalid_input_never_reaches_io(args, kind):
    fs = FS()
    with pytest.raises(AppError) as error:
        call(args, fs)
    assert error.value.kind == kind
    assert fs.calls == []


@pytest.mark.parametrize('exception,kind', [(FileNotFoundError('private'), 'not_found'),
    (PermissionError('private'), 'denied'), (OSError(errno.EFBIG, 'private'), 'invalid_input'),
    (OSError(errno.EIO, 'private'), 'internal')])
def test_io_failures_are_sanitized(exception, kind):
    with pytest.raises(AppError) as error:
        call({'path': 'res://x.json'}, FS(error=exception))
    assert error.value.kind == kind and 'private' not in str(error.value)


def test_missing_file_is_not_read():
    fs = FS(exists=False)
    with pytest.raises(AppError) as error:
        call({'path': 'res://x.json'}, fs)
    assert error.value.kind == 'not_found'
    assert fs.calls == [('is_file', 'x.json')]


def test_source_once_and_normalized_path():
    fs = FS()
    answer = call({'path': 'res://./dir//x.json'}, fs)
    assert fs.calls == [('is_file', 'dir/x.json'), ('read_raw', 'dir/x.json')]
    assert answer['path'] == 'res://dir/x.json' and answer['checked'] is True


@pytest.mark.parametrize('size,allowed', [(READ_TEXT_MAX_BYTES, True), (READ_TEXT_MAX_BYTES + 1, False)])
def test_byte_boundary_even_if_port_ignores_limit(size, allowed):
    fs = FS(raw=b' ' * size)
    if allowed:
        assert call({'path': 'res://x.md'}, fs)['checked'] is False
    else:
        with pytest.raises(AppError) as error:
            call({'path': 'res://x.md'}, fs)
        assert error.value.kind == 'invalid_input'


def test_text_given_to_contribution_preserves_crlf_and_replacement():
    from python.modules.verification.shared.check_kind import CheckKind
    seen = []
    def lint(text, path, ctx):
        seen.append((text, path))
        return {'problems': [], 'auto_fixable': False}
    fs = FS(raw=b'hello\r\n\xff')
    result = call({'path': 'res://x.gd'}, fs, [CheckKind('gd', ('.gd',), lint)])
    assert seen == [('hello\r\n\ufffd', 'res://x.gd')]
    assert result['kinds'] == ['gd'] and len(fs.calls) == 2


def test_python_is_compiled_but_not_executed():
    result = call({'path': 'res://x.py'}, FS(raw=b'raise RuntimeError("executed")'))
    assert result['problems'] == [] and result['checked'] is True


@pytest.mark.parametrize('requested,expected,snapshots', [
    (None, ['gd', 'api'], 1), (['api', 'gd', 'api'], ['gd', 'api'], 1),
    (['api'], ['api'], 1), (['gd'], ['gd'], 0), (['py'], [], 0),
])
def test_selected_api_fragment_order_and_one_owner_read(requested, expected, snapshots):
    from python.modules.verification.shared.check_kind import CheckKind
    seen = []
    def api(text, path, ctx):
        seen.append((text, path))
        return {'problems': ['api'], 'auto_fixable': False, 'checked': True, 'unavailable': []}
    def gd(text, path, ctx):
        return {'problems': ['lint'], 'auto_fixable': False}
    fs = FS(raw=b'extends Node2D\nvar x: int = "wrong"\nfunc run():\n\tself.rotatte(1)\n')
    ctx = context(fs, (CheckKind('api', ('.gd',), api), CheckKind('gd', ('.gd',), gd)))
    from python.modules.verification.check import app
    args = {'path': 'res://x.gd'}
    if requested is not None:
        args['kinds'] = requested
    result = app.call('verify', args, ctx)
    assert result['kinds'] == expected
    assert len(seen) == snapshots
    if seen:
        assert seen == [(fs.raw.decode(), 'res://x.gd')]
    assert fs.calls == [('is_file', 'x.gd'), ('read_raw', 'x.gd')]
    if expected == ['gd', 'api']:
        assert result['problems'] == ['lint', 'api']
    assert result['checked'] is bool(expected)


def test_no_api_module_keeps_gd_checked_and_discloses_fallback():
    from python.modules.verification.shared.check_kind import CheckKind
    gd = CheckKind('gd', ('.gd',), lambda *_: {'problems': [], 'auto_fixable': False})
    result = call({'path': 'res://x.gd'}, FS(raw=b'extends Node2D\n'), (gd,))
    assert result['checked'] is True and result['kinds'] == ['gd']
    assert result['unavailable'][0] == {'kind': 'api', 'reason': 'no_module'}
