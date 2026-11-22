"""Plan-only IO composition through the two consumer-owned read ports."""
from python.kernel.errors import AppError

from .domain import core, engine, text
from .ports import ApiCache, FileSystem


def call(fs: FileSystem, ctx, prefix, donor, raw, inventory, groups, target):
    groups = core.plan_groups(donor, inventory, groups, target)
    cache: ApiCache = ctx.port('api_cache')
    classes, _version = cache.snapshot()
    methods, props = engine.api(classes, inventory['extends'] or 'Control')
    for _module, module_rel, _const, _names in core.targets(donor, inventory, groups):
        if fs.exists(prefix + module_rel):
            raise AppError('invalid_input', 'целевой модуль уже существует: %s' % module_rel)
    return core.plan(donor, text.decode(raw), inventory, methods, props, groups, target,
                     newline=text.file_newline(raw))
