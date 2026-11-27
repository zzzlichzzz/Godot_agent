"""C.11 by specification: validation -> one fresh read-only snapshot -> domain."""
from python.kernel.errors import AppError
from python.kernel.schema import validate

from .domain import core
from .tools import API


def call(tool, args, ctx):
    if tool != 'api':
        raise AppError('unknown_tool', 'engine_kb.class_api владеет только api')
    problems = validate(args, API.args)
    if problems:
        raise AppError('invalid_input', '; '.join(problems))
    class_name = args['class_name'].strip()
    if not class_name:
        raise AppError('invalid_input', 'class_name пуст после удаления пробелов')
    classes, version = ctx.port('api_cache').snapshot()
    cache_version = version if classes else ''
    result = core.assemble(class_name, classes, cache_version)
    if not classes:
        result['unavailable'] = [{'kind': 'api_cache', 'reason': 'no_cache'}]
    return result
