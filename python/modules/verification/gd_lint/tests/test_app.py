"""Application uses a consumer-owned fake port, never imports an adapter."""
import errno
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.verification.gd_lint import app


@pytest.mark.parametrize('error,kind', [(OSError(errno.EFBIG, 'too big'), 'invalid_input'),
                                       (PermissionError('unsafe path'), 'invalid_input'),
                                       (FileNotFoundError('missing'), 'not_found')])
def test_read_refusals_through_declared_port(error, kind):
    class Reader:
        def read_raw(self, rel):
            raise error
    ctx = SimpleNamespace(path_policy=PathPolicy('project'), port=lambda name: Reader())
    with pytest.raises(AppError) as exc:
        app.call('gd_lint', {'path': 'scripts/x.gd'}, ctx)
    assert exc.value.kind == kind


def test_unknown_tool_is_typed():
    with pytest.raises(AppError) as exc:
        app.call('other_tool', {}, None)
    assert exc.value.kind == 'unknown_tool'
