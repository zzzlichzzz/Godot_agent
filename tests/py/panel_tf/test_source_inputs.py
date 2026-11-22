"""D90 changes one input identity, never the accepted extraction goldens."""
from importlib import import_module
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]
PATH='editor/core/resource_publication_observer.gd'

def inputs():
    rows=json.loads((ROOT/'fixtures/corpus/scene_model/t1_script_facts/manifest.json').read_bytes())['script_facts']
    fact=next(row for row in rows if row['path']==PATH)
    return fact,(ROOT/'fixtures/corpus/scene_model/tf_observer_source/before.txt').read_bytes(),(ROOT/PATH).read_bytes()

def test_d90_input_revision_keeps_original_fact_and_all_business_goldens():
    revise=import_module('tests.py.panel_tf.source_inputs').revised_fact
    fact,before,current=inputs();original=dict(fact);updated=revise(fact,before,current)
    assert fact==original and fact['bytes']==370 and updated['bytes']==409
    assert updated['sha256']=='4e61db341215fc73142098265e243fb12a996f5a35348b3fcaa77faf9ed90f47'
    assert {k:v for k,v in updated.items() if k not in ('bytes','sha256')}=={k:v for k,v in fact.items() if k not in ('bytes','sha256')}

@pytest.mark.parametrize('which',['before','current'])
def test_d90_input_revision_refuses_any_unproved_source_drift(which):
    revise=import_module('tests.py.panel_tf.source_inputs').revised_fact
    fact,before,current=inputs()
    with pytest.raises(ValueError):revise(fact,before+b'X' if which=='before' else before,current+b'X' if which=='current' else current)

def test_d90_input_revision_cannot_rebind_any_other_source():
    revise=import_module('tests.py.panel_tf.source_inputs').revised_fact
    fact,before,current=inputs()
    with pytest.raises(ValueError):revise(dict(fact,path='editor/native/agent_resource_executor.gd'),before,current)
