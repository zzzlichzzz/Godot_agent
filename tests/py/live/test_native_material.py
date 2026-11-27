"""The shipped resource executor must load in its disposable editor project."""
import os

import pytest

from python.runtime.bootstrap import build_agent
from tests.py.editor_t1.test_structural_overlay import AFTER, BASE, action
from tests.py.live.test_scene_uids_and_policy_live import _find_godot
from tests.py.transfer_t1.test_write import ok


@pytest.mark.needs_live
def test_material_keeps_its_uid_and_rolls_back(tmp_path, monkeypatch):
    engine = os.environ.get('GODOT_AGENT_GODOT_BIN') or _find_godot()
    if not engine:
        pytest.skip('Godot editor required')
    monkeypatch.setenv('GODOT_AGENT_GODOT_BIN', engine)
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'project.godot').write_bytes(b'config_version=5\n')
    target = project / 'material.tres'
    target.write_bytes(BASE)

    agent = build_agent(project, 'cli', state_dir=tmp_path / 'state')
    plan = ok(agent, 'assistant_plan', {'action': action()})
    assert plan['diffs'] == [{'path': 'res://material.tres', 'before': BASE.decode(), 'after': AFTER.decode()}]
    assert target.read_bytes() == BASE
    applied = ok(agent, 'assistant_confirm', {'plan_id': plan['plan_id'], 'digest': plan['digest'], 'approved': True})
    assert target.read_bytes() == AFTER
    ok(agent, 'assistant_rollback', {'plan_id': plan['plan_id'], 'entry_id': applied['entry_id']})
    assert target.read_bytes() == BASE
