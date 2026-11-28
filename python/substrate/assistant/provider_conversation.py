"""Provider-owned launch pages and permanent conversation identities for the dock."""
import time

from python.kernel.errors import AppError
from python.substrate.llm.browser.page_origin import kimi_provisional, permanent, route

_INPUT = {'qwen':'textarea.message-input-textarea,textarea#chat-input,[contenteditable="true"]',
          'deepseek':'textarea#chat-input,textarea[name="search"]', 'kimi':'.chat-input-editor[contenteditable="true"]'}


def save_unique(store, base, cid, site, url):
    target = permanent(site, url)
    if not target: return None
    with store._lock(base):
        if any(r['id'] != cid and permanent(site, r.get('url')) == target for r in store.list_chats(base)):
            return None
        return store.update_chat(base, cid, url=target)


def ready(driver, site):
    if site['id'] in ('arena', 'arena_battle'):
        from python.substrate.llm.parsers.arena_composer import composer
        return bool(composer(driver))
    return driver.execute_script('return [...document.querySelectorAll(arguments[0])].some(el => '
                                 'el.checkVisibility({opacityProperty:true,visibilityProperty:true}) && '
                                 '!el.matches(":disabled,[readonly]") && !el.closest("[inert],[role=dialog],[aria-hidden=true]"))', _INPUT[site['id']]) is True


def open_launch(driver, site, navigate):
    from python.substrate.llm.parsers import studio_navigation
    window, home = driver.current_window_handle, site['new_chat_url']
    if not navigate(driver, home): return False
    if site['id'] == 'aistudio': return studio_navigation.open_blank(driver, window, home)
    # The site may require login before the first send. Never save its redirect
    # (or the previous conversation) as the newly created chat's destination.
    return driver.current_window_handle == window and route(site, driver.current_url) == home


class FirstReply:
    """A route can change at first dispatch, not at an arbitrary later reply."""
    def __init__(self, driver, site, start):
        self.window = driver.current_window_handle
        self.handles = set(getattr(driver, 'window_handles', ()) or ())
        self.start, self.site = route(site, start), site

    def confirmed(self, driver, prompt, *, accepted, parser=None, check=None):
        site = self.site; actual = route(site, driver.current_url); window = driver.current_window_handle
        if accepted and self.start == site['new_chat_url']:
            # Some SPA routers publish the id after the final response event.
            deadline = time.monotonic()+2.5
            while (window == self.window and time.monotonic() < deadline and
                   (actual == self.start or kimi_provisional(site, driver.current_url))):
                if check: check()
                time.sleep(.12)
                actual, window = route(site,driver.current_url), driver.current_window_handle
        if self.window == window and actual == self.start: return None
        new_arena = site['id'] in ('arena','arena_battle') and window not in self.handles
        if (self.start == site['new_chat_url'] and permanent(site, actual) and (window == self.window or new_arena)
                and (accepted or site['id'] == 'qwen') and (driver.execute_script(_SENT, prompt) is True
                     or accepted and _network_turn(driver, parser, site['id']))
                and driver.current_window_handle == window and route(site,driver.current_url) == actual):
            return actual
        raise AppError('conflict', 'Адрес диалога изменился, но отправленный запрос на этой странице не подтверждён. Проверьте вкладку агента.')


_SENT = r'''
const expected=arguments[0].replace(/\s+/g,' ').trim();
const selector='.qwen-chat-message-user,.user-message,.segment-user,.chat-content-item-user,[data-role="user"],[data-message-author-role="user"],.message-user,[data-testid="user-message"]';
return [...document.querySelectorAll(selector)].slice(-3).some(n=>[n,...n.querySelectorAll('p,.message-content,.chat-user-message,.whitespace-pre-wrap')].some(x=>(x.innerText||'').replace(/\s+/g,' ').trim()===expected));
'''


def _network_turn(driver, parser, sid):
    # Kimi may replace a long prompt with a .txt attachment. Verify the fresh
    # answer's actual browser target, not the first monitor on the same host.
    if sid not in ('qwen','kimi','arena','arena_battle'): return False
    p = getattr(parser,'PARSER',parser); mon = getattr(p,'_monitor',None)
    if not mon or getattr(p,'_req_count_before_send',None) is None or not p.net_answer_ready(driver): return False
    try:
        info = mon._cdp.send_command('Target.getTargetInfo',timeout=1)['targetInfo']
        return info['targetId'].lower() == driver.current_window_handle.lower() and info['url'] == driver.current_url
    except Exception: return False  # Includes the transport's native WSError.


