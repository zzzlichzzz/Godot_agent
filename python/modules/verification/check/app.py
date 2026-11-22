"""C.9 orchestration: preflight -> single source read -> registry checks -> result."""
import errno
import json

from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from python.kernel.schema import validate
from python.modules.verification.shared.source_text import decode_source

from .domain import core
from .tools import VERIFY


def call(tool, args, ctx):
    if tool != 'verify':
        raise AppError('unknown_tool', 'verification.check владеет только verify')
    if validate(args, VERIFY.args):
        raise AppError('invalid_input', 'неверные аргументы verify',
                       hint='Нужен path; допустимые kinds: gd, tscn, py, json, cfg, api, headless')
    if not args['path'].startswith('res://'):
        raise AppError('invalid_input', 'требуется путь res:// внутри проекта')
    rel = normalize_rel(args['path'][len('res://'):])
    if rel is None:
        raise AppError('denied', 'путь вне проекта')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    path, requested = 'res://' + rel, args.get('kinds')
    ext = core.extension(path)
    try:
        fs = ctx.port('fs')
        if not fs.is_file(rel):
            raise AppError('not_found', 'файл не найден внутри проекта')
        raw = fs.read_raw(rel)
        if len(raw) > READ_TEXT_MAX_BYTES:
            raise AppError('invalid_input', 'файл больше лимита чтения')
        text = decode_source(raw)
        contributions = ctx.registry.contributions('verify')
        selected = core.select(ext, requested, contributions, core.builtins(json.loads))
        reports = [(c.name, c.lint(text, path, ctx)) for c in selected]
    except FileNotFoundError:
        raise AppError('not_found', 'файл не найден внутри проекта') from None
    except PermissionError:
        raise AppError('denied', 'путь недоступен для безопасного чтения') from None
    except OSError as exc:
        if exc.errno == errno.EFBIG:
            raise AppError('invalid_input', 'файл больше лимита чтения') from None
        raise AppError('internal', 'ошибка безопасного чтения') from None
    return core.assemble(path, ext, reports, requested)
