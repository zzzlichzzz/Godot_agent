"""Read-port orchestration only; path policy is kernel, syntax is formats."""
import errno

from python.formats import tscn_lint_syntax as fmt
from python.kernel.errors import AppError
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel


def _rel(path, ctx):
    rel = normalize_rel(path[len('res://'):])
    if rel is None:
        raise AppError('denied', 'путь ресурса вне проекта')
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError('denied', reason)
    return rel


def gather(text, planned_paths, ctx):
    fs = ctx.port('fs')
    existing, instances = set(), {}
    planned = {p.replace('res://', '').replace('\\', '/').strip('/').lower()
               for p in planned_paths}
    for token in fmt.ext_finditer(text):
        attrs = fmt.attrs(token.group(1))
        path = attrs.get('path')
        if not isinstance(path, str) or not path.startswith('res://'):
            continue
        raw_rel = path[len('res://'):]
        rel = _rel(path, ctx)
        key = raw_rel.replace('\\', '/').strip('/')
        if key.lower() not in planned and fs.is_file(rel):
            existing.add(key)
        if fmt.is_scene_path(path) and raw_rel not in instances:
            try:
                raw = fs.read_raw(rel)
            except (FileNotFoundError, PermissionError):
                instances[raw_rel] = None
            else:
                if len(raw) > READ_TEXT_MAX_BYTES:
                    raise OSError(errno.EFBIG, 'файл больше лимита чтения')
                # Old io.open(... UTF-8/errors=replace) used universal newlines.
                instances[raw_rel] = raw.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')
    classes = ctx.port('api_cache').classes()
    return existing, instances, classes
