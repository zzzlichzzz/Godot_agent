"""SEC-TF: external state cannot turn hardlinks into project effects."""
from importlib import import_module
import os
import pytest
from tests.py.panel_tf.conftest import http_client,isolated_chat_native_generation,extra_aliases
from tests.py.transfer_t1.test_write import client,physical

@pytest.mark.parametrize('route,payload',[
 ('/project/update_api_cache',{'classes':{'Node':{}},'godot_version':'SYNTHETIC'}),
 ('/project/api_cache_status',{})],ids=['cache-write','cache-read'])
def test_external_cache_hardlink_cannot_modify_or_read_project(http_client,client,route,payload):
    http,_,project,_,headers=http_client
    service=import_module('python.runtime.panel_services').PanelServices(project,client[2])
    path=service.reader.history_dir/'godot_api_cache.json';path.parent.mkdir(parents=True,exist_ok=True)
    os.link(project/'hero.gd',path);assert path.stat().st_nlink==2
    before=physical(project);response=http.post(route,json=payload,headers=headers)
    assert response.status_code==403 and response.json['kind']=='denied',response.json
    assert physical(project)==before and path.stat().st_nlink==2

@pytest.mark.parametrize('name',['log_state.json','log_state.json.tmp'],ids=['marker','native-temp'])
def test_external_log_marker_hardlink_refuses_before_turn(http_client,client,name,monkeypatch):
    http,agent,project,_,headers=http_client
    service=import_module('python.runtime.panel_services').PanelServices(project,client[2])
    log=service.state/'logs/godot.log';log.parent.mkdir();log.write_text('SCRIPT ERROR: synthetic offline\n','utf-8')
    assert http.post('/project/check_log',json={},headers=headers).status_code==200
    path=service.reader.history_dir/name;path.parent.mkdir(parents=True,exist_ok=True);os.link(project/'hero.gd',path)
    before=physical(project);calls=[];original=agent.call
    monkeypatch.setattr(agent,'call',lambda name,args:(calls.append(name),original(name,args))[1])
    response=http.post('/project/send_log_errors',json={},headers=headers)
    assert response.status_code==403 and response.json['kind']=='denied',response.json
    assert calls==[] and physical(project)==before and path.stat().st_nlink==2
    assert http.application.extensions['godot_session'].pending_log_report is not None

def test_external_log_input_hardlink_is_not_a_read_policy_bypass(http_client,client):
    http,_,project,_,headers=http_client
    service=import_module('python.runtime.panel_services').PanelServices(project,client[2])
    path=service.state/'logs/godot.log';path.parent.mkdir();os.link(project/'hero.gd',path)
    before=physical(project);response=http.post('/project/check_log',json={},headers=headers)
    assert response.status_code==403 and response.json['kind']=='denied',response.json
    assert physical(project)==before
