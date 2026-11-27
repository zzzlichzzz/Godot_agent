"""Identify provider-owned launch and conversation URLs for saved browser chats."""
import re
from urllib.parse import urlsplit

_PREFIX = {'qwen':'/c/', 'deepseek':'/a/chat/s/', 'kimi':'/chat/', 'arena':'/c/', 'arena_battle':'/c/'}


def studio_route(url):
    try:
        page=urlsplit(url or '')
        if (page.scheme=='https' and page.netloc=='aistudio.google.com'
                and re.fullmatch(r'/prompts/[A-Za-z0-9_-]+',page.path)):
            # Studio's save flag and launch model aren't conversation identities.
            query = '&'.join(part for part in page.query.split('&') if part != 'save=true' and
                             not (page.path == '/prompts/new_chat' and part.startswith('model=')))
            return page._replace(query=query, fragment='').geturl()
    except ValueError:
        pass
    return None


def is_new_prompt(url):
    return bool(studio_route(url)) and urlsplit(url).path == '/prompts/new_chat'


def matches_saved_origin(site, url):
    page = urlsplit(url)
    return bool(site and page.scheme == 'https' and page.netloc == urlsplit(site['new_chat_url']).netloc)


def route(site, url):
    try:
        if not matches_saved_origin(site, url): return None
        sid = site['id']
        if sid == 'aistudio': return studio_route(url)
        page = urlsplit(url); home = site['new_chat_url']; path = page.path.rstrip('/')
        if path == urlsplit(home).path.rstrip('/'): return home
        if sid == 'kimi' and path == '/chat/provisional': return None
        if sid in _PREFIX and re.fullmatch(_PREFIX[sid] + r'[A-Za-z0-9_-]+', path):
            return page._replace(path=path, query='', fragment='').geturl()
    except (ValueError, TypeError):
        pass
    return None


def permanent(site, url):
    actual = route(site, url)
    return actual if actual and actual != site['new_chat_url'] and not is_new_prompt(actual) else None
