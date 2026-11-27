"""AI Studio draft edits: one range replacement, never a send or a clear/retype retry."""
import re
from urllib.parse import urlsplit


def studio_route(url):
    try:
        page=urlsplit(url or '')
        if (page.scheme=='https' and page.netloc=='aistudio.google.com'
                and re.fullmatch(r'/prompts/[A-Za-z0-9_-]+',page.path)):
            # Studio's transient save flag and new-chat model selector aren't
            # conversation identities. Keep account/unknown parameters intact.
            query = '&'.join(part for part in page.query.split('&') if part != 'save=true' and
                             not (page.path == '/prompts/new_chat' and part.startswith('model=')))
            return page._replace(query=query, fragment='').geturl()
    except ValueError:
        pass
    return None


def is_new_prompt(url):
    return bool(studio_route(url)) and urlsplit(url).path == '/prompts/new_chat'


_COMPOSER=r'''
const fields = [], roots = [document];
const box = 'ms-prompt-box,ms-prompt-input,ms-prompt-input-wrapper,ms-chat-input';
const excluded = 'dialog,[role="dialog"],[inert],[aria-hidden="true"],ms-system-instructions,[data-turn-role]';
while (roots.length) {
    const root = roots.pop();
    for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) roots.push(el.shadowRoot);
        if (el.tagName !== 'TEXTAREA' || el.matches(':disabled,[readonly]') ||
            !el.checkVisibility({opacityProperty:true, visibilityProperty:true})) continue;
        let inside = false, blocked = false;
        for (let n = el; n; n = n.getRootNode().host) {
            inside ||= !!n.closest(box); blocked ||= !!n.closest(excluded);
        }
        const hint = [el.placeholder, el.getAttribute('aria-label')].join(' ');
        if (!blocked && !/system|instruction|search|системн|поиск/i.test(hint) &&
            (inside || /prompt|start typing|type something|message|запрос|сообщени/i.test(hint))) fields.push(el);
    }
}
const el = fields.length === 1 ? fields[0] : null;
'''

_READY = _COMPOSER + '''
return !!el && location.href === arguments[0] && (!arguments[1] ||
    !!document.querySelector('[data-turn-role="User"],[data-turn-role="Model"]'));
'''
_EDIT = _COMPOSER + r'''
const [url, desired] = arguments;
if (!el || location.href !== url) return false;
const old = el.value;
if (old === desired) return true;
// Compare Unicode scalars first. DOM selection and setRangeText take UTF-16 indices.
const a = Array.from(old), b = Array.from(desired);
let i=0, j=0;
while (i<a.length && i<b.length && a[i]===b[i]) i++;
while (j<a.length-i && j<b.length-i && a[a.length-1-j]===b[b.length-1-j]) j++;
const from=b.slice(0,i).join('').length, tail=b.slice(b.length-j).join('').length;
const change=desired.slice(from,desired.length-tail), to=old.length-tail;
const event={bubbles:true,composed:true,inputType:change ? 'insertText' : 'deleteContentBackward',data:change || null};
if (!el.dispatchEvent(new InputEvent('beforeinput',{...event,cancelable:true}))) return false;
if (location.href !== url || !el.isConnected || el.value!==old || el.matches(':disabled,[readonly]')) return false;
el.setRangeText(change,from,to,'end');
el.dispatchEvent(new InputEvent('input',event));
return el.isConnected && el.value===desired;
'''
_READBACK = _COMPOSER + 'return !!el && location.href === arguments[0] && el.value === arguments[1];'


class StudioDraft:
    def __init__(self, parser):
        self.parser=parser

    def mirror_input(self,driver,text,prefer_url=None):
        expected=studio_route(prefer_url)
        if not expected:return False
        actual=driver.current_url
        desired=text.replace('\r\n','\n').replace('\r','\n')
        if studio_route(actual)!=expected or not driver.execute_script(_EDIT,actual,desired):return False
        # A reactive page can replace/reset its textarea after the input handler returns.
        # Read the current visible composer in a separate browser command, without typing again.
        return driver.execute_script(_READBACK,actual,desired)
