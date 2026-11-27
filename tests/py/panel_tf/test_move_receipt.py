from tests.py.panel_tf.test_qwen_turn import setup
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


def test_committed_move_receipt_contains_both_names_and_uid(client,cold_tf6,monkeypatch):
    from python.substrate.llm.browser.backends.browser_backend import BrowserBackend
    _,root,_=client
    app,cid,post=setup(client,cold_tf6,monkeypatch)
    before=physical(root)
    source,dest='res://hero.gd','res://moved.gd'
    action=dict(action='move_file',path=source,dest=dest)
    monkeypatch.setattr(BrowserBackend,'send',lambda *a,**kw:dict(text='Перенесу.',action=action))
    preview=post('/chat',chat_id=cid,prompt='Перенеси hero.gd')
    assert preview.status_code==200 and preview.json['pending_confirmation'] and physical(root)==before
    receipt=post('/chat/confirm_action',chat_id=cid,approved=True).json
    assert receipt['state']=='COMMITTED' and set(receipt['changed_paths'])=={source,dest,source+'.uid',dest+'.uid'}
    assert (root/'moved.gd').read_bytes()==before['hero.gd'] and (root/'moved.gd.uid').read_bytes()==before['hero.gd.uid']
    assert post('/chat/rollback').status_code==200 and physical(root)==before
