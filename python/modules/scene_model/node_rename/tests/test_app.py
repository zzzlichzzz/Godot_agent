import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import PathPolicy
from .. import app
from .test_core import CASES, ROOT, supplied


class Reader:
    def __init__(self, project, error=None):
        self.project, self.error = project, error
    def read_raw(self, rel_path):
        if self.error:
            raise self.error
        return (self.project / rel_path).read_bytes()


def context(record, error=None):
    project = ROOT / 'fixtures/projects' / record['fixture']
    reader = Reader(project, error)
    _, _, lint = supplied(record)
    ports = {'fs': reader, 'gd_lint': lint}
    return SimpleNamespace(path_policy=PathPolicy(str(project)), port=lambda name: ports[name])


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_app_literal_plan_and_refusals(record):
    ctx, e = context(record), record['expect']
    if e['ok']:
        assert app.call('node_rename_preview', record['args'], ctx) == e['result']
    else:
        with pytest.raises(AppError) as error:
            app.call('node_rename_preview', record['args'], ctx)
        assert (error.value.kind, error.value.message) == (e['kind'], e['message'])


@pytest.mark.parametrize('error,kind', [(FileNotFoundError('HOST-SECRET'), 'not_found'),
    (PermissionError('HOST-SECRET'), 'denied'), (OSError(errno.EFBIG, 'HOST-SECRET'), 'invalid_input'),
    (OSError(errno.EIO, 'HOST-SECRET'), 'invalid_input')])
def test_primary_io_is_typed_and_does_not_leak_host(error, kind):
    with pytest.raises(AppError) as got:
        app.call('node_rename_preview', CASES[0]['args'], context(CASES[0], error))
    assert got.value.kind == kind and 'HOST-SECRET' not in got.value.message


@pytest.mark.parametrize('where', ['main.tscn', 'main.gd'])
def test_shared_read_limit_is_enforced_on_primary_and_attached(where):
    ctx = context(CASES[1])
    ordinary = ctx.port('fs').read_raw
    ctx.port('fs').read_raw = lambda rel: b'x' * (READ_TEXT_MAX_BYTES + 1) if rel == where else ordinary(rel)
    with pytest.raises(AppError) as error:
        app.call('node_rename_preview', CASES[1]['args'], ctx)
    assert error.value.kind == 'invalid_input'


def test_unknown_apply_is_not_a_preview_entry():
    with pytest.raises(AppError) as error:
        app.call('node_rename_apply', {}, context(CASES[0]))
    assert error.value.kind == 'unknown_tool'


def test_consumer_protocols_are_structural():
    from ..ports import RawReader, Linter
    ctx = context(CASES[0])
    assert isinstance(ctx.port('fs'), RawReader)
    assert isinstance(ctx.port('gd_lint'), Linter)


@pytest.mark.parametrize('record', [CASES[8], CASES[10]], ids=lambda r: r['id'])
def test_target_refusal_precedes_unnecessary_attached_reads(record):
    ctx = context(record)
    ordinary = ctx.port('fs').read_raw
    read = []
    def guarded(rel):
        read.append(rel)
        return ordinary(rel) if rel == 'main.tscn' else b'x' * (READ_TEXT_MAX_BYTES + 1)
    ctx.port('fs').read_raw = guarded
    with pytest.raises(AppError) as error:
        app.call('node_rename_preview', record['args'], ctx)
    assert error.value.message == record['expect']['message']
    assert read == ['main.tscn']
