"""C.22 substrate primitives: raw transfers and actual NTFS casing."""
from pathlib import Path

import pytest

from python.substrate.fs.atomic_write import AtomicFileWriter


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("raw", [b"", b"\x00\xff", b"\xef\xbb\xbfBOM\r\n",
                                b"a\r\nb\nc\r", b"a\nb\n", b"a\rb\r"])
def test_move_uses_raw_bytes_and_creates_only_missing_parents(tmp_path, raw):
    (tmp_path / "old.bin").write_bytes(raw)
    (tmp_path / "foreign.uid").write_bytes(b"foreign")
    writer = AtomicFileWriter(tmp_path)
    writer.move("old.bin", "nested/new.bin")
    assert files(tmp_path) == {"nested/new.bin": raw, "foreign.uid": b"foreign"}
    writer.move("nested/new.bin", "old.bin")
    assert files(tmp_path) == {"old.bin": raw, "foreign.uid": b"foreign"}
    assert not list(tmp_path.rglob("*.agent-tmp"))


def test_move_refuses_occupied_destination_without_effect(tmp_path):
    (tmp_path / "old.bin").write_bytes(b"source")
    (tmp_path / "new.bin").write_bytes(b"foreign")
    writer = AtomicFileWriter(tmp_path)
    before = files(tmp_path)
    with pytest.raises(FileExistsError):
        writer.move("old.bin", "new.bin")
    assert files(tmp_path) == before


def test_leaf_case_move_is_direct_and_inverse_restores_actual_name(tmp_path, monkeypatch):
    import os
    (tmp_path / "hero.gd").write_bytes(b"\xef\xbb\xbfraw\r\n")
    writer = AtomicFileWriter(tmp_path)
    replace, calls = os.replace, []

    def observe(src, dst):
        calls.append((Path(src).name, Path(dst).name))
        return replace(src, dst)

    monkeypatch.setattr(os, "replace", observe)
    writer.move("hero.gd", "Hero.gd")
    assert (tmp_path / "Hero.gd").resolve().name == "Hero.gd"
    writer.move("Hero.gd", "hero.gd")
    assert (tmp_path / "hero.gd").resolve().name == "hero.gd"
    assert calls == [("hero.gd", "Hero.gd"), ("Hero.gd", "hero.gd")]


@pytest.mark.parametrize("old,new", [("chars", "Chars"), ("chars/items", "Chars/Items")])
def test_directory_case_changes_actual_segments_and_inverse_bytes(tmp_path, old, new):
    directory = tmp_path / old
    directory.mkdir(parents=True)
    (directory / "hero.gd").write_bytes(b"\xef\xbb\xbfraw\r\n")
    (directory / "orphan.uid").write_bytes(b"historical uid")
    writer = AtomicFileWriter(tmp_path)
    before = files(tmp_path)
    writer.rename_dir_case(old, new)
    assert (tmp_path / new).resolve().relative_to(tmp_path.resolve()).as_posix() == new
    assert files(tmp_path) == {new + "/hero.gd": b"\xef\xbb\xbfraw\r\n",
                               new + "/orphan.uid": b"historical uid"}
    writer.rename_dir_case(new, old)
    assert files(tmp_path) == before
    assert (tmp_path / old).resolve().relative_to(tmp_path.resolve()).as_posix() == old


def test_dir_case_never_becomes_a_content_directory_move(tmp_path):
    (tmp_path / "chars").mkdir()
    (tmp_path / "chars/hero.bin").write_bytes(b"raw")
    writer = AtomicFileWriter(tmp_path)
    before = files(tmp_path)
    with pytest.raises(ValueError):
        writer.rename_dir_case("chars", "elsewhere")
    assert files(tmp_path) == before and not (tmp_path / "elsewhere").exists()


@pytest.mark.parametrize("method", ["move", "rename_dir_case"])
def test_transfer_primitives_reject_parent_escape(tmp_path, method):
    project = tmp_path / "project"
    project.mkdir()
    (project / "item.bin").write_bytes(b"raw")
    before = files(tmp_path)
    with pytest.raises(PermissionError):
        getattr(AtomicFileWriter(project), method)("item.bin", "../outside.bin")
    assert files(tmp_path) == before
