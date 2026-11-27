"""Native bootstrap/dispatcher/default fs, not direct-domain substitutes."""
import hashlib
import json
from pathlib import Path
import pytest
from python.runtime.bootstrap import build_agent

ROOT=Path(__file__).resolve().parents[3]
CORPUS=ROOT/'fixtures/corpus/scene_model/connections'
CASES=[json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_dispatcher_full_literal_corpus_read_only(case,tmp_path):
    project=CORPUS/'project'
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file()}
    agent=build_agent(project,profile='headless',state_dir=tmp_path/'state')
    answer=agent.call('connections',case['args'])
    assert answer['ok']==case['expect']['ok']
    if answer['ok']:
        assert answer['result']==case['expect']['result']
    else:
        assert answer['kind']==case['expect']['kind'] and answer['message']==case['expect']['message']
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file()}
