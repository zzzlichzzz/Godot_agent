"""Only the declared channel reference lane changes old corpus selection."""
import json
from pathlib import Path
from tools.corpus_replay import selected_folders,corpus_routes

def test_native_http_lane_is_selected_without_touching_old_module_selection(tmp_path):
    root=tmp_path/'channels/http';root.mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'module':'channels.http','reference_only':True}),encoding='utf-8')
    other=tmp_path/'ordinary';other.mkdir();folders=[other,root]
    assert selected_folders(folders,'channels.http')==[root]
    assert selected_folders(folders,'assistant.write')==folders

def test_native_http_lane_is_not_sent_to_the_ordinary_agent_dispatcher(tmp_path,monkeypatch):
    import sys,types
    root=tmp_path/'channels/http';root.mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'module':'channels.http','reference_only':True}),encoding='utf-8')
    replay=types.SimpleNamespace(replay=lambda folder,compare:(5,5,[]))
    monkeypatch.setitem(sys.modules,'tools.http_replay',replay)
    @corpus_routes(lambda a,b,path:'')
    def ordinary(cache,folder,only=None): raise AssertionError('reference data became a public tool call')
    assert ordinary({},root,{'http'})==(5,5,[])
    assert ordinary({},root,{'assistant_plan'})==(0,0,[])
