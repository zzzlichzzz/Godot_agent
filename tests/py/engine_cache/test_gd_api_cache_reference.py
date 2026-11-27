import hashlib
import json
import re
from unittest.mock import patch
import pytest
from tools import check_limits as limits
from tools import security_audit
from tests.py.engine_cache.observations import CORPUS,ROOT,cases,observe

@pytest.mark.parametrize('row',cases('cache'),ids=lambda row:row['id'])
def test_cache_corpus(row,tmp_path):
    assert observe(row['input'],tmp_path/row['id'])==row['expected']

class SourcePath:
    def __init__(self,relative):
        self.relative,self.name=relative,relative.rsplit('/',1)[-1]
    def relative_to(self,root):
        from pathlib import Path
        return Path(self.relative)

BOUNDARIES=[]
for folder in ('engine','store','verification'):
    base='python/substrate/'+folder
    BOUNDARIES.extend([(base+'/reference.py',939,True),(base+'/reference.py',3400,True),(base+'/reference.py',3401,False),
                       (base+'/nested/reference.py',3400,True),(base+'_wrong/reference.py',401,False),
                       (base+'/app.py',81,False),(base+'/module.py',151,False),(base+'/tools.py',151,False)])
BOUNDARIES.extend([('python/substrate/elsewhere.py',401,False),('python/substrate/elsewhere.py',400,True),
                   ('python/substrate/llm/backends/reference.py',3400,True),('python/substrate/project/reference.py',2000,True),('python/substrate/project/reference.py',2001,False)])
@pytest.mark.parametrize('relative,lines,accepted',BOUNDARIES)
def test_narrow_class_boundary(relative,lines,accepted):
    with patch.object(limits,'python_files',return_value=[SourcePath(relative)]),patch.object(limits,'line_count',return_value=lines):
        assert (not limits.check_files()) is accepted

def test_old_limits_unchanged():
    assert (limits.FILE_MAX,limits.MODULE_MAX,limits.AREA_MAX,limits.AREA_COHESION_MAX,limits.FOLDER_MIN,limits.FOLDER_MAX)==(400,3000,8000,8400,5,9)
    assert limits.ENTRY_MAX=={'module.py':150,'tools.py':150,'app.py':80}
    assert (limits.VERBATIM_FILE_MAX,limits.PARSER_VERBATIM_FILE_MAX,limits.API_VERBATIM_FILE_MAX,limits.ROUTING_VERBATIM_FILE_MAX,limits.PROJECT_VERBATIM_FILE_MAX)==(600,3400,3400,3400,2000)

def test_reference_and_dataset_pins(tmp_path):
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    folders={'history_manager.py':'store','gd_api_cache.py':'engine','gd_api_check.py':'verification','gd_lint.py':'verification'}
    for name,expected in manifest['sources'].items():
        raw=(ROOT/'python/substrate'/folders[name]/name).read_bytes()
        assert {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'LF':raw.count(b'\n'),'CRLF':raw.count(b'\r\n')}==expected
    raw=(ROOT/'agent_api_cache/default_api_cache.json').read_bytes()
    assert len(raw)==2004630 and hashlib.sha256(raw).hexdigest()=='7352d27c8d8ed77b84b3b98400093c85144c4b6f8b8919b147ca035a67c8a93c'
    assert not any(re.search(pattern,raw.decode('utf-8')) for pattern in security_audit.SECRET_PATTERNS)
    from python.substrate.store.api_cache_store import ApiCacheStore
    from tests.py.engine_cache.observations import snapshot
    project=tmp_path/'project';project.mkdir()
    before=snapshot(tmp_path)
    store=ApiCacheStore(project,state_dir=tmp_path/'absent-state',addon_dir=ROOT)
    classes,version=store.snapshot()
    assert len(classes)==1488 and version=='4.6.3-stable (official)'
    assert len(store.classes())==1488
    assert snapshot(tmp_path)==before and not (tmp_path/'absent-state').exists()
    assert hashlib.sha256((ROOT/'agent_api_cache/default_api_cache.json').read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()

def test_manifest_once_only_case_fixture_integrity():
    manifest=json.loads((CORPUS/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['cases'])==len({row['id'] for row in manifest['cases']})==228
    for row in manifest['cases']:
        raw=(CORPUS/row['file']).read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    for relative,expected in manifest['fixtures'].items():
        raw=(CORPUS/relative).read_bytes()
        assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
