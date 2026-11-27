"""Request -> validation -> read-only snapshot -> pure projection, without WAL."""
from python.kernel.errors import AppError

from . import ports
from .domain import core


def call(tool, args, ctx):
    if tool != "paths_preview":
        raise AppError("unknown_tool", "модуль editing.paths_preview не владеет %r" % tool)
    old, new = core.request(args)
    fs = ctx.port("paths_fs")
    source_file, source_exists = ports.metadata(fs, old)
    _target_file, target_exists = ports.metadata(fs, new)
    is_directory = core.validate(old, new, source_file, source_exists, target_exists, ctx.path_policy)
    documents, existing, unsafe = ports.read_project(fs, ctx.path_policy, old, is_directory)
    return core.preview(old, new, is_directory, documents, existing, unsafe)
