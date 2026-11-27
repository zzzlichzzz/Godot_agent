"""A panel transcript is what /chats/open restores, independent of provider memory."""
from python.channels.http.app import create_app
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


def test_cold_reopen_only_visible_messages_in_selected_chat(cold_tf6, monkeypatch):
    http, headers, state, _, (_, _, app) = cold_tf6
    from python.substrate.llm.backends.api_backend import ApiBackend
    key = 'synthetic-local-transcript-fixture-key'
    project = app.extensions['native_references'].project

    def post(path, **fields):
        body = dict(panel_body(app, state, **fields), allow_addons=False, allow_self_edit=False)
        res = http.post(path, json=body, headers=headers)
        assert res.status_code == 200, res.json
        return res.json

    config = dict(provider='openrouter', model='synthetic-offline-model')
    post('/api/settings/set', key=key, **config)
    a, b = [post('/chats/new', kind='api', **config)['current_id'] for _ in range(2)]
    first = '## Вывод\n**Важно:** *курсив* и `код[0]`.'
    rendered = '[b][font_size=20]Вывод[/font_size][/b]\n[b]Важно:[/b] [i]курсив[/i] и [code]код[lb]0[rb][/code].'
    replies = iter([('internal partial', 'length'), (first, 'stop'), ('Второй ответ.', 'stop')])
    def reply(self, prompt):
        text, finish = next(replies)
        return dict(text=text, raw=text, finish_reason=finish)
    monkeypatch.setattr(ApiBackend, 'send', reply)
    assert post('/chat', chat_id=a, prompt='Запрос '+key)['answer'] == rendered
    assert post('/chat', prompt='Сообщение Б')['answer'] == 'Второй ответ.'
    app = create_app(project, state)
    http = app.test_client()
    for cid, expected in [(a, rendered), (b, 'Второй ответ.')]:
        rows = [r for r in post('/chats/open', id=cid)['transcript'] if r['role'] != 'system']
        assert [r['role'] for r in rows] == ['user', 'agent']
        assert rows[1]['text'] == expected
        if cid == a:
            assert rows[0]['text'].startswith('Запрос ')
        else:
            assert rows[0]['text'] == 'Сообщение Б'
    saved = (state/'agent_chats.json').read_text('utf-8')
    assert key not in saved and 'internal partial' not in saved


def test_implicit_chat_and_failed_save_do_not_resend(cold_tf6, monkeypatch):
    import json
    from python.substrate.llm.backends.api_backend import ApiBackend
    from python.substrate.llm.api import chat_store
    http, headers, state, _, (_, _, app) = cold_tf6
    calls = []
    def reply(self, prompt):
        calls.append(prompt)
        return dict(text='На экране.', raw='На экране.', finish_reason='stop')
    monkeypatch.setattr(ApiBackend, 'send', reply)
    def send(prompt):
        response=http.post('/chat',json=dict(panel_body(app,state,prompt=prompt),allow_addons=False,allow_self_edit=False),headers=headers)
        assert response.status_code==200
        return response.json
    token=headers['X-Agent-Token']
    assert send(token)['answer']=='На экране.'
    assert send('Вторая реплика')['answer']=='На экране.'
    saved=(state/'agent_chats.json').read_text('utf8');records=json.loads(saved)
    assert token not in saved and len(records)==1
    assert [r['role'] for r in records[0]['transcript']]==['user','agent','user','agent']
    def fail(*args): raise OSError('synthetic save failure')
    monkeypatch.setattr(chat_store, 'append_transcript_entries', fail)
    response=send('Третья реплика')
    assert response['answer']=='На экране.' and response['transcript_warning'] and len(calls)==3
    assert (state/'agent_chats.json').read_text('utf8')==saved
