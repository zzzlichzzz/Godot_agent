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
    ports = {'fs': Reader(project, error), 'node_diff': ports['node_diff']}
    return SimpleNamespace(path_policy=PathPolicy(str(project)), port=lambda name: ports[name])


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_application_matches_complete_plan_and_literal_errors(record, c7_ports):
    ctx, e = context(record, c7_ports), record['expect']
    if e['ok']:
        assert app.call('node_delete_preview', record['args'], ctx) == e['result']
    else:
        with pytest.raises(AppError) as got:
            app.call('node_delete_preview', record['args'], ctx)
        assert (got.value.kind, got.value.message) == (e['kind'], e['message'])


@pytest.mark.parametrize('fault,kind', [(FileNotFoundError('HOST-SECRET'), 'not_found'),
    (PermissionError('HOST-SECRET'), 'denied'), (OSError('HOST-SECRET'), 'invalid_input')])
def test_primary_faults_are_typed_without_absolute_leaks(fault, kind, c7_ports):
    with pytest.raises(AppError) as got:
        app.call('node_delete_preview', CASES[0]['args'], context(CASES[0], c7_ports, fault))
    assert got.value.kind == kind and 'HOST-SECRET' not in got.value.message


@pytest.mark.parametrize('path', ['main.tscn', 'root.gd'])
def test_single_read_limit_on_scene_and_remaining_script(path, c7_ports):
    ctx = context(CASES[1], c7_ports)
    ordinary = ctx.port('fs').read_raw
    ctx.port('fs').read_raw = lambda rel: b'x' * (READ_TEXT_MAX_BYTES + 1) if rel == path else ordinary(rel)
    with pytest.raises(AppError) as got:
        app.call('node_delete_preview', CASES[1]['args'], ctx)
    assert got.value.kind == 'invalid_input'


def test_root_refusal_precedes_scripts_and_removed_script_is_never_read(c7_ports):
    ctx = context(CASES[2], c7_ports)
    ordinary = ctx.port('fs').read_raw
    ctx.port('fs').read_raw = lambda rel: ordinary(rel) if rel == 'main.tscn' else pytest.fail('premature script IO')
    with pytest.raises(AppError) as got:
        app.call('node_delete_preview', CASES[2]['args'], ctx)
    assert got.value.message == CASES[2]['expect']['message']
    ctx = context(CASES[1], c7_ports)
    result = app.call('node_delete_preview', CASES[1]['args'], ctx)
    assert result == CASES[1]['expect']['result']
    assert 'tip.gd' not in ctx.port('fs').reads


def test_cleanup_false_reads_no_scripts_and_apply_not_owned(c7_ports):
    ctx = context(CASES[7], c7_ports)
    app.call('node_delete_preview', CASES[7]['args'], ctx)
    assert ctx.port('fs').reads == ['main.tscn']
    from ..ports import RawReader, DiffPreview
    assert isinstance(ctx.port('fs'), RawReader) and isinstance(ctx.port('node_diff'), DiffPreview)
    with pytest.raises(AppError) as got:
        app.call('node_delete_apply', {}, ctx)
    assert got.value.kind == 'unknown_tool'
