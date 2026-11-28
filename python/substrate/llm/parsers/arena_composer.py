"""Locate the chat editor, never a search field or a hidden fallback textarea."""
from selenium.webdriver.common.keys import Keys


def _field(driver):
    return driver.execute_script('''
      const visible = el => el.checkVisibility({opacityProperty:true,visibilityProperty:true});
      if ([...document.querySelectorAll('dialog[open],[role=dialog]')].some(el => visible(el) &&
          !el.closest('[hidden],[inert],[aria-hidden=true]'))) return 'dialog';
      const fields = [...document.querySelectorAll('form div.tiptap.ProseMirror[contenteditable="true"],textarea[name="message"]')]
        .filter(el => visible(el) &&
          !el.matches(':disabled,[readonly]') && !el.closest('[hidden],[inert],[aria-disabled=true],[aria-hidden=true],[role=dialog],dialog'));
      return fields.length === 1 ? fields[0] : null;
    ''')


def composer(driver):
    field = _field(driver)
    return None if field == 'dialog' else field


def page_status(driver):
    field = _field(driver)
    return {'ready':False,'reason':'dialog'} if field == 'dialog' else {'ready':bool(field)}


def select_draft(driver, field):
    # A keyboard shortcut is not evidence of a selection: Chrome can type a literal 'a'.
    return driver.execute_script('''
      const el = arguments[0]; el.focus({preventScroll:true});
      if (!el.isConnected || document.activeElement !== el) return false;
      if (el.tagName === 'TEXTAREA') {
        el.setSelectionRange(0,el.value.length);
        return el.selectionStart === 0 && el.selectionEnd === el.value.length;
      }
      const selection = window.getSelection(), range = document.createRange();
      range.selectNodeContents(el); selection.removeAllRanges(); selection.addRange(range);
      if (selection.rangeCount !== 1 || document.activeElement !== el) return false;
      const actual = selection.getRangeAt(0);
      return actual.startContainer === el && actual.startOffset === 0 &&
             actual.endContainer === el && actual.endOffset === el.childNodes.length;
    ''', field) is True


def draft_text(driver, field):
    # innerText puts two line breaks between <p>s; Arena stores just one.
    return driver.execute_script(r'''
      const el = arguments[0];
      if (el.tagName === 'TEXTAREA') return el.value;
      // TipTap decorations are visible DOM, but are not part of the message.
      const editor = el.editor;
      if (editor && !editor.isDestroyed && editor.view?.dom === el && typeof editor.getText === 'function')
        return editor.getText({blockSeparator:'\n'});
      // Chrome can leave the first line as bare text when replacing a draft.
      const nodes = [...el.childNodes], first = nodes.findIndex(n => n.nodeName === 'P');
      if (first < 0 || nodes.slice(0,first).some(n => n.nodeType !== Node.TEXT_NODE) ||
          nodes.slice(first).some(n => n.nodeName !== 'P')) return el.innerText;
      function text(n) {
        if (n.nodeName === 'BR') return n.classList.contains('ProseMirror-trailingBreak') ? '' : '\n';
        if (n.nodeType === Node.TEXT_NODE) return n.data;
        return [...n.childNodes].map(text).join('');
      }
      const prefix = nodes.slice(0,first).map(text).join(''), lines = nodes.slice(first).map(text);
      if (prefix) lines.unshift(prefix);
      return lines.join('\n');
    ''', field)


def mirror_draft(parser, driver, field, text):
    desired = text.replace('\r\n', '\n').replace('\r', '\n')
    # send_keys interprets Tab and WebDriver's private-use characters as commands.
    if any((ord(c) < 32 and c != '\n') or '\ue000' <= c <= '\uf8ff' for c in desired): return False
    current = draft_text(driver, field)
    if current == desired: return True
    common = 0
    while common < min(len(current),len(desired)) and current[common] == desired[common]: common += 1
    back, tail = len(current)-common, desired[common:]
    replace = back > 80
    if replace: tail = desired
    if len(tail) > 512: return False  # A pasted block stays local until explicit Send.
    parser._focus_input_caret_end(driver, field)
    if not driver.execute_script('return document.activeElement === arguments[0]', field): return False
    if replace:
        if not select_draft(driver, field): return False
        field.send_keys(Keys.BACKSPACE)
    elif back: field.send_keys(Keys.BACKSPACE * back)
    if tail: parser._type_text_soft_newlines(field, tail)
    return parser._insert_text_matches(draft_text(driver, field), desired)
