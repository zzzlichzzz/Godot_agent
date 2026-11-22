"""Explicit D98 source-input revision; no old test or business golden is edited."""
from pathlib import Path
from tests.py.panel_tf.source_inputs import PATH,revised_fact

ROOT=Path(__file__).resolve().parents[1]

def pytest_collection_modifyitems(items):
    target=ROOT/'tests/py/formats/test_scene_deps_facts.py';revised=0
    for item in items:
        if Path(item.path)!=target or getattr(item,'originalname',None)!='test_handlers_and_code_facts_differential_all_gd':continue
        fact=item.callspec.params['fact']
        if fact['path']!=PATH:continue
        before=(ROOT/'fixtures/corpus/scene_model/tf_observer_source/before.txt').read_bytes()
        item.callspec.params['fact']=revised_fact(fact,before,(ROOT/PATH).read_bytes());revised+=1
    assert revised<=1,'D90 observer input must not be duplicated'
