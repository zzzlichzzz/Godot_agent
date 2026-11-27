"""Validate data/path -> one fresh snapshot -> shared chain -> pure scanner."""
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from python.kernel.schema import validate
from python.modules.engine_kb.shared.inheritance import collect_members, resolve_chain

from .domain import core
from .tools import API_CHECK


def call(tool, args, ctx):
    if tool != 'api_check':
        raise AppError('unknown_tool', 'verification.api_check владеет только api_check')
    if validate(args, API_CHECK.args):
        raise AppError('invalid_input', 'неверные аргументы api_check')
    path = args['path']
    if not path.startswith('res://'):
        raise AppError('invalid_input', 'требуется путь res:// внутри проекта')
    rel = normalize_rel(path[len('res://'):])
    if rel is None:
        raise AppError('denied', 'путь вне проекта')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    content = args['content']
    try:
        size = len(content.encode('utf-8'))
    except UnicodeEncodeError:
        raise AppError('invalid_input', 'content должен быть корректным UTF-8') from None
    if size > READ_TEXT_MAX_BYTES:
        raise AppError('invalid_input', 'content больше лимита чтения')
    classes, _version = ctx.port('api_cache').snapshot()
    chain = resolve_chain(classes, core.base_class(content))
    members = collect_members(classes, chain)
    problems, base, checked, reason = core.check(content, classes, members)
    kinds = {'no_extends': 'source', 'no_cache': 'api_cache', 'base_not_in_cache': 'base_class'}
    return {'path': 'res://' + rel, 'problems': problems, 'checked': checked,
            'base_class': base,
            'unavailable': [{'kind': kinds[reason], 'reason': reason}] if reason else []}
