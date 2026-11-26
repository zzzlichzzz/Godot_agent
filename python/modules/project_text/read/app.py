"""Read orchestration: native policy, physical read, then pure slice."""
from python.kernel.errors import AppError
from python.kernel.schema import validate
from .domain import core
from .tools import READ


def call(tool, args, ctx):
    if tool != "read":
        raise AppError("unknown_tool", "модуль project_text.read не владеет инструментом")
    problems = validate(args, READ.args)
    if problems:
        raise AppError("invalid_input", "; ".join(problems))
    selection = {key: args[key] for key in ("start_line", "end_line", "offset") if key in args}
    if "end_line" in selection and selection["end_line"] < selection.get("start_line", 1):
        raise AppError("invalid_input", "end_line must not precede start_line")
    fs = ctx.port("project_text_fs")
    rel = fs.resolve(args["path"], ctx.path_policy)
    if not fs.is_file(rel):
        raise AppError("not_found", "Файл не найден: " + args["path"])
    try:
        text = fs.read_text(rel)
    except FileNotFoundError:
        raise AppError("not_found", "Файл не найден: " + args["path"]) from None
    except OSError:
        raise AppError("denied", "Файл недоступен для чтения: " + args["path"]) from None
    return core.render("res://" + rel, text, args.get("max_chars", 50000), **selection)
