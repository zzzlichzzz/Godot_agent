"""Read, judge and commit one branch of the current Qwen multi-response turn."""
import time

from python.kernel.errors import AppError
from .qwen_rename import rename_block


_DOM = r'''
const visible=e=>!!e?.checkVisibility({visibilityProperty:true});
const body='.response-message-content.phase-answer .qwen-markdown,.response-message-content:not([class*="phase-"]) .qwen-markdown';
const legacy='button.smulti-make-better';
function lists(){
 const groups=[...document.querySelectorAll('.smrm-list')].filter(visible);
 for(const b of document.querySelectorAll(legacy)){
  if(!visible(b)||b.closest('.smrm-list'))continue;
  const owner=b.closest('.qwen-chat-message-assistant');
  let l=b.parentElement;while(l && l!==document.body && (!owner||owner.contains(l)) && l.querySelectorAll(legacy).length<2)l=l.parentElement;
  if(l && l!==document.body && (!owner||owner.contains(l)) && l.querySelectorAll(legacy).length>=2 && !groups.includes(l))groups.push(l);
 }
 return groups.sort((a,b)=>a===b?0:(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1));
}
function cards(list){
 if(list.matches('.smrm-list'))return [...list.querySelectorAll(':scope > .smrm-card')];
 return [...list.querySelectorAll(legacy)].filter(visible).map(b=>{
  let c=b;while(c.parentElement!==list && c.parentElement.querySelectorAll(legacy).length===1)c=c.parentElement;
  return c;
 });
}
const button=c=>c.matches(legacy)?c:c.querySelector('.smrm-card__footer button.smrm-card__prefer-btn,'+legacy);
const current=()=>{const l=lists().at(-1),owner=l?.closest('.qwen-chat-message-assistant');
 return !owner||owner===[...document.querySelectorAll('.qwen-chat-message-assistant')].at(-1)?l:null;};
function answer(root){
 if(!root)return null;
 const parts=[];
 function visit(n){
  if(n.nodeType===3){parts.push(n.nodeValue);return;}
  if(n.nodeType!==1 || n.matches('script,style,button,svg'))return;
  if(n.matches('pre')){
   const box=n.querySelector('.view-lines');let code;
   const editor=window.monaco?.editor?.getEditors?.().find(e=>n.contains(e.getDomNode()));
   if(editor)code=editor.getModel()?.getValue();
   else if(box){
    const lines=[...box.querySelectorAll('.view-line')].sort((a,b)=>parseFloat(a.style.top)-parseFloat(b.style.top));
    const h=parseFloat(box.style.lineHeight),total=parseFloat(box.style.height);
     if(h && lines.length && lines.length*h===total && lines.every((l,i)=>parseFloat(l.style.top)===i*h))
      code=lines.map(l=>l.textContent.replace(/\u00a0/g,' ')).join('\n');
     else if(n.__agentFullBlock?.signature===box.outerHTML)code=n.__agentFullBlock.text;
   } else code=n.querySelector('code')?.textContent;
   if(code==null)throw 'partial';
   let lang=n.querySelector('.qwen-markdown-code-header > :first-child')?.textContent.trim()||'';
   // Qwen sometimes labels the protocol block json. Judge exactly what can become an action.
   if(lang==='json'){try{if(typeof JSON.parse(code)?.action==='string')lang='agent_action';}catch{}}
   parts.push('\n```'+lang+'\n'+code+'\n```\n');return;
  }
  if(n.matches('br'))parts.push('\n');
  n.childNodes.forEach(visit);
  if(n.matches('p,div,li,h1,h2,h3,h4,tr'))parts.push('\n');
 }
 try{visit(root);return parts.join('').trim();}catch{return null;}
}
function rows(list){return cards(list).map(c=>{const b=button(c),root=c.querySelector('.smrm-card__content')||c;
 const parts=[...root.querySelectorAll(body)].map(answer);
 return [c.id,parts.length && parts.every(t=>t!==null)?parts.join('\n').trim():null,visible(b)&&!b.disabled&&b.getAttribute('aria-disabled')!=='true'];});}
'''
_BASE = _DOM + 'return lists().map(l=>[l,cards(l).map(c=>c.id)]);'
_FRESH = _DOM + '''const l=current();return l?[l,cards(l).map(c=>c.id)]:null;'''
_CLICK = _DOM + '''const [list,expected,index]=arguments;
 if(current()!==list || JSON.stringify(rows(list))!==JSON.stringify(expected))return false;
 button(cards(list)[index]).click();return true;'''
_CONFIRM = _DOM + '''const [text,id]=arguments,l=current();
 if(l && id && cards(l).some(c=>c.id===id && button(c)?.getAttribute('aria-pressed')==='true'))return true;
 const turns=[...document.querySelectorAll('.qwen-chat-message-assistant')];
 const nodes=[...(turns.at(-1)||document).querySelectorAll(body)].filter(n=>!n.closest('.smrm-list')&&visible(n));
 if(text===null)return !l && nodes.length>0;
 return (!l || id && !cards(l).some(c=>c.id===id)) &&
        (answer(nodes.at(-1))===text || nodes.map(answer).join('\\n').trim()===text);'''


