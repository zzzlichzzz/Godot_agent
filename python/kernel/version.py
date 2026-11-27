"""Runtime contract versions. Manifest ranges: *, exact or caret, up to three components."""
import re

KERNEL_API = '1.0.0'
GODOT_BASELINE = '4.6.0'


def _parts(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,2}', value):
        raise ValueError('invalid version: %r' % (value,))
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts))


def compatible(requirement, version):
    actual = _parts(version)
    if requirement == '*':
        return True
    if not requirement.startswith('^'):
        return actual == _parts(requirement)
    raw = requirement[1:]
    low = _parts(raw)
    pivot = next((i for i, n in enumerate(low) if n), raw.count('.'))
    high = low[:pivot] + (low[pivot] + 1,) + (0,) * (2 - pivot)
    return low <= actual < high
