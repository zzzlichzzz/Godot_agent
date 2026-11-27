import hashlib
from importlib import import_module
import json
import pytest
from .observations import CORPUS,ROOT,cases,observe

def test_verbatim_judge_pin():
    raw=(ROOT/'python/substrate/assistant/answer_judge.py').read_bytes()
    expected=json.loads((CORPUS/'manifest.json').read_text('utf-8'))['source']
    assert {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'LF':raw.count(b'\n'),'CRLF':raw.count(b'\r\n')}==expected

def test_native_double_integrity():
    manifest=json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    assert manifest['oracle_runs']==2 and manifest['oracle_differences']==0
    assert [c['id'] for c in cases()]==manifest['case_ids']
    for name,pin in manifest['observations'].items():
        raw=(CORPUS/'native'/(name+'.json')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==pin['sha256']

@pytest.mark.parametrize('case',cases(),ids=lambda x:x['id'])
def test_public_native_parity(case,tmp_path):
    expected=json.loads((CORPUS/'native'/(case['id']+'.json')).read_text('utf-8'))
    assert observe(case,tmp_path/'public')==expected

@pytest.mark.parametrize('args',[{}, {'full_text':False},{'full_text':7},{'full_text':'x','extra':1},{'full_text':'\x00'},{'full_text':'x'*200001}])
def test_public_invalid_input(args,tmp_path):
    from python.runtime.bootstrap import build_agent
    result=build_agent(tmp_path,profile='test',state_dir=tmp_path.parent/'state').call('judge',args)
    assert result['ok'] is False and result['kind']=='invalid_input'

def test_missing_required_port_disables_owner(tmp_path):
    from python.runtime.bootstrap import build_agent,default_ports
    ports=default_ports(tmp_path,'test',tmp_path.parent/'state')
    del ports['librarian']
    result=build_agent(tmp_path,profile='test',ports=ports).call('judge',{'full_text':'===DONE==='})
    assert result['ok'] is False and result['kind']=='unavailable'
