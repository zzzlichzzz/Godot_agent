"""Typed arguments do not introduce a separate write capability."""
import pytest

from tests.py.transfer_t1.test_write import client, ok, physical


def test_typed_file_preview_requires_confirmation_and_can_roll_back(client):
    agent, project, _ = client
    before = physical(project)
    plan = ok(agent, 'assistant_plan', {'operations': [
        {'create_file': {'path': 'res://new.gd', 'content': 'extends Node\n'}},
        {'patch_file': {'path': 'res://new.gd', 'search': 'extends Node', 'replace': 'extends Node2D'}},
    ]})
    assert plan['diffs'] == [{'path': 'res://new.gd', 'before': None, 'after': 'extends Node2D\n'}]
    args = {key: plan[key] for key in ('plan_id', 'digest')}
    assert agent.call('write_apply', args)['kind'] == 'denied'
    assert physical(project) == before
    receipt = ok(agent, 'assistant_confirm', dict(args, approved=True))
    assert (project / 'new.gd').read_bytes() == b'extends Node2D\n'
    ok(agent, 'assistant_rollback', {'plan_id': plan['plan_id'], 'entry_id': receipt['entry_id']})
    assert physical(project) == before


@pytest.mark.parametrize('args', [
    {}, {'action': {'action': 'create_file'}, 'operations': [{}]},
    {'operations': [{}]}, {'operations': [{'run': {'command': 'echo'}}]},
    {'operations': [{'create_file': {'path': 'res://a.txt'}}]},
    {'operations': [{'create_file': {'path': 'res://a.txt', 'content': '', 'approved': True}}]},
    {'operations': [{'create_file': {'path': 'res://a.txt', 'content': ''},
                     'move_file': {'path': 'res://hero.gd', 'dest': 'res://b.gd'}}]},
    {'operations': [{'create_file': {'path': 'res://../escape.gd', 'content': 'extends Node\n'}}]},
    {'operations': [{'create_file': {'path': 'res://addons/x.gd', 'content': 'extends Node\n'}}]},
    {'operations': [{'patch_file': {'path': 'res://project.godot', 'search': '[application]', 'replace': ''}}]},
])
def test_typed_preview_rejects_mixed_invalid_and_protected_targets_without_wal(client, args):
    agent, project, state = client
    before = physical(project)
    result = agent.call('assistant_plan', args)
    assert not result['ok'] and result['kind'] in ('invalid_input', 'denied')
    assert before == physical(project) and not list(state.rglob('*.jsonl'))