class QwenChoices:
    def __init__(self, driver, project, addon, valid_read=None, rank=None):
        self.rank = rank
        self.project, self.addon, self.valid_read = project, addon, valid_read
        old = driver.execute_script(_BASE)
        self.old_lists = {el for el, _ in old}
        self.old_ids = {cid for _, ids in old for cid in ids if cid}
        self.text = self.frame = self.action = None
        self.attempted = False

    def resolve(self, driver, check):
        if self.frame is not None: return
        if self.attempted: raise AppError('unavailable','Qwen не подтвердил выбор ветки. Проверьте диалог на сайте.')
        group = driver.execute_script(_FRESH)
        if not group or self.old_ids.intersection(group[1]) or (group[0] in self.old_lists and not all(group[1])): return
        from answer_judge import select_best_project_answer
        from parser_base import split_net_text_and_action
        group = group[0]; before = None; stable_since = time.monotonic(); deadline = stable_since+90
        while time.monotonic()<deadline:
            check(driver)
            options = driver.execute_script(_DOM+'return rows(arguments[0]);', group)
            if options!=before: stable_since=time.monotonic()
            if any(enabled and not text for _,text,enabled in options):
                _copy_missing(driver, group, check)
            if (len(options)>=2 and all(r[2] for r in options) and options==before
                    and (all(r[1] for r in options) or time.monotonic()-stable_since>=4)):
                # The DOM may also contain literal markdown rather than a rendered pre.
                canonical={i:(rename_block(r[1]) or (None,None,r[1]))[2] for i,r in enumerate(options) if r[1]}
                readable=list(canonical.items())
                key,text,judgment,judgments = ((self.rank(readable) if self.rank else select_best_project_answer(self.project,readable,addon_dir=self.addon))
                                               if readable else (0,None,None,[]))
                # The frozen Arena judge predates panel symbol reads. Only a single
                # unknown-action finding may be resolved by the active READ schema.
                eligible=[]
                for i,j in judgments:
                    action=j['action'] or {}; issues=j['blocking']
                    if j['acceptable'] and not issues: eligible.append((i,j))
                    elif (self.valid_read and len(issues)==1 and issues[0]['category']=='schema'
                          and issues[0]['message']=='unknown action: '+str(action.get('action')) and self.valid_read(action)):
                        eligible.append((i,dict(j,score=80)))
                if eligible:
                    key,judgment=max(eligible,key=lambda row:row[1]['score'])
                text=options[key][1]  # Confirm the exact visible card, not a normalized copy.
                check(driver)
                self.attempted = True  # Unknown outcome must never cast a second vote.
                if driver.execute_script(_CLICK,group,options,key): break
                self.attempted = False  # Snapshot changed before click: evaluate the new options.
            before=options; time.sleep(.35)
        else: raise AppError('unavailable','Qwen: варианты ответа не загрузились полностью.')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            check(driver)
            if driver.execute_script(_CONFIRM,text,options[key][0]):
                self.text=canonical.get(key,'')
                prose,raw=split_net_text_and_action(self.text)
                if not eligible:
                    self.action={'action':'parse_error','error':'Выбран вариант Qwen; исправьте ответ по протоколу.'}
                    raw=None
                else: self.action=judgment['action']
                self.frame={'text':prose,'actionRaw':raw,'error':None}; return
            time.sleep(.15)
        raise AppError('unavailable','Qwen не подтвердил выбор ветки. Проверьте диалог на сайте.')


def _copy_missing(driver, group, check):
    """Use Qwen's Copy for a virtualized Monaco; bind the result to this exact pre."""
    from parser_base import build_copy_click_js, _COPY_CAPTURE_READ_JS, _COPY_INTERCEPT_RESTORE_JS
    blocks=driver.execute_script(_DOM+'''return cards(arguments[0]).flatMap(c=>[...c.querySelectorAll('pre.qwen-markdown-code')]
        .filter(p=>answer(p)===null).map(p=>[p,p.querySelector('.view-lines')?.outerHTML]));''',group)
    for block,signature in blocks:
        if not signature: continue
        check(driver)
        script=build_copy_click_js('const block=arguments[0];function scoped(){return [block.parentElement];}',
            'scoped','pre.qwen-markdown-code','.qwen-markdown-code-header-action-item')
        idx=driver.execute_script("return [...arguments[0].parentElement.querySelectorAll('pre.qwen-markdown-code')].indexOf(arguments[0])",block)
        try:
            if not driver.execute_script(script.replace('__CB_IDX__',str(idx)),block): continue
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                check(driver); value=driver.execute_script(_COPY_CAPTURE_READ_JS)
                if value is not None:
                    driver.execute_script('arguments[0].__agentFullBlock={signature:arguments[1],text:arguments[2]}',block,signature,value)
                    break
                time.sleep(.1)
        finally: driver.execute_script(_COPY_INTERCEPT_RESTORE_JS)
