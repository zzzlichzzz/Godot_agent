"""Thin read-only scenario; no substrate imports, writes or registration."""
from .domain.request import request


def call(tool, args, ctx):
    text, addons, self_edit = request(args, ctx.path_policy)
    return ctx.port('librarian').judge(text, allow_addons=addons, allow_self_edit=self_edit)
