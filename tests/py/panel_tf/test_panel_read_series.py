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
    (root/'actors').mkdir()
    before = physical(root)
    path = 'res://hero.gd'
    actions = [dict(action='read_file', path=path),
               dict(action='read_file', paths=[path,'res://actors',path,'res://no.gd'], max_chars=450),
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
    assert len(feedback[1])==3 and 'hit' in feedback[3][0]['names']
    file, directory, missing = feedback[1]
    assert file['path']==path and directory['error']['target_type']=='directory'
    assert 'list_files' in directory['error']['hint'] and 'target_type' not in missing['error']
    assert feedback[5][0]['missing']==['no_such_function']
    assert path in str(feedback[6]) and 'level.tscn' not in str(feedback[6])
    log=(state/'agent_turn_timings.json').read_text('utf8')
    turns=json.loads(log)
    assert len(turns)==9 and 'read_tool' not in turns[0]
    assert turns[2]['read_tool']=='read' and turns[2]['read_results']==['ok','directory','not_found']
    assert turns[6]['read_tool']=='functions' and turns[6]['read_results']==['missing_names']
    assert path not in log and 'no_such_function' not in log and 'Шаг проверен' not in log
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


def test_one_consent_for_disjoint_lines_and_no_repeat(client,cold_tf6,monkeypatch):
    http, headers, state, root, app = _setup_browser_chat(client,cold_tf6,monkeypatch)
    chat=app.extensions['native_references'].state.STATE['current_chat_id']
    original='Найди две части скрипта'
    spans=[[2,3],[9,10]]
    action=dict(action='read_file',path='res://hero.gd',ranges=spans)
    prompts=[]
    def reply(prompt):
        prompts.append(prompt)
        return dict(text='Чтение.\n===DONE===',actionRaw=json.dumps(dict(action,reason=str(len(prompts)))))
    _install_composer(app,monkeypatch,'ok',reply)
    def post(path,**args):
        response=http.post(path,json=_body(app,state,chat_id=chat,**args),headers=headers)
        assert response.status_code==200,response.json
        return response.json
    ticket=post('/chat',prompt=original)['read_request']
    assert ticket['action']['ranges']==spans and len(prompts)==1
    result=post('/chat/read/decision',request_id=ticket['id'],approved=True)
    assert result['state']=='final' and 'Чтение остановлено' in result['answer'] and 'read_request' not in result
    assert len(prompts)==3 and original in prompts[0] and all(original not in p for p in prompts[1:])
    chunks=json.loads(prompts[1].split('Результат чтения:\n')[1]);lines=(root/'hero.gd').read_text().splitlines()
    assert [(c['start_line'],c['end_line'],c['content'].splitlines()) for c in chunks]==[(a,b,lines[a-1:b]) for a,b in spans]
    assert 'Результат чтения' not in prompts[2]


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
