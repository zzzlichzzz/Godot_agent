"""Pure C.20 confirmation and write-plan projection for a public split plan."""
import hashlib

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.kernel.write_plan import Step

from . import core


def request(args):
    """Validate the accepted public plan before any donor IO."""
    path = args["path"]
    if not path.startswith("res://"):
        raise AppError("invalid_input", "укажите непустой path в формате res://…py")
    rel = normalize_rel(path[6:])
    if rel is None:
        raise AppError("denied", "путь вне проекта")
    if not rel.lower().endswith(".py"):
        raise AppError("invalid_input", "пила работает только с .py: %s" % rel)
    public = args["plan"]
    if public["errors"]:
        raise AppError("invalid_input", "план не готов к применению: %s"
                       % "; ".join(public["errors"]))
    return rel, public


def groups_of(public):
    """Rebuild explicit native groups from their accepted public projection."""
    if public["auto_groups"]:
        return None
    return [{"module": item["rel"].rsplit("/", 1)[-1][:-3],
             "symbols": list(item["names"])} for item in public["modules"]]


def confirm(public, prepared, donor):
    """Pin regeneration, all compile checks and donor identity before effects."""
    if public["donor"] != donor or public["facade"]["rel"] != donor:
        raise AppError("invalid_input", "path не совпадает с донором плана")
    if prepared["errors"]:
        raise AppError("invalid_input", "план не готов к применению: %s"
                       % "; ".join(prepared["errors"]))
    _compile_all(prepared)
    if core.assemble_plan(prepared) != public:
        raise AppError("stale_plan", "план split_plan больше не совпадает с проектом",
                       hint="Постройте split_plan заново")


def donor_matches(source, public):
    return hashlib.sha256(source.encode("utf-8")).hexdigest() == public["donor_sha256"]


def steps(prepared, raw, target_prefix):
    """Create modules first, then replace donor while preserving donor style."""
    result = []
    for module in prepared["modules"]:
        result.append(Step("create", "res://" + target_prefix + module["rel"],
                           {"text": module["text"], "newline": "lf"}, "", "delete"))
    from python.modules.editing.shared import script_edits
    text, newline, _bom = script_edits.decode(raw)
    donor = "res://" + target_prefix + prepared["donor"]
    edit = {"start": 0, "end": len(text),
            "replacement": prepared["facade"]["text"]}
    result.append(Step("script_edit", donor, {"edits": [edit], "newline": newline},
                       script_edits.sha256_text(text)))
    return tuple(result)


def result(prepared, receipts):
    return {"donor": prepared["donor"],
            "written": [item["rel"] for item in prepared["modules"]],
            "moved": list(prepared["moved_names"]),
            "facade_lines": prepared["facade"]["lines"],
            "receipts": list(receipts)}


def _compile_all(prepared):
    for module in prepared["modules"]:
        try:
            compile(module["text"], module["rel"], "exec")
        except (SyntaxError, ValueError) as exc:
            raise AppError("invalid_input", "%s: текст модуля не компилируется: %s"
                           % (module["rel"], exc)) from None
    facade = prepared["facade"]
    try:
        compile(facade["text"], facade["rel"], "exec")
    except (SyntaxError, ValueError) as exc:
        raise AppError("invalid_input", "%s: текст фасада не компилируется: %s"
                       % (facade["rel"], exc)) from None
