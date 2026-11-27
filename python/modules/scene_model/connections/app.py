"""PathPolicy -> raw fs port -> pure reference-view projection."""
import errno
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from .domain import core


def call(tool,args,ctx):
    if tool!='connections':
        raise AppError('unknown_tool','модуль scene_model.connections не владеет этим инструментом')
    path=str(args.get('path') or '').strip();value=path.removeprefix('res://')
    rel=normalize_rel(value)
    if rel is None or '://' in value:
        message='Путь вне проекта отклонен: %s'%path if value.startswith('..') else 'путь вне проекта'
        raise AppError('invalid_input',message)
    reason=ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied',reason)
    try:
        raw=ctx.port('fs').read_raw(rel)
        if len(raw)>READ_TEXT_MAX_BYTES:
            raise OSError(errno.EFBIG,'limit')
    except FileNotFoundError:
        raise AppError('not_found','Файл не найден: %s'%path) from None
    except PermissionError:
        raise AppError('denied','путь недоступен для безопасного чтения') from None
    except OSError as exc:
        message='файл больше лимита чтения' if exc.errno==errno.EFBIG else 'файл недоступен для чтения'
        raise AppError('invalid_input',message) from None
    if not rel.lower().endswith(('.tscn','.scn')):
        raise AppError('invalid_input','list_scene работает только со сценами .tscn: %s'%path)
    try:
        return core.describe(raw)
    except ValueError as exc:
        raise AppError('invalid_input',str(exc)) from None
