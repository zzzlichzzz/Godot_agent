"""Only declared fake ports here; real composition is common integration."""
import errno
from types import SimpleNamespace
import pytest
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from .. import app


@pytest.mark.parametrize(('exc','kind'),[(FileNotFoundError('HOST-SECRET'),'not_found'),
    (PermissionError('HOST-SECRET'),'invalid_input'),(OSError(errno.EFBIG,'HOST-SECRET'),'invalid_input')])
def test_declared_port_typed_refusals(exc,kind):
    class Reader:
        def read_raw(self,path):
            raise exc
    ctx = SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Reader())
    with pytest.raises(AppError) as err:
        app.call('node',{'path':'scenes/hierarchy.tscn','node':'.'},ctx)
    assert err.value.kind == kind and 'HOST-SECRET' not in str(err.value)


def test_unknown_tool_refused():
    with pytest.raises(AppError) as err:
        app.call('node_rename',{},None)
    assert err.value.kind == 'unknown_tool'
