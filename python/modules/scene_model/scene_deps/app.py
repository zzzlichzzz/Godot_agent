"""Project IO through fs seams; no local scene/script parsing or writes."""
import errno
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel
from .domain import core
from .settings import PROJECT_SCAN_MAX_BYTES


def _decode(raw):
    return raw.decode('utf-8',errors='replace').replace('\r\n','\n').replace('\r','\n')


def _raw(fs,rel):
    raw=fs.read_raw(rel)
    if len(raw)>READ_TEXT_MAX_BYTES:
        raise OSError(errno.EFBIG,'limit')
    return raw


def _collect(fs,policy):
    gd,scenes={},{}
    try:
        paths=fs.list_files()
    except OSError:
        return gd,scenes
    for rel in paths:
        if not policy.can_read(rel) or not core.is_project_file(rel):
            continue
        try:
            raw=_raw(fs,rel)
        except OSError:
            continue
        if len(raw)<=PROJECT_SCAN_MAX_BYTES:
            (gd if rel.endswith('.gd') else scenes)['res://'+rel]=_decode(raw)
    return gd,scenes


def call(tool,args,ctx):
    if tool!='scene_deps':
        raise AppError('unknown_tool','модуль scene_model.scene_deps не владеет этим инструментом')
    path=str(args.get('path') or '').strip();value=path.removeprefix('res://');rel=normalize_rel(value)
    if rel is None or '://' in value:
        message='Путь вне проекта отклонен: %s'%path if value.startswith('..') else 'путь вне проекта'
        raise AppError('invalid_input',message)
    reason=ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied',reason)
    fs=ctx.port('fs')
    try:
        source=_decode(_raw(fs,rel))
    except FileNotFoundError:
        raise AppError('not_found','Файл не найден: %s'%path) from None
    except PermissionError:
        raise AppError('denied','путь недоступен для безопасного чтения') from None
    except OSError as exc:
        message='файл больше лимита чтения' if exc.errno==errno.EFBIG else 'файл недоступен для чтения'
        raise AppError('invalid_input',message) from None
    if not rel.lower().endswith(('.gd','.tscn','.scn')):
        raise AppError('invalid_input','list_scene работает только со сценами .tscn: %s'%path)
    if rel.lower().endswith('.gd'):
        handlers=core.prepare_script(source)
        gd,scenes=_collect(fs,ctx.path_policy) if handlers else ({},{})
        return core.script_action(source,path,gd,scenes,handlers)
    view=core.prepare_scene(source)
    gd,scenes=_collect(fs,ctx.path_policy) if view[3] else ({},{})
    attached={}
    for node,script_res in view[3]:
        key=core.resource_key(script_res);script_rel=normalize_rel(key.removeprefix('res://')) if key else None
        if script_rel and ctx.path_policy.can_read(script_rel):
            try:
                attached[key]=_decode(_raw(fs,script_rel))
            except OSError:
                pass
    return core.scene_action(source,path,view,gd,scenes,attached)
