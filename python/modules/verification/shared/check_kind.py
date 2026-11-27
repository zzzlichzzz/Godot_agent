"""ADR-0004 contribution descriptor; no IO, binding or global runtime state."""
import re


class CheckKind:
    """lint(text, path, ctx) -> problems:list[str], auto_fixable:bool.

    Optional checked:bool / unavailable:list[{kind:str, reason:str}].
    The verify owner validates fragments and defaults omitted fields to True/[]
    for legacy gd/tscn contributions; the descriptor shape stays unchanged.
    """
    __slots__ = ('name', 'extensions', 'lint')

    def __init__(self, name, extensions, lint):
        if not isinstance(name, str) or re.fullmatch(r'[a-z][a-z0-9_]*', name) is None:
            raise ValueError('invalid check kind name')
        if not isinstance(extensions, tuple) or not extensions or any(
            not isinstance(ext, str) or re.fullmatch(r'\.[a-z0-9_]+', ext) is None
            for ext in extensions
        ):
            raise ValueError('check extensions must be a nonempty lowercase tuple')
        if not callable(lint):
            raise ValueError('check lint must be callable')
        self.name, self.extensions, self.lint = name, extensions, lint
