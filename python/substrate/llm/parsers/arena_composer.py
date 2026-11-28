"""Locate the chat editor, never a search field or a hidden fallback textarea."""


def composer(driver):
    return driver.execute_script('''
      const fields = [...document.querySelectorAll('form div.tiptap.ProseMirror[contenteditable="true"],textarea[name="message"]')]
        .filter(el => el.checkVisibility({opacityProperty:true,visibilityProperty:true}) &&
          !el.matches(':disabled,[readonly]') && !el.closest('[hidden],[inert],[aria-disabled=true],[aria-hidden=true],[role=dialog],dialog'));
      return fields.length === 1 ? fields[0] : null;
    ''')


def draft_text(driver, field):
    # innerText puts two line breaks between <p>s; Arena stores just one.
    return driver.execute_script(r'''
      const el = arguments[0];
      if (el.tagName === 'TEXTAREA') return el.value;
      if (!el.children.length || ![...el.childNodes].every(n => n.nodeName === 'P')) return el.innerText;
      function text(n) {
        if (n.nodeName === 'BR') return n.classList.contains('ProseMirror-trailingBreak') ? '' : '\n';
        if (n.nodeType === Node.TEXT_NODE) return n.data;
        return [...n.childNodes].map(text).join('');
      }
      return [...el.children].map(text).join('\n');
    ''', field)
