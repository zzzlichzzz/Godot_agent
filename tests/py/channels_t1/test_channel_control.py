"""Control plane must not queue behind a native/profile lock."""
import threading
from types import SimpleNamespace
from python.channels.http.app import create_app
from tests.py.channels_t1.test_channels import http_client
from tests.py.channels_t1.test_channel_security import raw_http
from tests.py.transfer_t1.test_write import client,physical

def test_oversized_numeric_host_port_is_denied_without_integer_conversion_failure(http_client):
    web,_,root,_,headers=http_client;before=physical(root)
    response=raw_http(web,'/health',{**headers,'Host':'127.0.0.1:'+('9'*6000)})
    assert response.status_code==403 and physical(root)==before

def test_stop_remains_available_during_a_blocked_chat_turn(http_client):
    _,_,root,state,headers=http_client;before=physical(root)
    entered=threading.Event();release=threading.Event();stopped=threading.Event();done=threading.Event();results={}
    class BlockedAgent:
        def call(self,name,args):
            assert name=='assistant_turn';entered.set();assert release.wait(10)
            return dict(ok=True,result=dict(state='answered',text='done',plan=None))
    app=create_app(root,state,agent=BlockedAgent(),native_routes=True)
    def stop():stopped.set();return True
    app.extensions['godot_session'].gateway=SimpleNamespace(stop=stop)
    def chat():results['chat']=app.test_client().post('/chat',json=dict(text='wait'),headers=headers)
    def cancel():
        try:results['stop']=app.test_client().post('/chat/stop',json={},headers=headers)
        finally:done.set()
    turn=threading.Thread(target=chat);control=threading.Thread(target=cancel);turn.start()
    try:
        assert entered.wait(5);control.start();assert done.wait(2),'Stop queued behind the blocked chat scope'
        assert stopped.is_set() and results['stop'].get_json()['ok'] is True
    finally:
        release.set();turn.join(10)
        if control.ident is not None:control.join(10)
    assert not turn.is_alive() and not control.is_alive() and physical(root)==before
