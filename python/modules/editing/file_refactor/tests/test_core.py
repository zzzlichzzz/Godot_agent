"""C.22 pure request/manifest pins, before implementation."""
import importlib

import pytest

from python.kernel.errors import AppError
from python.modules.editing.file_refactor.domain import core


@pytest.mark.parametrize("old,new,expected", [
    ("res://a.gd", "res://b.gd", ("res://a.gd", "res://b.gd")),
    (" res://a.gd/ ", "res://b.gd", ("res://a.gd", "res://b.gd")),
    ("res://dir\\a.gd", "res://dir/b.gd", ("res://dir/a.gd", "res://dir/b.gd")),
])
def test_request_normalizes(old, new, expected):
    assert core.request({"old_path": old, "new_path": new})[:2] == expected


@pytest.mark.parametrize("old,new,message", [
    ("a.gd", "b.gd", "Путь должен начинаться с res://: a.gd"),
    ("res://a.gd", "b.gd", "Путь должен начинаться с res://: b.gd"),
    ("res://./a.gd", "res://b.gd", "Некорректный путь: res://./a.gd"),
    ("res://a//x.gd", "res://b.gd", "Некорректный путь: res://a//x.gd"),
    ("res://../a.gd", "res://b.gd", "Некорректный путь: res://../a.gd"),
    ("res://missing.gd", "res://missing.gd", "Новый путь совпадает со старым: res://missing.gd"),
])
def test_refusal_order_and_messages(old, new, message):
    with pytest.raises(AppError) as error:
        core.request({"old_path": old, "new_path": new})
    assert str(error.value) == message


def test_manifest_is_internal_and_declares_read_seam_dependency():
    module = importlib.import_module("python.modules.editing.file_refactor.module")
    spec = module.MODULE
    assert spec.provides_tools == ()
    assert "editing.paths_preview" in spec.requires
    assert spec.internal_services == ("file_refactor",)
    assert {"prepare", "apply", "sync"} <= set(spec.entrypoints)
