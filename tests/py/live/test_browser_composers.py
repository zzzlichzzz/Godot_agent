"""The panel's actual HTTP draft/send routes against isolated provider documents."""
import pytest

from .test_studio_conversation import local_studio
from tests.py.panel_tf.test_control_envelope import panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


ARENA = '''<textarea name="message" hidden></textarea><input type="search" value="keep">
<form><div class="tiptap ProseMirror" contenteditable="true" style="white-space:pre-wrap"></div></form>
<script>window.sends=0;document.onkeydown=e=>{if(e.key==='Enter' && !e.shiftKey){e.preventDefault();sends++}}</script>'''
ARENA_SEND = ARENA + r'''<script>
const field=document.querySelector('.tiptap');field.innerHTML='<p><br></p>';
document.execCommand('defaultParagraphSeparator',false,'p'); window.pastes=[];window.sent=[];
field.onbeforeinput=e=>{if(e.inputType==='insertText')pastes.push(e.data)};
field.oninput=()=>field.querySelectorAll('p > br:only-child').forEach(n=>n.className='ProseMirror-trailingBreak');
field.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();
 const logical=[...field.childNodes].map(n=>n.textContent).join('\n');sent.push([logical,field.innerText]);
 const user=document.createElement('div');user.className='user-message';user.textContent=logical;document.body.append(user);
 field.replaceChildren();history.pushState({},'', '/c/first');}};</script>'''
KIMI = '''<div class="chat-input-editor" contenteditable="true"></div><div class="send-button-container"></div>
<script>const field=document.querySelector('[contenteditable]');window.sent=[];window.files=[];
field.onpaste=e=>{let text=e.clipboardData.getData('text/plain');e.preventDefault();
 if(new TextEncoder().encode(text).length>4000){files.push(text);document.body.insertAdjacentHTML('beforeend','<b class="file-card-container">paste.txt</b>');field.innerText=window.afterPaste||''}
 else document.execCommand('insertText',false,text)};
document.querySelector('.send-button-container').onclick=()=>{if(window.block){window.attempts++;return}sent.push([field.innerText,files.splice(0)]);
 field.innerText='';document.querySelectorAll('.file-card-container').forEach(n=>n.remove())};</script>'''


