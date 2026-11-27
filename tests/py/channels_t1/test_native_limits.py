"""Exact-path/full-byte native exceptions, not a server-directory escape hatch."""
from pathlib import Path
import pytest

CASES=[pytest.param('chat_routes.py',1080,id='chat_routes.py-1080'),('server_state.py',832)]

@pytest.fixture
def mirrored_checker(monkeypatch,tmp_path):
    from tools import check_limits
    monkeypatch.setattr(check_limits,'ROOT',tmp_path)
    monkeypatch.setattr(check_limits,'PYTHON',tmp_path/'python')
    return check_limits,tmp_path

def materialize(root,name,data):
    path=root/'python/substrate/assistant/server'/name
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return path

def native(name):
    return (Path(__file__).resolve().parents[3]/'python/substrate/assistant/server'/name).read_bytes()

@pytest.mark.parametrize('name,cap',CASES)
def test_exact_native_path_and_bytes_have_the_measured_cap(mirrored_checker,name,cap):
    checker,root=mirrored_checker;path=materialize(root,name,native(name))
    assert checker.line_count(path)==cap and checker.check_files()==[]

@pytest.mark.parametrize('name,cap',CASES)
def test_eol_mutation_revokes_native_permission(mirrored_checker,name,cap):
    checker,root=mirrored_checker;materialize(root,name,native(name).replace(b'\r\n',b'\n'))
    assert checker.check_files()==[f'python/substrate/assistant/server/{name}: {cap} строк (лимит 400)']

@pytest.mark.parametrize('name,cap',CASES)
def test_sibling_path_cannot_borrow_native_permission(mirrored_checker,name,cap):
    checker,root=mirrored_checker;materialize(root,'copy_'+name,native(name))
    assert checker.check_files()==[f'python/substrate/assistant/server/copy_{name}: {cap} строк (лимит 400)']

@pytest.mark.parametrize('name,cap',CASES)
def test_extra_line_cannot_borrow_native_permission(mirrored_checker,name,cap):
    checker,root=mirrored_checker;materialize(root,name,native(name)+b'\n')
    assert checker.check_files()==[f'python/substrate/assistant/server/{name}: {cap+1} строк (лимит 400)']

def test_default_entry_and_area_caps_remain_closed(mirrored_checker):
    checker,root=mirrored_checker
    assert (checker.FILE_MAX,checker.MODULE_MAX,checker.AREA_MAX,checker.AREA_COHESION_MAX)==(400,3000,8000,8400)
    assert checker.ENTRY_MAX=={'module.py':150,'tools.py':150,'app.py':80}
    materialize(root,'app.py',b'\n'*81)
    assert checker.check_files()==['python/substrate/assistant/server/app.py: 81 строк (лимит 80)']
