"""C.21 reads use their port, never the write funnel or shared decoder."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "python/modules/editing/paths_preview"


def test_production_has_no_direct_io_effects_or_normalizing_decoder():
    for path in MODULE.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        parsed = ast.parse(text)
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id in {"open", "eval", "exec"} for n in ast.walk(parsed))
        assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) and
                       any(word in ast.get_source_segment(text, n) for word in
                           ("substrate", "script_edits", "funnel", "journal", "backups", "normalize_newlines"))
                       for n in ast.walk(parsed))


class Outside:
    def is_file(self, rel):
        raise PermissionError("physical realpath escape")


def test_physical_escape_is_invalid_input_without_absolute_path():
    from python.modules.editing.paths_preview.app import call
    ctx = SimpleNamespace(path_policy=PathPolicy("project"), port=lambda name: Outside())
    with pytest.raises(AppError) as caught:
        call("paths_preview", {"old_path": "res://linked/a.gd", "new_path": "res://next.gd"}, ctx)
    assert caught.value.kind == "invalid_input"
    assert caught.value.message == "Путь вне проекта отклонен: res://linked/a.gd"


def test_unknown_tool_does_not_touch_any_port():
    from python.modules.editing.paths_preview.app import call
    def forbidden(name):
        raise AssertionError("unexpected port")
    with pytest.raises(AppError) as caught:
        call("find_file_references", {}, SimpleNamespace(port=forbidden))
    assert caught.value.kind == "unknown_tool"


def test_call_requests_only_read_port_and_never_effect_ports():
    from python.modules.editing.paths_preview.app import call
    class Files:
        def is_file(self, rel):
            return rel == "a.gd"
        def exists(self, rel):
            return rel == "a.gd"
        def list_files(self):
            return ["a.gd"]
        def read_raw(self, rel):
            assert rel == "a.gd"
            return b"# donor\r\n# lone\r"
    def port(name):
        assert name == "paths_fs", "effect or shared fs port requested"
        return Files()
    result = call("paths_preview", {"old_path": "res://a.gd", "new_path": "res://b.gd"},
                  SimpleNamespace(port=port, path_policy=PathPolicy("project")))
    assert result["source_text"] == "# donor\r\n# lone\r" and result["file_count"] == 1
