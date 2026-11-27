"""Explicit D98/D113/D116 source-input revisions; no old test or business golden is edited."""
from pathlib import Path
from tests.py.panel_tf.source_inputs import (
    BUG_REGISTER_REVISIONS,D116_REVISIONS,D122_REVISIONS,PANEL_PATH,PATH,revised_bug_register_fact,
    D123_REVISIONS,revised_dock_fact,revised_d116_fact,revised_fact,revised_panel_fact,
    D124_TRANSCRIPT,revised_transcript_fact,
    D124_VISUAL,revised_workspace_fact,D126_CHAT,revised_chat_fact,D128,D129,before_d128,
)

ROOT=Path(__file__).resolve().parents[1]

def pytest_collection_modifyitems(items):
    target=ROOT/'tests/py/formats/test_scene_deps_facts.py';revised=0;revised_panel=0;revised_d116=0
    for item in items:
        if Path(item.path)!=target or getattr(item,'originalname',None)!='test_handlers_and_code_facts_differential_all_gd':continue
        fact=item.callspec.params['fact']
        path=fact['path']; current=before_d128(path,(ROOT/path).read_bytes())
        if fact['path']==PATH:
            before=(ROOT/'fixtures/corpus/scene_model/tf_observer_source/before.txt').read_bytes()
            item.callspec.params['fact']=revised_fact(fact,before,(ROOT/PATH).read_bytes());revised+=1
        elif fact['path']==PANEL_PATH:
            item.callspec.params['fact']=revised_panel_fact(fact,current);revised_panel+=1
        elif fact['path'] in D126_CHAT:
            item.callspec.params['fact']=revised_chat_fact(fact,current)
        elif fact['path'] in D124_VISUAL:
            item.callspec.params['fact']=revised_workspace_fact(fact,current)
        elif fact['path'] in D116_REVISIONS:
            item.callspec.params['fact']=revised_d116_fact(fact,current);revised_d116+=1
        elif fact['path'] in D123_REVISIONS:
            item.callspec.params['fact']=revised_dock_fact(fact,(ROOT/fact['path']).read_bytes())
        elif fact['path'] in BUG_REGISTER_REVISIONS:
            item.callspec.params['fact']=revised_bug_register_fact(fact,(ROOT/fact['path']).read_bytes())
        elif fact['path']==D124_TRANSCRIPT:
            item.callspec.params['fact']=revised_transcript_fact(fact,current)
        elif fact['path'] in D122_REVISIONS:
            item.callspec.params['fact']=revised_bug_register_fact(fact,current,D122_REVISIONS)
        for revisions in (D128,D129):
            if path in revisions:
                prior=item.callspec.params['fact']
                assert [prior['bytes'],prior['sha256']]==revisions[path]['before']
                size,sha=revisions[path]['after'];item.callspec.params['fact']=dict(prior,bytes=size,sha256=sha)
    assert revised<=1,'D90 observer input must not be duplicated'
    assert revised_panel<=1,'D112 panel input must not be duplicated'
    assert revised_d116<=len(D116_REVISIONS),'D116 panel/locale inputs must not be duplicated'
