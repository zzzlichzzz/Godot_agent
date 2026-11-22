"""Native sites are byte-position capability records, never a blanket allowance."""
from pathlib import Path
import pytest
from tools import security_audit as checker
SOURCE=Path(__file__).resolve().parents[3]
CASES=('agent_server_link.gd','agent_updater.gd')
@pytest.fixture
def mirror(tmp_path,monkeypatch):
    monkeypatch.setattr(checker,'ROOT',tmp_path)
    monkeypatch.setattr(checker,'GD_ROOTS',(tmp_path/'editor',tmp_path/'runtime'))
    return tmp_path
def put(root,name,data):
    path=root/'editor/native'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
@pytest.mark.parametrize('name',CASES)
def test_exact_inactive_native_sites_have_measured_permission(mirror,name):
    put(mirror,name,(SOURCE/'editor/native'/name).read_bytes())
    assert checker.check_gdscript()==[]
@pytest.mark.parametrize('name',CASES)
def test_added_native_forbidden_site_revokes_all_permission(mirror,name):
    put(mirror,name,(SOURCE/'editor/native'/name).read_bytes()+b'\nfunc new_effect():\n\tOS.execute("untrusted", [])\n')
    assert checker.check_gdscript()
@pytest.mark.parametrize('name',CASES)
def test_sibling_file_cannot_borrow_native_permission(mirror,name):
    put(mirror,'copy_'+name,(SOURCE/'editor/native'/name).read_bytes())
    assert checker.check_gdscript()
def test_native_CRLF_change_revokes_permission(mirror):
    data=(SOURCE/'editor/native/agent_server_link.gd').read_bytes();assert b'\r\n' in data
    put(mirror,'agent_server_link.gd',data.replace(b'\r\n',b'\n'))
    assert checker.check_gdscript()
def test_unrelated_GDScript_forbidden_sites_remain_closed(mirror):
    put(mirror,'unrelated.gd',b'extends Node\nfunc effect():\n\tOS.create_process("x", [])\n')
    assert checker.check_gdscript()

def test_non_effect_trailing_bytes_revoke_full_SHA_permission_independently(mirror):
    data=(SOURCE/'editor/native/agent_updater.gd').read_bytes()
    put(mirror,'agent_updater.gd',data+b'\n# No new forbidden sites or shifted positions.\n')
    assert checker.check_gdscript()
