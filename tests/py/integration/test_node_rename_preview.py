import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'fixtures/corpus/scene_model/node_rename').glob('[0-9]*.json'))]


def census(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


@pytest.mark.parametrize('record', CASES, ids=lambda r: r['id'])
def test_native_dispatcher_real_ports_read_only_plan(record, tmp_path):
    project = ROOT / 'fixtures/projects' / record['fixture']
    before = census(project)
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path / 'state')
    answer = agent.call('node_rename_preview', record['args'])
    e = record['expect']
    if e['ok']:
        assert answer['ok'] and answer['result'] == e['result']
    else:
        assert not answer['ok'] and (answer['kind'], answer['message']) == (e['kind'], e['message'])
    assert census(project) == before


def test_one_shared_lookup_and_relative_path_implementation():
    from python.modules.scene_model.node_info.domain import core as info
    from python.modules.scene_model.shared import node_path
    assert info.find_node_in_scene is node_path.find_node_in_scene
    assert info.rel_path_between is node_path.rel_path_between


def test_public_lint_port_reuses_accepted_algorithm(tmp_path):
    from python.modules.verification.gd_lint import lint_gdscript
    from python.modules.verification.gd_lint.domain.core import lint_gdscript as accepted
    assert lint_gdscript is accepted
    from python.runtime.bootstrap import default_ports
    assert default_ports(tmp_path, 'headless', tmp_path / 'state')['gd_lint'] is lint_gdscript
