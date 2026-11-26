"""D122: replay a sequence like chat.txt through the real panel dispatcher and parser."""
import json
import threading
from types import SimpleNamespace

from tests.py.panel_tf.test_bug014_chat_turn import _setup_browser_chat
from tests.py.panel_tf.test_deepseek_delivery import _body, _install_composer
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical


def test_eight_reads_return_individually_and_can_finish(client, cold_tf6, monkeypatch):
    http, headers, state, root, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    chat = app.extensions['native_references'].state.STATE['current_chat_id']
    before = physical(root)
    path = 'res://hero.gd'
    actions = [dict(action='read_file', path=path),
               dict(action='read_file', paths=[path,'res://level.tscn'], max_chars=450),
               dict(action='read_file', path=path, start_line=2, end_line=3),
               dict(action='read_function', path=path), dict(action='read_function', path=path, names=['hit']),
               dict(action='read_function', path=path, names=['no_such_function']),
               dict(action='list_files', only_exts=['gd']), dict(action='list_files', max_depth=1)]
    feedback = []
    def reply(prompt):
        if prompt.startswith('Результат чтения:\n'):
            feedback.append(json.loads(prompt.split('\n', 2)[1]))
        else:
            assert prompt.endswith('проверить чтение') and 'res://hero.gd' not in prompt
        action = actions[len(feedback)] if len(feedback)<len(actions) else None
        return dict(text='Шаг проверен.\n===DONE===', actionRaw=json.dumps(action) if action else None)
    composer = _install_composer(app, monkeypatch, 'ok', reply)
    def post(endpoint, **body):
        res = http.post(endpoint,json=_body(app,state,chat_id=chat,**body), headers=headers)
        assert res.status_code==200, res.json
        return res.json
    result = post('/chat', prompt='проверить чтение')
    for step, action in enumerate(actions, 1):
        ticket = result['read_request']
        assert ticket['action']['action']==action['action'] and result['answer']=='Шаг проверен.'
        assert ticket['pause']==(step==8) and len(composer.submits)==step
        result = post('/chat/read/decision',request_id=ticket['id'],approved=True)
    assert result['state']=='final' and len(composer.submits)==9 and physical(root)==before
    assert len(feedback[1])==2 and 'hit' in feedback[3][0]['names']
    assert feedback[5][0]['missing']==['no_such_function']
    assert path in str(feedback[6]) and 'level.tscn' not in str(feedback[6])
    from python.substrate.llm.api import chat_store
    rows=chat_store.find_chat(str(state),chat)['transcript']
    assert [r['text'] for r in rows if r['role']=='user']==['проверить чтение']
    assert [r['text'] for r in rows if r['role']=='agent']==['Шаг проверен.']*9


def test_tickets_expire_and_new_prompts_replace_them(client, cold_tf6, monkeypatch):
    from python.channels.http import read_consent
    http, headers, state, _, app = _setup_browser_chat(client, cold_tf6, monkeypatch)
    now = [0]
    monkeypatch.setattr(read_consent, 'time', SimpleNamespace(monotonic=lambda:now[0]))
    chat = app.extensions['native_references'].state.STATE['current_chat_id']
    composer = _install_composer(app,monkeypatch,'ok',lambda _: dict(text='Запрос.\n===DONE===',
        actionRaw='{"action":"read_file","path":"res://hero.gd"}'))
    def request():
        return http.post('/chat',json=_body(app,state,prompt='прочти',chat_id=chat),headers=headers).json['read_request']['id']
    def decide(ticket, auth=headers, **extra):
        return http.post('/chat/read/decision',json=_body(app,state,chat_id=chat,request_id=ticket,approved=True,**extra),headers=auth)
    first, second = request(), request()
    assert decide(first).status_code==409
    assert decide(second, auth={}).status_code==403
    assert decide(second, action={'action':'create_file'}).status_code==400
    now[0]+=601
    assert decide(second).status_code==409 and decide(second).status_code==409
    assert len(composer.submits)==2 and 'Результат чтения' not in ''.join(composer.submits)


def test_browser_progress_arrives_before_the_completed_http_turn(client,cold_tf6,monkeypatch):
    http, headers, state, _, app = _setup_browser_chat(client,cold_tf6,monkeypatch)
    from python.substrate.llm.parsers import deepseek_parser
    import api_keys
    _install_composer(app,monkeypatch,'ok',lambda _:None)
    reached,release = threading.Event(),threading.Event()
    monkeypatch.setattr(api_keys,'_secrets_cache',{'list':['synthetic-progress-secret']})
    def wait(*_, progress_cb=None, **kwargs):
        progress_cb(dict(phase='печатает',elapsed=2,chars=32000,stream='synthetic-progress-secret '+'слово '*5500))
        reached.set()
        assert release.wait(8)
        return dict(text='Готово.\n===DONE===',actionRaw=None)
    monkeypatch.setattr(deepseek_parser.DeepSeekParser,'wait_for_new_answer',wait)
    responses=[]
    thread=threading.Thread(target=lambda:responses.append(app.test_client().post('/chat',json=_body(app,state,prompt='текст'),headers=headers)))
    thread.start()
    try:
        assert reached.wait(8)
        assert http.get('/chat/progress').status_code==403
        progress=http.get('/chat/progress',headers=headers).json
        assert progress['active'] and progress['phase']=='печатает' and 0<len(progress['stream'])<=30000
        assert 'слово' in progress['stream'] and 'synthetic-progress-secret' not in progress['stream']
    finally:
        release.set();thread.join(8)
    assert responses[0].json['response']=='Готово.'
    assert 'stream' not in http.get('/chat/progress',headers=headers).json
