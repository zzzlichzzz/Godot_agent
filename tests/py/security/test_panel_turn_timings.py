"""Timing evidence can be read locally without granting access to a conversation."""
import json
import os

import pytest

from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_deepseek_delivery import _body, _install_composer
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


def test_private_browser_timings_survive_reopen(client,cold_tf6,monkeypatch):
    http,headers,state,_,app = _setup_browser_chat(client,cold_tf6,monkeypatch)
    from python.substrate.llm.parsers import deepseek_parser
    _install_composer(app,monkeypatch,'ok',lambda _:None)
    def wait(*_, progress_cb, **kwargs):
        progress_cb(dict(phase='secret-unknown-phase',stream='res://secret-path',chars=17))
        progress_cb(dict(phase='проверяю, что ответ дописан',stream='secret-response\n===DONE===',chars=25))
        progress=http.get('/chat/progress',headers=headers).json
        assert progress['phase']=='Маркер получен · сверяю ответ'
        return dict(text='secret-response\n===DONE===',actionRaw=None)
    monkeypatch.setattr(deepseek_parser.DeepSeekParser,'wait_for_new_answer',wait)
    response=http.post('/chat',json=_body(app,state,prompt='secret-question'),headers=headers)
    assert response.status_code==200, response.json
    assert response.json['answer']=='secret-response'
    record,=json.loads((state/'agent_turn_timings.json').read_text('utf8'))
    assert record['kind']=='message' and record['outcome']=='final' and record['chars']==25
    assert 0<=record['first_text_ms']<=record['visible_done_ms']<=record['verify_ms']<=record['total_ms']
    assert record.keys()=={'kind','outcome','utc_s','chars','first_text_ms','visible_done_ms','verify_ms','total_ms'}


def test_bounded_history_and_untrusted_prior_rows(tmp_path):
    from python.substrate.panel_timings import TimingLog
    writer=TimingLog(tmp_path/'profile',tmp_path/'project')
    row=dict(kind='read',outcome='final',utc_s=123,chars=100,first_text_ms=None,
             visible_done_ms=None,verify_ms=None,total_ms=40)
    writer.append(row)
    path=tmp_path/'profile/agent_turn_timings.json'
    path.write_text(json.dumps([row]*70 + [dict(row,phase='PRIVATE'),dict(row,kind='PRIVATE')]))
    writer.append(dict(row,utc_s=456))
    rows=json.loads(path.read_text());assert len(rows)==64 and rows[-1]['utc_s']==456
    assert rows[:-1]==[row]*63
    before=path.read_bytes()
    event=dict(variants=1,decision='single',mode='direct')
    for extra in (dict(stream='PRIVATE'), dict(read_tool='PRIVATE', read_results=['ok']),
                  dict(arena=[dict(event,answer='private')], arena_posts=[1]),
                  dict(arena=[dict(event,decision='private')], arena_posts=[1]),
                  dict(arena=[event],arena_posts=['private']),
                  dict(read_tool='read', read_results=['res://private']), dict(read_tool='read', read_results=['ok']*6)):
        with pytest.raises(ValueError):writer.append(dict(row,**extra))
    assert path.read_bytes()==before
    path.unlink();outside=tmp_path/'outside';outside.write_text('untouched');os.link(outside,path)
    from python.kernel.errors import AppError
    with pytest.raises(AppError):writer.append(row)
    assert outside.read_text()=='untouched'
