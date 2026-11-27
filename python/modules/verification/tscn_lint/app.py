"""Strict preflight -> pure scanners -> read facts -> pure finish. No writes."""
import errno

from python.formats import tscn_lint_syntax as fmt
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from python.kernel.schema import validate

from .domain import core
from .read_inputs import gather
from .tools import CHECK


def _path(value, ctx):
    if not value.startswith('res://'):
        raise AppError('invalid_input', 'требуется путь res:// внутри проекта')
    rel = normalize_rel(value[len('res://'):])
    if rel is None:
        raise AppError('denied', 'путь вне проекта')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    return rel


def call(tool, args, ctx):
    if tool != 'check':
        raise AppError('unknown_tool', 'verification.tscn_lint владеет только check')
    if validate(args, CHECK.args):
        raise AppError('invalid_input', 'неверные аргументы check',
                       hint='Нужны path, content; planned_paths — массив res:// путей')
    rel = _path(args['path'], ctx)
    if not fmt.is_scene_path(rel):
        raise AppError('invalid_input', 'check работает только с .tscn/.scn')
    planned = args.get('planned_paths', [])
    for path in planned:
        _path(path, ctx)
    content = args['content']
    try:
        size = len(content.encode('utf-8'))
    except UnicodeEncodeError:
        raise AppError('invalid_input', 'content должен быть корректным UTF-8') from None
    if size > READ_TEXT_MAX_BYTES:
        raise AppError('invalid_input', 'content больше лимита чтения')
    prepared = core.prepare(content)
    if not prepared[2]:
        return core.finish(prepared, content)
    try:
        existing, instances, classes = gather(prepared[0], planned, ctx)
    except FileNotFoundError:
        raise AppError('not_found', 'файл не найден внутри проекта') from None
    except PermissionError:
        raise AppError('denied', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения') from None
        raise AppError('internal', 'ошибка безопасного чтения') from None
    return core.finish(prepared, content, existing, instances, classes, planned)
