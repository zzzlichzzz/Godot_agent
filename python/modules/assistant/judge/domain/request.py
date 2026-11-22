"""No IO/import side effects; flags belong to the caller's PathPolicy."""
from python.kernel.errors import AppError

MAX_TEXT = 200000


def request(args, policy):
    if not isinstance(args, dict) or set(args) != {'full_text'}:
        raise AppError('invalid_input', 'ожидается только full_text')
    text = args['full_text']
    if not isinstance(text, str) or not (1 <= len(text) <= MAX_TEXT) or '\x00' in text:
        raise AppError('invalid_input', 'full_text должен содержать 1..200000 символов без NUL')
    return text, bool(policy.allow_addons), bool(policy.allow_self_edit)
