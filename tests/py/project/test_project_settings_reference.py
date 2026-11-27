"""Strict settings intents/prepare only; no Godot get/set/confirm/undo integration."""
import pytest

from tests.py.project.observations import cases, load, observe

ROWS = cases('settings')


@pytest.mark.parametrize('row', ROWS, ids=[row['id'] for row in ROWS])
def test_project_settings_corpus(row, tmp_path):
    case = load(row)
    actual = observe(case['input'], tmp_path / 'sandbox')
    assert actual == case['expected']
    assert actual['before'] == actual['after'], 'prepare wrote project.godot'
    result = actual['result']
    if 'normalized' in result:
        assert result['prepared']['state'] == 'preview'
        assert result['prepared']['before_hash'] == actual['before']['files']['project/project.godot']
        assert result['public']['expected_project_hash'] == result['prepared']['before_hash']
        assert result['public']['prepare_in_editor'] is True
        assert 'action' not in result['public']
        assert result['reverse_digest'] == result['prepared']['action_digest']
