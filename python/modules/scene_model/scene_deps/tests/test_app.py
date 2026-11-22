"""Consumer-declared project scan/read seams and primary-vs-scan IO policy."""
import errno
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from .. import app

ROOT=Path(__file__).resolve().parents[5]
CORPUS=ROOT/'fixtures/corpus/scene_model/scene_deps'
CASES=[json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_app_call_actual_old_corpus_and_literal_refusals(case):
    root=ROOT/'fixtures/projects'/case['fixture']
    class Files:
        def list_files(self):
            return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
        def read_raw(self,path):
            return (root/path).read_bytes()
    ctx=SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Files())
    if case['expect']['ok']:
        assert app.call('scene_deps',case['args'],ctx)==case['expect']['result']
    else:
        with pytest.raises(AppError) as err:
            app.call('scene_deps',case['args'],ctx)
        assert err.value.kind==case['expect']['kind']
        assert str(err.value).encode()==case['expect']['message'].encode()


@pytest.mark.parametrize(('exc','kind'),[(FileNotFoundError('HOST-SECRET'),'not_found'),
    (PermissionError('HOST-SECRET'),'denied'),(OSError(errno.EFBIG,'HOST-SECRET'),'invalid_input'),
    (OSError(errno.EIO,'HOST-SECRET'),'invalid_input')])
def test_primary_io_failures_are_typed(exc,kind):
    class Files:
        def list_files(self):
            return []
        def read_raw(self,path):
            raise exc
    ctx=SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Files())
    with pytest.raises(AppError) as err:
        app.call('scene_deps',{'path':'main.gd'},ctx)
    assert err.value.kind==kind and 'HOST-SECRET' not in str(err.value)


@pytest.mark.parametrize('blocked',['__pycache__/other.gd','addons/other.gd','.agent_history/other.gd'])
def test_scan_policy_and_skip_directory_do_not_read(blocked):
    seen=[]
    class Files:
        def list_files(self):
            return [blocked]
        def read_raw(self,path):
            seen.append(path)
            if path=='main.gd':
                return b'func _on_button_pressed():\n\tpass\n'
            raise AssertionError('restricted file was read')
    ctx=SimpleNamespace(path_policy=PathPolicy(),port=lambda name:Files())
    assert app.call('scene_deps',{'path':'res://main.gd'},ctx)['notes']==[]
    assert seen==['main.gd']


def test_existing_fs_structurally_satisfies_own_protocols():
    from ..ports import ProjectFiles,RawReader
    class Files:
        def list_files(self):
            return []
        def read_raw(self,path):
            return b''
    assert isinstance(Files(),ProjectFiles) and isinstance(Files(),RawReader)


def test_unknown_tool():
    with pytest.raises(AppError) as err:
        app.call('write_scene_deps',{},None)
    assert err.value.kind=='unknown_tool'
