from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import PathPolicy
from tests.py.node_c7_ports import c7_ports
from .. import app
from .test_core import CASES, ROOT


class Reader:
    def __init__(self, project, error=None):
        self.project, self.error, self.reads = project, error, []
    def read_raw(self, path):
        self.reads.append(path)
        if self.error:
            raise self.error
        return (self.project / path).read_bytes()


def context(record, ports, error=None):
    project = ROOT / 'fixtures/projects' / record['fixture']
    ports = {'fs': Reader(project, error), 'gd_lint': ports['gd_lint'], 'node_diff': ports['node_diff']}
    return SimpleNamespace(path_policy=PathPolicy(str(project)), port=lambda name: ports[name])


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_application_matches_complete_plan_and_literal_errors(record, c7_ports):
    ctx, e = context(record, c7_ports), record['expect']
    if e['ok']:
        assert app.call('node_reparent_preview', record['args'], ctx) == e['result']
    else:
        with pytest.raises(AppError) as got:
            app.call('node_reparent_preview', record['args'], ctx)
        assert (got.value.kind, got.value.message) == (e['kind'], e['message'])


@pytest.mark.parametrize('fault,kind', [(FileNotFoundError('HOST-SECRET'), 'not_found'),
    (PermissionError('HOST-SECRET'), 'denied'), (OSError('HOST-SECRET'), 'invalid_input')])
def test_primary_faults_are_typed_without_absolute_leaks(fault, kind, c7_ports):
    with pytest.raises(AppError) as got:
        app.call('node_reparent_preview', CASES[0]['args'], context(CASES[0], c7_ports, fault))
    assert got.value.kind == kind and 'HOST-SECRET' not in got.value.message


@pytest.mark.parametrize('path', ['main.tscn', 'root.gd'])
def test_single_read_limit_on_scene_and_attached_script(path, c7_ports):
    ctx = context(CASES[0], c7_ports)
    ordinary = ctx.port('fs').read_raw
    ctx.port('fs').read_raw = lambda rel: b'x' * (READ_TEXT_MAX_BYTES + 1) if rel == path else ordinary(rel)
    with pytest.raises(AppError) as got:
        app.call('node_reparent_preview', CASES[0]['args'], ctx)
    assert got.value.kind == 'invalid_input'


@pytest.mark.parametrize('index', [4, 6, 7, 8, 9])
def test_preflight_refuses_before_attached_io(index, c7_ports):
    record = CASES[index]
    ctx = context(record, c7_ports)
    ordinary = ctx.port('fs').read_raw
    ctx.port('fs').read_raw = lambda rel: ordinary(rel) if rel == 'main.tscn' else pytest.fail('premature script IO')
    with pytest.raises(AppError) as got:
        app.call('node_reparent_preview', record['args'], ctx)
    assert got.value.message == record['expect']['message']


def test_ports_are_structural_and_apply_not_owned(c7_ports):
    from ..ports import RawReader, Linter, DiffPreview
    ctx = context(CASES[0], c7_ports)
    assert isinstance(ctx.port('fs'), RawReader)
    assert isinstance(ctx.port('gd_lint'), Linter) and isinstance(ctx.port('node_diff'), DiffPreview)
    with pytest.raises(AppError) as got:
        app.call('node_reparent_apply', {}, ctx)
    assert got.value.kind == 'unknown_tool'
