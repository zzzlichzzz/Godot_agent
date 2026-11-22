"""Read orchestration only: path policy -> declared fs port -> pure lint domain."""
import errno

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel

from .domain import core


def call(tool, args, ctx):
    if tool != 'gd_lint':
        raise AppError('unknown_tool', 'модуль verification.gd_lint не владеет этим инструментом')
    path = str(args.get('path') or '').strip()
    value = path.removeprefix('res://')
    rel = normalize_rel(value)
    if rel is None or '://' in value:
        raise AppError('invalid_input', 'путь вне проекта',
                       hint='Укажите относительный путь или res://scripts/player.gd')
    if not rel.lower().endswith('.gd'):
        raise AppError('invalid_input', 'gd_lint работает только с .gd')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    try:
        raw = ctx.port('fs').read_raw(rel)
    except FileNotFoundError:
        raise AppError('not_found', 'файл не найден: res://%s' % rel) from None
    except PermissionError:
        raise AppError('invalid_input', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения',
                           hint='Максимальный размер указан в limits.max_file_bytes') from None
        raise
    return core.check(raw)
