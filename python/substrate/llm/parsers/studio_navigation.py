"""Navigation evidence from the active Studio tab; never submit or inspect other tabs."""
import time
from urllib.parse import urlsplit

from .studio_draft import _COMPOSER, is_new_prompt, studio_route
from ..browser.page_origin import matches_saved_origin

_BLANK = _COMPOSER + '''
return location.href === arguments[0] && !!el && !el.value &&
    !document.querySelector('[data-turn-role="User"],[data-turn-role="Model"]');
'''
_NEW_ACTION = '''
const controls = [...document.querySelectorAll('a[href],button,[role="button"]')].filter(el => {
    if (!el.checkVisibility({opacityProperty:true,visibilityProperty:true}) || el.matches(':disabled') ||
        el.closest('[inert],[aria-hidden="true"],[role="dialog"]') || (el.target && el.target !== '_self')) return false;
    const name = (el.getAttribute('aria-label') || el.title || el.innerText || '').trim();
    if (el.tagName === 'A') return el.origin === location.origin && el.pathname === '/prompts/new_chat';
    return /^(new chat|create new chat|start new chat|новый чат|создать чат)$/i.test(name);
});
return controls.length === 1 ? controls[0] : null;
'''
_MATCH = _COMPOSER + r'''
if (!el || location.href !== arguments[0]) return false;
const nodes = [...document.querySelectorAll('[data-turn-role="User"],[data-turn-role="Model"]')];
const rows = arguments[1], norm = s => s.replace(/\s+/g, ' ').trim();
if (nodes.length !== rows.length) return false;
return nodes.every((n,i) => {
    const [role,text] = rows[i];
    if (n.dataset.turnRole !== role) return false;
    return [n, ...n.querySelectorAll('ms-text-chunk,.turn-content')].some(el => {
        let s = el.innerText || '';
        if (role === 'User') s=s.split('\n\n=== CURRENT REQUEST (answer it directly) ===\n').pop();
        else s=s.replace(/\n===DONE===\s*$/, '');
        return norm(s) === norm(text);
    });
});
'''


def navigate(driver, url):
    """Use the selected window, never the last handle. Reload even at new_chat."""
    target = studio_route(url)
    if not target:
        return False
    # Chrome's frontmost tab can differ from WebDriver's selected window.
    driver.switch_to.window(driver.current_window_handle)
    if not is_new_prompt(target) and studio_route(driver.current_url) == target:
        return True
    from selenium.common.exceptions import TimeoutException
    previous = driver.timeouts.page_load
    driver.set_page_load_timeout(10)
    try:
        driver.get(url if is_new_prompt(target) else target)
    except TimeoutException:
        pass  # An SPA can have a working composer before all resources load.
    finally:
        driver.set_page_load_timeout(previous)
    return True  # Caller verifies the actual document and window.


def restore_after_home(driver, window, previous):
    """A broken saved link shouldn't strand the user on Studio's home screen."""
    if not studio_route(previous) or driver.current_window_handle != window:
        return
    landing = urlsplit(driver.current_url)
    if (landing.scheme, landing.netloc, landing.path) == ('https', 'aistudio.google.com', '/'):
        navigate(driver, previous)


def wait_blank(driver, window, target, timeout=8):
    end = time.monotonic() + timeout
    previous = False
    while time.monotonic() < end and driver.current_window_handle == window:
        actual = driver.current_url
        blank = studio_route(actual) == studio_route(target) and driver.execute_script(_BLANK, actual)
        if blank and previous:
            return True
        previous = blank
        time.sleep(.25)
    return False


def open_blank(driver, window, target):
    if wait_blank(driver, window, target):
        return True
    if driver.current_window_handle != window or not matches_saved_origin({'new_chat_url':target}, driver.current_url):
        return False
    # Some Studio sessions restore the previous prompt even on a fresh GET.
    # Use Studio's own New chat action once and check the result again.
    action = driver.execute_script(_NEW_ACTION)
    if action is not None and driver.current_window_handle == window:
        action.click()
        return wait_blank(driver, window, target)
    return False


def matching_open_chat(driver, rec):
    if driver is None or rec.get('transcript_trimmed'):
        return None
    rows = [('User' if r['role'] == 'user' else 'Model', r['text']) for r in rec.get('transcript', ())
            if r.get('role') in ('user', 'agent') and r.get('text')]
    if not rows or rows[0][0] != 'User' or rows[-1][0] != 'Model':
        return None
    window, actual = driver.current_window_handle, driver.current_url
    route = studio_route(actual)
    if route and not is_new_prompt(route) and driver.execute_script(_MATCH, actual, rows):
        if driver.current_window_handle == window and studio_route(driver.current_url) == route:
            return route
    return None