def recover_qwen(driver, rec, site):
    """A legacy home URL is recoverable only with role/text evidence on the original page."""
    if not driver or site['id'] != 'qwen' or rec.get('transcript_trimmed'): return None
    rows = [(r['role'],r['text']) for r in rec.get('transcript',()) if r.get('role') in ('user','agent') and r.get('text')]
    if not rows or rows[0][0] != 'user' or 'agent' not in dict(rows): return None
    window = driver.current_window_handle
    def match():
        url = permanent(site, driver.current_url)
        if url and driver.execute_script(_MATCH, rows) is True and permanent(site, driver.current_url) == url:
            return url
    if (url := match()) and ready(driver,site): return url
    previous = driver.current_url; candidates = []
    from .chat_navigation import navigate
    # An already-open original tab is evidence too; navigate the selected tab
    # rather than stealing the user's other tab. Never inspect foreign documents.
    try:
        for h in getattr(driver,'window_handles',()):
            if h != window:
                driver.switch_to.window(h)
                if url := match(): candidates.append(url)
    finally:
        if driver.current_window_handle != window: driver.switch_to.window(window)
    if route(site,previous):
        deadline=time.monotonic()+2
        while driver.current_window_handle==window and route(site,driver.current_url)==route(site,previous):
            links=driver.execute_script('''return [...document.querySelectorAll('aside a[href],nav a[href],[class*=sidebar] a[href]')]
                .sort((a,b)=>Number(arguments[0].includes(b.innerText.trim()))-Number(arguments[0].includes(a.innerText.trim()))).map(a=>a.href)''',
                [rec.get('title',''),rows[0][1]])
            candidates += [u for link in (links if isinstance(links,list) else []) if (u:=permanent(site,link))]
            if candidates or time.monotonic()>=deadline: break
            time.sleep(.15)
    tried=False; confirmed=set()
    try:
        for candidate in list(dict.fromkeys(candidates))[:6]:
            if driver.current_window_handle != window: break
            tried=True
            if navigate(driver,candidate):
                end=time.monotonic()+2
                while driver.current_window_handle == window and time.monotonic()<end:
                    if match()==candidate and ready(driver,site): confirmed.add(candidate); break
                    time.sleep(.15)
            if len(confirmed)>1: return None
        if confirmed and driver.current_window_handle == window:
            candidate=confirmed.pop()
            if candidate!=permanent(site,driver.current_url): navigate(driver,candidate)
            if match()==candidate and ready(driver,site): tried=False; return candidate
    finally:
        if tried and driver.current_window_handle == window: navigate(driver,previous)
    return None


_MATCH = r'''
const turns=[...document.querySelectorAll('.qwen-chat-message-user,.qwen-chat-message-assistant')];
const rows=arguments[0], norm=s=>s.replace(/\[(\/?)(b|i|code|codeblock|u)\]/gi,'').replace(/\s+/g,' ').trim();
function prose(s){return norm(s.replace(/\n?```(?:agent_action\b|json\s*\n\s*\{\s*"action"\s*:)[\s\S]*$/i,'')
 .replace(/\s*===DONE===\s*$/,'').replace(/`([^`\n]+)`/g,'$1').replace(/\*\*(.+?)\*\*/g,'$1')
 .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm,'').replace(/^#{1,6}\s+/gm,''));}
const canon=x=>Array.isArray(x)?x.map(canon):x && typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canon(x[k])])):x;
function actions(s){const out=[];for(const m of s.matchAll(/```(?:agent_action|json)\s*\n([\s\S]*?)\n```/gi)){
 try{const a=JSON.parse(m[1]);if(typeof a?.action==='string')out.push(JSON.stringify(canon(a)));}catch{}
}return out;}
function rendered(el){
 const copy=el.cloneNode(true);
 const found=[];
 for(const pre of copy.querySelectorAll('pre')){
  const header=pre.querySelector('.qwen-markdown-code-header'),lang=header?.firstElementChild?.textContent.trim();
  if(lang!=='agent_action' && lang!=='json')continue;
  header.remove();const lines=[...pre.querySelectorAll('.view-line')];
  try{const a=JSON.parse((lines.length?lines.map(l=>l.textContent).join('\n'):pre.textContent).replace(/\u00a0/g,' '));
   if(typeof a?.action==='string'){found.push(JSON.stringify(canon(a)));pre.remove();}}catch{}
 }
 for(const n of copy.querySelectorAll('br,p,li,div,h1,h2,h3,tr'))n.append(' ');
 return [copy.textContent,found];
}
let i=0,users=0,agents=0;
for(const [role,text] of rows){
 let next=turns.findIndex((n,j)=>j>=i && n.matches('.qwen-chat-message-user')===(role==='user') &&
  [n,...n.querySelectorAll('.chat-user-message,.message-content,.response-message-content .qwen-markdown')].some(el=>{
    const s=el.innerText||'';if(role==='user'){const literal=v=>v.replace(/\s+/g,' ').trim();return literal(s.split('=== CURRENT REQUEST (answer it directly) ===\n').pop())===literal(text);}
    const expected=prose(text),wanted=actions(text),[body,found]=rendered(el);
    return expected && (prose(s)===expected || prose(body)===expected) &&
      (!wanted.length || [found,actions(s)].some(a=>JSON.stringify(a)===JSON.stringify(wanted)));}));
  if(next<0)return false;
 i=next+1; if(role==='user')users++;else agents++;
}return users>0 && agents>0;
'''
