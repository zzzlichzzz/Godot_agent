"""kernel/ids.py - plan_id, entry_id, session_id: генерация и разбор.

Только stdlib: идентификатор — это строка, а не повод тянуть зависимость.
"""

import uuid

PREFIXES = ("plan", "entry", "session", "call")


def new_id(prefix="call"):
    """Короткий уникальный идентификатор с говорящим префиксом."""
    if prefix not in PREFIXES:
        raise ValueError("неизвестный префикс id: %r" % (prefix,))
    return "%s_%s" % (prefix, uuid.uuid4().hex[:12])


def parse_id(value):
    """`(префикс, остаток)`; None, если строка не похожа на id агента."""
    text = str(value or "")
    prefix, _, rest = text.partition("_")
    if prefix not in PREFIXES or not rest:
        return None
    return prefix, rest

