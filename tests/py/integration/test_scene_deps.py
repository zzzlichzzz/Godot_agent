"""Real recursive filesystem, untouched candidate and attached/project files."""
import hashlib
import json
from pathlib import Path
import pytest
from python.runtime.bootstrap import build_agent

ROOT=Path(__file__).resolve().parents[3]
CORPUS=ROOT/'fixtures/corpus/scene_model/scene_deps'
CASES=[json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_dispatcher_native_dependencies_and_read_only(case,tmp_path):
    project=ROOT/'fixtures/projects'/case['fixture']
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file()}
    agent=build_agent(project,profile='headless',state_dir=tmp_path/'state')
    answer=agent.call('scene_deps',case['args'])
    assert answer['ok']==case['expect']['ok']
    if answer['ok']:
        assert answer['result']==case['expect']['result']
    else:
        assert answer['kind']==case['expect']['kind'] and answer['message']==case['expect']['message']
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file()}
