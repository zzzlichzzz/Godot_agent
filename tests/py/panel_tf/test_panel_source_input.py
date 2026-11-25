"""D113 changes one input identity for D112, never the accepted extraction goldens."""
from importlib import import_module
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]
PATH = 'editor/native/agent_panel.gd'


def _panel_fact():
    rows = json.loads((ROOT / 'fixtures/corpus/scene_model/t1_script_facts/manifest.json').read_bytes())['script_facts']
    return next(row for row in rows if row['path'] == PATH)


def test_d113_input_revision_keeps_original_fact_and_all_business_goldens():
    revise = import_module('tests.py.panel_tf.source_inputs').revised_panel_fact
    fact = _panel_fact()
    original = dict(fact)
    updated = revise(fact, (ROOT / PATH).read_bytes())
    assert fact == original and fact['bytes'] == 82171 and updated['bytes'] == 82185
    assert updated['sha256'] == 'c160c67762741a4b0d55596f4d4c1e44527e2e2c297b6013a61d2a99b8b3ac43'
    assert {k: v for k, v in updated.items() if k not in ('bytes', 'sha256')} == {
        k: v for k, v in fact.items() if k not in ('bytes', 'sha256')
    }


def test_d113_input_revision_refuses_any_unproved_source_drift():
    revise = import_module('tests.py.panel_tf.source_inputs').revised_panel_fact
    fact = _panel_fact()
    current = (ROOT / PATH).read_bytes()
    with pytest.raises(ValueError):
        revise(fact, current + b'X')


def test_d113_input_revision_cannot_rebind_any_other_source():
    revise = import_module('tests.py.panel_tf.source_inputs').revised_panel_fact
    fact = _panel_fact()
    current = (ROOT / PATH).read_bytes()
    with pytest.raises(ValueError):
        revise(dict(fact, path='editor/native/agent_entry.gd'), current)
