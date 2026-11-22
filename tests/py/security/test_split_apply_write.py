"""SEC-21: split_py prepares data; only the shared funnel mutates files."""
import ast
from pathlib import Path

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.editing.shared import funnel, script_edits

ROOT = Path(__file__).resolve().parents[3]
SPLIT = ROOT / "python/modules/editing/split_py"
FORBIDDEN = {"open", "remove", "unlink", "rmtree", "write_raw",
             "write_text", "write_bytes", "create", "delete"}


class _Ctx:
    path_policy = PathPolicy("")


def test_split_py_has_no_direct_project_write_calls():
    for path in sorted(SPLIT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                assert name not in FORBIDDEN, "%s calls %s" % (path, name)


def test_protected_and_escape_targets_are_denied():
    for rel in ("../evil.py", "plugin.cfg", "addons", "addons/demo/new.py"):
        try:
            funnel.guard_path(_Ctx(), rel)
        except AppError as exc:
            assert exc.kind == "denied"
        else:
            raise AssertionError("write target was not denied: %s" % rel)


def test_unknown_file_operation_never_falls_back_to_edit():
    try:
        script_edits.apply_step(b"safe\n", {"op": "replace_anyway",
            "target": "res://safe.py", "payload": {"edits": []}})
    except AppError as exc:
        assert exc.kind == "invalid_input"
    else:
        raise AssertionError("unknown op silently used script_edit")
