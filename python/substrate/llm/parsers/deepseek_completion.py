"""Positive completion evidence for the rebuild DeepSeek delivery adapter."""
import json
import re
from selenium.common.exceptions import WebDriverException
from parser_base import DONE_MARKER, answer_transfer_incomplete, height_says_incomplete
from . import deepseek_parser as native


PLACEHOLDER = '[color=#888888]— агент предлагает действие (см. ниже) —[/color]'
_READ = {'read_file', 'read_function', 'list_files', 'list_scene', 'search_project',
         'ask_librarian', 'gather_context', 'find_symbol_usages', 'analyze_rename'}
# For wrapped prose: require the text actually present in layout to match the
# extraction and glyph ranges to account for the height (no empty virtual region).
_WRAPPED = native._BLOCKS_JS + """
const blocks=__answerBlocks(), el=blocks[blocks.length-1];
if (!el || el.childElementCount>1024) return false;
const norm=s=>s.replace(/\\s+/g,' ').trim();
const visible=norm(el.innerText), expected=norm(arguments[0]), raw=arguments[1];
if (visible!==expected && !(raw && visible===norm(arguments[0].replace(raw,()=> 'agent_action '+raw)))) {
    // JS_EXTRACT adds markers to lists; Chromium's innerText may omit them.
    // Prove both projections from the same actual items. Never strip a number
    // out of arbitrary prose (it could be part of the answer).
    const plain=[], numbered=[]; let items=0;
    if (raw || el.childNodes.length>512) return false;
    for (const block of el.childNodes) {
        if (block.nodeType===1 && ['OL','UL'].includes(block.tagName)) {
            let index=0;
            for (const li of block.children) {
                if (++items>512 || li.tagName!=='LI' || li.querySelector('ol,ul')) return false;
                const part=li.innerText; plain.push(part);
                numbered.push((block.tagName==='UL'?'• ': (++index)+'. ')+part);
            }
        } else {
            const part=block.nodeType===3?block.textContent:block.innerText||'';
            plain.push(part); numbered.push(part);
        }
    }
    if (!items || norm(plain.join(' '))!==visible || norm(numbered.join(' '))!==expected) return false;
}
const box=el.getBoundingClientRect(), walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
const rows=[]; let node,n=0;
while(node=walker.nextNode()) {
    if (++n>2048) return false;
    if (!node.textContent.trim()) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    for(const r of range.getClientRects()) {
        if (rows.length>=4096) return false;
        if (r.width && r.height) rows.push([r.top,r.bottom]);
    }
}
let edge=box.top, covered=0;
for(const [top,bottom] of rows.sort((a,b)=>a[0]-b[0])) {
    if(top-edge>64) return false;
    covered+=Math.max(0,bottom-Math.max(top,edge)); edge=Math.max(edge,bottom);
}
return box.height>0 && covered>=0.65*box.height && box.bottom-edge<=64;
"""


def complete(driver, frame):
    text = frame.get('text') or ''
    raw = frame.get('actionRaw')
    if frame.get('error') or not text or len(text)>200000:
        return False
    material = text
    if raw is not None:
        if not isinstance(raw,str) or len(raw)>30000 or text.count(PLACEHOLDER)!=1:
            return False
        try: action=json.loads(raw)
        except (ValueError,RecursionError):return False
        if not isinstance(action,dict) or not isinstance(action.get('action'),str) or action['action'] not in _READ:
            return False
        if answer_transfer_incomplete(raw,text):return False
        material=text.replace(PLACEHOLDER,raw)
        text=text.replace(PLACEHOLDER,'').rstrip()
    marker = text.rstrip().rsplit('\n',1)[-1].strip()
    # innerText is plain, but JS_EXTRACT preserves Markdown emphasis. Require
    # the entire last line and a matching wrapper, never a quoted substring.
    if marker != DONE_MARKER and not any(marker == f'[{tag}]{DONE_MARKER}[/{tag}]' for tag in ('code','b','i')):
        return False
    if not height_says_incomplete(material,frame.get('blockHeight')):
        return True
    # Only remove formatting emitted by JS_EXTRACT (literal brackets are escaped there).
    visible=re.sub(r'\[/?(?:b|i|code|font_size(?:=20)?)\]', '', frame['text'])
    visible=visible.replace(PLACEHOLDER,raw or '').replace('[lb]','[').replace('[rb]',']')
    try:return driver.execute_script(_WRAPPED,visible,raw) is True
    except WebDriverException:return False
