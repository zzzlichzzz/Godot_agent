"""Deletion stays a read-only client report, with scripts unchanged bytewise."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_delete'
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def snapshot(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_headless_client_full_native_report_and_project_bytes(record, tmp_path):
    project = ROOT / 'fixtures/projects' / record['fixture']
    before = snapshot(project)
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path / 'state')
    answer = agent.call('node_delete_preview', record['args'])
    assert snapshot(project) == before
    e = record['expect']
    assert answer['ok'] == e['ok']
    if e['ok']:
        assert answer['result'] == e['result']
    else:
        assert (answer['kind'], answer['message']) == (e['kind'], e['message'])


def test_delete_read_owner_and_unrequested_apply_is_unknown(tmp_path):
    agent = build_agent(project_root=ROOT / 'fixtures/projects/minimal', profile='headless', state_dir=tmp_path)
    assert 'node_delete_preview' in {t['name'] for t in agent.tools()}
    effects = agent.call('context', {'sections': ['tools']})['result']['sections']['tools']['effects']
    assert effects['node_delete_preview'] == 'read'
    assert 'scene_model.node_delete' not in agent.disabled()
    assert agent.call('node_delete_apply', {})['kind'] == 'unknown_tool'


@pytest.mark.parametrize('args', [{}, {'path': 'res://main.tscn', 'node': 1},
    {'path': 'res://main.tscn', 'node': 'Old', 'cleanup_code': 'yes'}])
def test_client_bad_args_are_typed_before_domain(args, tmp_path):
    agent = build_agent(project_root=ROOT / 'fixtures/projects/minimal', profile='headless', state_dir=tmp_path)
    assert agent.call('node_delete_preview', args)['kind'] == 'invalid_input'