def bind(browser, fixture, monkeypatch):
    http,headers,state,_,(_,_,app)=fixture
    from python.substrate.llm.browser.backends import browser_backend
    monkeypatch.setattr(browser_backend,'wait_driver',lambda:browser)
    monkeypatch.setattr(app.extensions['native_references'].state,'wait_driver',lambda *a,**k:browser)
    monkeypatch.setattr(app.extensions['godot_session'].gateway,'current_driver',lambda:browser)
    def post(route,**kw):
        return http.post(route,headers=headers,json=dict(panel_body(app,state,**kw),allow_addons=False,allow_self_edit=False)).json
    return post


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA}],indirect=True)
def test_panel_drafts_in_direct_and_battle(local_studio,cold_tf6,monkeypatch):
    browser=local_studio;post=bind(browser,cold_tf6,monkeypatch);seq=0
    for site in ('arena','arena_battle'):
        cid=post('/chats/new',site_id=site)['current_id']
        def draft(text):
            nonlocal seq
            seq+=1;return post('/chat/live_input',chat_id=cid,text=text,seq=seq)['applied']
        for text in ('привет','привет\nАрена','тест',''):
            assert draft(text)
            assert browser.execute_script('return document.querySelector(".tiptap").innerText').rstrip('\n')==text
        browser.execute_script('document.querySelector("form").setAttribute("aria-hidden","true")')
        assert not draft('blocked')
        assert browser.execute_script('return [sends,document.querySelector("input").value,document.querySelector("textarea").value]')==[0,'keep','']
        browser.execute_script('document.querySelector("form").removeAttribute("aria-hidden")')
        assert not post('/chats/open',id=cid)['history_only']


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA_SEND}],indirect=True)
@pytest.mark.parametrize('remount',[False, True])
def test_arena_accepts_logical_paragraphs_on_first_send(local_studio,cold_tf6,monkeypatch,remount):
    from types import SimpleNamespace
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    browser=local_studio;post=bind(browser,cold_tf6,monkeypatch)
    mon=SimpleNamespace(chat_request_count=lambda:0,end_battle_capture=lambda:None,is_generating=lambda:False,
                        assistant_message_count=lambda:0)
    monkeypatch.setattr(ArenaDelivery,'_ensure_monitor',lambda *_:mon)
    monkeypatch.setattr(ArenaDelivery,'_arena_targets',lambda *_:{})
    monkeypatch.setattr(ArenaDelivery,'_follow_first_chat_transition',lambda *_:None)
    monkeypatch.setattr(ArenaDelivery,'extract_answer_snapshot',lambda *_:{})
    monkeypatch.setattr(ArenaDelivery,'wait_for_new_answer',lambda *a,**kw:{'text':'Ответ. ===DONE==='})
    monkeypatch.setattr(ArenaDelivery,'_set_clipboard_text',lambda *_:pytest.fail('used system clipboard'))
    cid=post('/chats/new',site_id='arena')['current_id'];request='первая\n\nпоследняя' if remount else 'привет'
    assert post('/chat/live_input',chat_id=cid,seq=1,text=request)['applied']
    # A lost select-all shortcut can arrive as a literal 'a' after the mirrored draft.
    browser.execute_script('''pastes.length=0;field.addEventListener('keydown',e=>{
      if(e.code==='KeyA'){e.preventDefault();document.execCommand('insertText',false,'a')}
    });''')
    if remount:
        # A SPA replaces its field while committing the paste. The logical document
        # is intact; innerText now includes a non-document decoration as well.
        browser.execute_script('''field.addEventListener('input',()=>{const next=field.cloneNode(true);
          next.onkeydown=e=>{if(e.key==='Enter' && !e.shiftKey){e.preventDefault();
            const value=next.editor.getText({blockSeparator:'\\n'});sent.push([value,next.innerText]);
            const user=document.createElement('div');user.className='user-message';user.textContent=value;
            document.body.append(user);next.replaceChildren();history.pushState({},'', '/c/first')}};
          const text=[...next.childNodes].map(n=>n.textContent).join('\\n');
          const note=document.createElement('span');note.contentEditable='false';note.textContent='Decoration';next.append(note);
          next.editor={view:{dom:next},getText:()=>text};field.replaceWith(next);
        },{once:true})''')
    reply=post('/chat',chat_id=cid,prompt=request);assert reply['ok'],reply
    pastes,sent=browser.execute_script('return [pastes,sent]');assert len(pastes)==len(sent)==1
    logical,rendered=sent[0];assert logical==pastes[0] and rendered!=logical
    assert 'agent_action' in logical and logical.endswith(request) and logical.count(request)==1
    assert browser.current_url.endswith('/c/first')


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://www.kimi.ai/*':KIMI}],indirect=True)
def test_first_kimi_attachment_caption_and_plain_followup(local_studio,cold_tf6,monkeypatch):
    browser=local_studio;post=bind(browser,cold_tf6,monkeypatch)
    from python.substrate.llm.parsers.kimi_delivery import KimiDelivery
    # Only the remote response is simulated; the actual send must stay on this page.
    for method,reply in [('is_generating',False),('count_answers',0),('extract_answer_snapshot',{}),
                         ('answer_stream',''),('wait_for_new_answer',{'text':'Ответ. ===DONE==='})]:
        monkeypatch.setattr(KimiDelivery,method,lambda *a,ret=reply,**kw:ret)
    for method in ('_set_clipboard_text','_verify_clipboard_text','_dispatch_ctrl_v'):
        monkeypatch.setattr(KimiDelivery,method,lambda *args:pytest.fail('used system clipboard'))
    for seq,(request,leftover,caption) in enumerate([('привет',s,'привет') for s in ('привет','','ста')]+[('две\nстроки','ста','')],1):
        cid=post('/chats/new',site_id='kimi')['current_id']
        assert post('/chat/live_input',chat_id=cid,seq=seq,text=request)['applied']
        browser.execute_script('window.afterPaste=arguments[0]',leftover)
        assert post('/chat',chat_id=cid,prompt=request)['ok']
        sent=browser.execute_script('return sent');assert len(sent)==1
        body,files=sent[0];assert body==caption
        assert len(files)==1 and 'agent_action' in files[0] and files[0].endswith(request)
        assert post('/chat',chat_id=cid,prompt='пока')['ok']
        assert browser.execute_script('return sent.slice(1)')==[['пока',[]]]
    # A blocked submit leaves the card and an empty caption: neither success nor a second click.
    cid=post('/chats/new',site_id='kimi')['current_id'];browser.execute_script('window.block=true;window.attempts=0')
    monkeypatch.setattr(KimiDelivery,'wait_for_new_answer',lambda *a,**kw:pytest.fail('waited for an unsent request'))
    post('/chat',chat_id=cid,prompt='две\nстроки')
    assert browser.execute_script('return [attempts,sent.length,files.length,field.innerText]')==[1,0,1,'']
