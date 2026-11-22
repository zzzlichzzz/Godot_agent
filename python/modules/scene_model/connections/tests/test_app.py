"""Read-only entrypoint against declared structural fake raw port."""
import errno
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from .. import app

ROOT=Path(__file__).resolve().parents[5]
CORPUS=ROOT/'fixtures/corpus/scene_model/connections'
CASES=[json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_app_call_full_corpus_and_literal_refusals(case):
    class Reader:
        def read_raw(self,path):
            return (CORPUS/'project'/path).read_bytes()
    ctx=SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Reader())
    if case['expect']['ok']:
        assert app.call('connections',case['args'],ctx)==case['expect']['result']
    else:
        with pytest.raises(AppError) as err:
            app.call('connections',case['args'],ctx)
        assert err.value.kind==case['expect']['kind']
        assert str(err.value).encode()==case['expect']['message'].encode()


@pytest.mark.parametrize(('exc','kind'),[(FileNotFoundError('HOST-SECRET'),'not_found'),
    (PermissionError('HOST-SECRET'),'denied'),(OSError(errno.EFBIG,'HOST-SECRET'),'invalid_input'),
    (OSError(errno.EIO,'HOST-SECRET'),'invalid_input')])
def test_primary_io_failures_are_typed_without_host_paths(exc,kind):
    class Reader:
        def read_raw(self,path):
            raise exc
    ctx=SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Reader())
    with pytest.raises(AppError) as err:
        app.call('connections',{'path':'main.tscn'},ctx)
    assert err.value.kind==kind and 'HOST-SECRET' not in str(err.value)


def test_unknown_tool():
    with pytest.raises(AppError) as err:
        app.call('write_connections',{},None)
    assert err.value.kind=='unknown_tool'


def test_consumer_protocol_uses_existing_fs_shape():
    from ..ports import RawReader
    class Reader:
        def read_raw(self,path):
            return b''
    assert isinstance(Reader(),RawReader)
