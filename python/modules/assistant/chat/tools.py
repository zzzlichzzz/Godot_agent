"""D71/D73 source of truth for public chat; generated contract is derived."""
from python.kernel.tool_spec import ToolSpec
from .domain.core import MAX_TURNS, MAX_TEXT, MAX_REPLY

CHAT = ToolSpec(
    name='chat', description='Диалог read-only агента: модель, чтение проекта, native judge и ограниченные ходы.',
    args={'type': 'object', 'properties': {
        'text': {'type': 'string', 'minLength': 1, 'maxLength': MAX_TEXT},
        'max_turns': {'type': 'integer', 'minimum': 1, 'maximum': MAX_TURNS, 'default': MAX_TURNS},
        'budget_chars': {'type': 'integer', 'minimum': 1, 'maximum': MAX_TEXT, 'default': MAX_TEXT}},
        'required': ['text'], 'additionalProperties': False},
    result={'type': 'object', 'properties': {
        'text': {'type': 'string'}, 'turns_used': {'type': 'integer'},
        'actions_executed': {'type': 'array', 'items': {'type': 'string'}},
        'judge_summary': {'type': 'object'}},
        'required': ['text', 'turns_used', 'actions_executed', 'judge_summary'],
        'additionalProperties': False},
    effects='read', idempotent=False, errors=('invalid_input', 'not_found', 'denied'),
    availability='*', cost='heavy', limits={'max_turns': MAX_TURNS, 'text_chars': MAX_TEXT,
        'budget_chars': MAX_TEXT, 'reply_chars': MAX_REPLY, 'read_files': 5, 'read_file_chars': 30000})
TOOLS = (CHAT,)
