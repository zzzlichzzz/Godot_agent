"""Legacy scene_deps facts, not a new grammar or a consumer-local parser.

Col0/static/newline/Unicode/comment/literal quirks are deliberate. Native capture:
scene_deps.py:69-70,175-176,211-224,237-241, ba0535d4 (C.5 manifest).
"""
import re

_HANDLER_RE=re.compile(r'^(?:static\s+)?func\s+(_on_\w+)\s*\(',re.M)
_CUSTOM_SIGNAL_RE=re.compile(r'^\s*signal\s+(\w+)',re.M)


def handlers(script_text):
    return list(dict.fromkeys(_HANDLER_RE.findall(script_text or '')))


def custom_signals(script_text):
    return set(_CUSTOM_SIGNAL_RE.findall(script_text or ''))


def method_connected(script_text,method):
    """Literal string OR word on a connect(/Callable( line, including comments."""
    q1,q2='"%s"'%method,"'%s'"%method
    word=re.compile(r'\b%s\b'%re.escape(method))
    if q1 in script_text or q2 in script_text:
        return True
    return any(('connect(' in line or 'Callable(' in line) and word.search(line)
               for line in script_text.splitlines())
