"""Consumer fakes, preflight-before-IO and literal corpus via application."""
import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import PathPolicy
from python.modules.verification.tscn_lint import app
from .corpus import CASES, ROOT, inputs


def context(case):
    files = inputs(case)
    class Reader:
        def is_file(self, rel):
            return rel in files
        def read_raw(self, rel):
            if rel not in files:
                raise FileNotFoundError(rel)
            return files[rel]
    class Cache:
        def classes(self):
            return case['reference_api_classes'] or {}
    ports = {'fs': Reader(), 'api_cache': Cache()}
    return SimpleNamespace(path_policy=PathPolicy(ROOT / 'fixtures' / case['fixture']),
                           port=ports.__getitem__)


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_full_corpus_through_app(case):
    if not case['expect']['ok']:
        with pytest.raises(AppError) as exc:
            app.call('check', case['args'], context(case))
        assert exc.value.kind == case['expect']['kind']
    else:
        actual = app.call('check', case['args'], context(case))
        assert actual == case['expect']['result']
        assert actual['fixed'].encode('utf-8') == case['expect']['result']['fixed'].encode('utf-8')


def no_io_context():
    def forbidden(name):
        pytest.fail('preflight/early-return accessed port: ' + name)
    return SimpleNamespace(path_policy=PathPolicy('project'), port=forbidden)


@pytest.mark.parametrize('args,kind', [
    ({}, 'invalid_input'), ({'path': 'res://x.tscn'}, 'invalid_input'),
    ({'path': 'x.tscn', 'content': ''}, 'invalid_input'),
    ({'path': 'res://x.tres', 'content': ''}, 'invalid_input'),
    ({'path': 'res://../x.tscn', 'content': ''}, 'denied'),
    ({'path': 'res://addons/foreign/x.tscn', 'content': ''}, 'denied'),
    ({'path': 'res://x.tscn', 'content': 1}, 'invalid_input'),
    ({'path': 'res://x.tscn', 'content': '', 'extra': 1}, 'invalid_input'),
    ({'path': 'res://x.tscn', 'content': '', 'planned_paths': [1]}, 'invalid_input'),
    ({'path': 'res://x.tscn', 'content': '', 'planned_paths': ['x.png']}, 'invalid_input'),
    ({'path': 'res://x.tscn', 'content': '', 'planned_paths': ['res://../x.png']}, 'denied'),
])
def test_preflight_refuses_before_io(args, kind):
    with pytest.raises(AppError) as exc:
        app.call('check', args, no_io_context())
    assert exc.value.kind == kind


@pytest.mark.parametrize('number', [4, 11, 18, 32, 34, 35, 64])
def test_scanner_and_non_scene_early_returns_before_io(number):
    case = CASES[number - 1]
    assert app.call('check', case['args'], no_io_context()) == case['expect']['result']


def test_utf8_content_uses_existing_byte_budget_before_io():
    args = {'path': 'res://x.tscn', 'content': 'я' * (READ_TEXT_MAX_BYTES // 2 + 1)}
    with pytest.raises(AppError) as exc:
        app.call('check', args, no_io_context())
    assert exc.value.kind == 'invalid_input'


@pytest.mark.parametrize('error,kind', [(PermissionError('unsafe'), 'denied'),
    (OSError(errno.EFBIG, 'too big'), 'invalid_input'), (FileNotFoundError('missing'), 'not_found')])
def test_metadata_port_failures_are_typed(error, kind):
    case = CASES[23]
    ctx = context(case)
    original = ctx.port
    class Broken:
        def is_file(self, rel):
            raise error
    ctx.port = lambda name: Broken() if name == 'fs' else original(name)
    with pytest.raises(AppError) as exc:
        app.call('check', case['args'], ctx)
    assert exc.value.kind == kind


def test_unknown_tool():
    with pytest.raises(AppError) as exc:
        app.call('check_apply', {}, None)
    assert exc.value.kind == 'unknown_tool'
