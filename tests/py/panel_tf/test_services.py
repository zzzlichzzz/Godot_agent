"""Native positive read/preparation cases and explicit fail-closed boundaries."""
from importlib import import_module
from types import SimpleNamespace
import pytest
from tests.py.transfer_t1.test_write import physical

def test_librarian_query_uses_accepted_public_read(http_client):
    http,_,project,_,headers=http_client;before=physical(project)
    response=http.post('/librarian/query',json={'query':'hero.gd'},headers=headers)
    assert response.status_code==200 and response.json['success'] and isinstance(response.json['answer'],str)
    assert response.json['answer'] and physical(project)==before

def test_cache_update_status_external_native_cache_no_project_effect(http_client,client):
    http,_,project,_,headers=http_client;before=physical(project)
    services=import_module('python.runtime.panel_services').PanelServices(project,client[2])
    response=http.post('/project/update_api_cache',json={'classes':{'Node':{'methods':[]}},'godot_version':'4.6.SYNTHETIC'},headers=headers)
    assert response.status_code==200 and response.json=={'classes_count':1,'godot_version':'4.6.SYNTHETIC'}
    status=http.post('/project/api_cache_status',json={},headers=headers)
    assert status.status_code==200 and status.json=={'cached_version':'4.6.SYNTHETIC','has_cache':True}
    assert (services.reader.history_dir/'godot_api_cache.json').is_file() and physical(project)==before

@pytest.mark.parametrize('route,fields',[('',{'new_name':'Renamed'}),('/reparent',{'new_parent':'Pivot'}),('/delete',{})],ids=['rename','reparent','delete'])
def test_node_preview_apply_confirmation_rollback_real_bytes(http_client,route,fields):
    http,_,project,_,headers=http_client
    (project/'nodes.tscn').write_bytes(b'[gd_scene format=3]\r\n\r\n[node name="Root" type="Node"]\r\n\r\n[node name="Child" type="Node" parent="."]\r\n\r\n[node name="Pivot" type="Node" parent="."]\r\n')
    before=physical(project);body={'scene':'res://nodes.tscn','node_path':'Child',**fields};base='/scene/refactor/node'+route
    preview=http.post(base+'/preview',json=body,headers=headers)
    assert preview.status_code==200,preview.json
    assert physical(project)==before and preview.json['preview']['state']=='PREPARED'
    applied=http.post(base+'/apply',json=body,headers=headers)
    assert applied.status_code==200 and applied.json['state']=='COMMITTED',applied.json
    assert physical(project)!=before
    inverse=http.post('/chat/rollback',json={},headers=headers)
    assert inverse.status_code==200 and inverse.json['state']=='ROLLED_BACK' and physical(project)==before

def test_log_correct_userdata_argument_and_sent_after_success(http_client,client):
    http,_,project,_,headers=http_client;before=physical(project)
    services=import_module('python.runtime.panel_services').PanelServices(project,client[2]);log=services.state/'logs/godot.log'
    log.parent.mkdir();log.write_text('SCRIPT ERROR: synthetic offline error\n','utf-8')
    checked=http.post('/project/check_log',json={},headers=headers)
    assert checked.status_code==200 and checked.json['found']==1
    marker=services.reader.history_dir/'log_state.json';assert not marker.exists()
    sent=http.post('/project/send_log_errors',json={},headers=headers)
    assert sent.status_code==200 and sent.json['pending_action']['action']=='transaction'
    assert marker.is_file() and physical(project)==before
    assert http.post('/project/send_log_errors',json={},headers=headers).status_code==400

def test_live_input_owned_existing_parser_without_submit_or_start(http_client,monkeypatch):
    http,_,project,_,headers=http_client;before=physical(project)
    session=http.application.extensions['godot_session'];driver=object();calls=[]
    session.gateway=SimpleNamespace(current_driver=lambda:driver,_record={'kind':'site','site_id':'qwen','url':'https://invalid.offline.example/'})
    parser=SimpleNamespace(mirror_input=lambda d,t,prefer_url:(calls.append((d,t,prefer_url)),True)[1])
    module=import_module('python.runtime.panel_services');original=module.import_module
    monkeypatch.setattr(module,'import_module',lambda name:parser if name.startswith('python.substrate.llm.parsers.') else original(name))
    response=http.post('/chat/live_input',json={'seq':1,'text':'SYNTHETIC OFFLINE INPUT'},headers=headers)
    assert response.status_code==200 and response.json['applied'] is True,response.json
    assert calls==[(driver,'SYNTHETIC OFFLINE INPUT','https://invalid.offline.example/')]
    assert http.post('/chat/live_input',json={'seq':1,'text':'stale'},headers=headers).json['applied'] is False
    session.busy=True
    assert http.post('/chat/live_input',json={'seq':2,'text':'busy'},headers=headers).json['reason']=='busy'
    assert len(calls)==1 and physical(project)==before
