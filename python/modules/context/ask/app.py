"""Public ask orchestration: validate through the pure domain, call the port."""
from python.kernel.errors import AppError

from .domain import core


def call(tool, args, ctx):
    if tool != "ask":
        raise AppError("unknown_tool", "context.ask отвечает только за ask")
    request = core.build_request(args, ctx.path_policy)
    return ctx.port("librarian").answer(**request)
