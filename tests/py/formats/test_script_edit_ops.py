"""C.20: file-step op разбирается явно, без тихого replace."""
import pytest

from python.kernel.errors import AppError
from python.modules.editing.shared import script_edits


def test_old_script_edit_path_is_unchanged():
    raw = b"a\r\nb\r\n"
    step = {"op": "script_edit", "target": "res://x.py",
            "expected_hash": script_edits.sha256_text("a\nb\n"),
            "payload": {"edits": [{"start": 0, "end": 1,
                                    "replacement": "z"}]}}
    assert script_edits.apply_step(raw, step) == b"z\r\nb\r\n"


def test_create_encodes_declared_text_and_delete_has_no_bytes():
    create = {"op": "create", "target": "res://new.py", "expected_hash": "",
              "payload": {"text": "x\n", "newline": "lf"},
              "compensates": "delete"}
    assert script_edits.apply_step(None, create) == b"x\n"
    delete = {"op": "delete", "target": "res://old.py",
              "expected_hash": script_edits.sha256(b"x\n"), "payload": {}}
    assert script_edits.apply_step(b"x\n", delete) is None


def test_unknown_operation_is_invalid_input():
    with pytest.raises(AppError) as caught:
        script_edits.apply_step(b"x\n", {"op": "mystery",
                                          "target": "res://x.py",
                                          "payload": {}})
    assert caught.value.kind == "invalid_input"
