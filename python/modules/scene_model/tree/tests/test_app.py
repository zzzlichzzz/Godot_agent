"""Consumer-owned port boundary, no adapter/runtime imports."""
import errno
from types import SimpleNamespace
import pytest
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.scene_model.tree import app


@pytest.mark.parametrize('exc,kind', [(FileNotFoundError(),'not_found'),(PermissionError(),'invalid_input'),(OSError(errno.EFBIG,'host secret'),'invalid_input')])
def test_declared_reader_refusals_are_typed(exc, kind):
    class Reader:
        def read_raw(self, path):
            assert path == 'scenes/a.tscn'
            raise exc
    ctx = SimpleNamespace(port=lambda name: Reader(), path_policy=PathPolicy('.'))
    with pytest.raises(AppError) as got:
        app.call('scene', {'path':'res://scenes/a.tscn'}, ctx)
    assert got.value.kind == kind and 'host secret' not in str(got.value)


def test_unknown_tool_is_not_dispatched():
    with pytest.raises(AppError) as got:
        app.call('node_info', {}, None)
    assert got.value.kind == 'unknown_tool'
