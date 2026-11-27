"""Read-only locator inference respects visible scope and avoids guessing."""
import pytest

from python.runtime.bootstrap import build_agent


@pytest.mark.parametrize('tool,extra', [('usages', {}), ('analyze_rename', {'new_name': 'strike'})])
def test_symbol_locator_inference(tmp_path, tool, extra):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'project.godot').write_text('config_version=5\n', encoding='utf-8')
    (root / 'addons').mkdir()
    script = 'extends Node\n\nfunc hit():\n\tpass\n'
    (root / 'hero.gd').write_text(script, encoding='utf-8')
    (root / 'addons' / 'closed.gd').write_text(script, encoding='utf-8')
    agent = build_agent(root, 'test', state_dir=tmp_path / 'state')
    args = dict(kind='function', old_name='hit', **extra)
    unique = agent.call(tool, args)
    assert unique['ok'], unique
    locator = unique['result']['declaration']
    assert locator.startswith('res://hero.gd:3:')
    assert agent.call(tool, dict(args, declaration_path='res://addons/closed.gd'))['kind'] == 'denied'
    assert agent.call(tool, dict(args, declaration_path='res://../foreign.gd'))['kind'] == 'denied'
    (root / 'enemy.gd').write_text(script, encoding='utf-8')
    conflict = agent.call(tool, args)
    assert conflict['kind'] == 'invalid_input'
    assert 'res://hero.gd:3:' in conflict['message'] and 'res://enemy.gd:3:' in conflict['message']
    assert 'closed.gd' not in conflict['message']
    scoped = agent.call(tool, dict(args, declaration_path='res://hero.gd'))
    exact = agent.call(tool, dict(args, declaration=locator))
    assert scoped['ok'] and scoped == exact
    assert agent.call(tool, dict(args, declaration=locator, declaration_path='res://hero.gd'))['kind'] == 'invalid_input'
