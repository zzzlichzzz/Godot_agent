"""D13 red pins: unchanged C.21 default, proven NTFS alias, no zero-step WAL."""
import os

import pytest

from python.kernel.errors import AppError
from python.modules.editing import paths_preview
from python.modules.editing.file_refactor import app
from tools.probe import file_refactor_context


def test_external_relative_false_keeps_literals_but_rewrites_exact_res():
    text = 'const A=load("src/a.gd")\r\nconst B=load("res://src/a.gd")\n'
    docs = {"res://src/a.gd": {"text": "extends Node\n", "bom": False},
            "res://view.gd": {"text": text, "bom": False}}
    args = (docs, "res://src", "res://dest", {"src/a.gd"}, (),
            {"res://src/a.gd": "res://dest/a.gd"})
    legacy = paths_preview.project_directory(*args)
    assert legacy == paths_preview.project_directory(*args, external_relative=True)
    rows, after = paths_preview.project_directory(*args, external_relative=False)
    assert after["res://view.gd"] == text.replace('"res://src/a.gd"', '"res://dest/a.gd"')
    row = next(row for row in rows if row["path"] == "res://view.gd")
    assert row["occurrences"] == row["exact_matches"] == 1 and row["rel_matches"] == []
    assert 'load("res://dest/a.gd")' in legacy[1]["res://view.gd"]


def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return root, file_refactor_context(root, tmp_path / "state")


@pytest.mark.parametrize("bad", [None, "sha", "casing", "realpath"])
def test_ntfs_completed_alias_is_proven_or_conflict(tmp_path, monkeypatch, bad):
    root, (_agent, ctx, ports) = project(tmp_path)
    (root / "hero.gd").write_bytes(b"extends Node\r\n")
    os.rename(root / "hero.gd", root / "Hero.gd")
    writer = ports["writer"]
    assert writer.same_file("hero.gd", "Hero.gd")
    assert writer.actual_rel("hero.gd") == "Hero.gd"
    if bad == "sha":
        read = writer.read_raw
        monkeypatch.setattr(writer, "read_raw", lambda rel: b"foreign\r\n" if rel == "hero.gd" else read(rel))
    elif bad in ("casing", "realpath"):
        actual = writer.actual_rel
        monkeypatch.setattr(writer, "actual_rel", lambda rel: ("hero.gd" if bad == "casing" else "else.gd") if rel == "hero.gd" else actual(rel))
    args = {"old_path": "res://hero.gd", "new_path": "res://Hero.gd"}
    if bad:
        with pytest.raises(AppError) as error:
            app.sync(args, ctx)
        assert error.value.kind == "conflict"
    else:
        report = app.sync(args, ctx)
        assert report["anchor_already_completed"] is True
        assert report["patches"] == report["moved"] == [] and report["plan_id"] is None
        assert report["entry_id"] is None
    assert ports["journal"].plan_ids() == []
    assert (root / "Hero.gd").read_bytes() == b"extends Node\r\n"


@pytest.mark.parametrize("same", [False, True])
def test_empty_external_sync_never_creates_plan_or_wal(tmp_path, same):
    root, (_agent, ctx, ports) = project(tmp_path)
    (root / "dest").mkdir()
    report = app.sync({"old_path": "res://dest" if same else "res://src",
                       "new_path": "res://dest", "is_directory": True}, ctx)
    assert report["patches"] == report["moved"] == [] and report["plan_id"] is None
    assert ports["journal"].plan_ids() == []
    assert (root / "dest").is_dir() and not (root / "src").exists()
    assert ports["lock"].acquire()
    ports["lock"].release()


def test_sync_holds_one_lock_from_scan_until_committed(tmp_path, monkeypatch):
    root, (_agent, ctx, ports) = project(tmp_path)
    (root / "dest.gd").write_bytes(b"extends Node\n")
    (root / "view.gd").write_bytes(b'const A=load("res://src.gd")\n')
    lock = ports["lock"]
    events = []
    for owner, name in ((lock, "acquire"), (lock, "release"), (ports["paths_fs"], "list_files"),
                        (ports["journal"], "write_prepared"), (ports["journal"], "append")):
        original = getattr(owner, name)
        def observe(*args, _original=original, _name=name, **kwargs):
            events.append((_name, args[1].get("state") if _name == "append" else None))
            if _name in ("list_files", "write_prepared", "append"):
                assert os.path.exists(lock.path)
            return _original(*args, **kwargs)
        monkeypatch.setattr(owner, name, observe)
    report = app.sync({"old_path": "res://src.gd", "new_path": "res://dest.gd"}, ctx)
    assert events[0][0] == "acquire" and events[-1][0] == "release"
    assert [name for name, _state in events].count("acquire") == 1
    assert events[-2] == ("append", "COMMITTED")
    assert report["plan_id"] and report["entry_id"].startswith(report["plan_id"] + "#")


def test_completed_alias_with_patches_has_no_anchor_receipt_and_keeps_casing(tmp_path):
    root, (agent, ctx, ports) = project(tmp_path)
    (root / "Hero.gd").write_bytes(b"extends Node\n")
    (root / "view.gd").write_bytes(b'const A=load("res://hero.gd")\r\n')
    report = app.sync({"old_path": "res://hero.gd", "new_path": "res://Hero.gd"}, ctx)
    assert report["anchor_already_completed"] is True
    steps = ports["journal"].read(report["plan_id"])[0]["plan"]["steps"]
    assert [(s["op"], s["target"]) for s in steps] == [("replace_raw", "res://view.gd")]
    assert agent.call("write_rollback", {"entry_id": report["entry_id"]})["ok"]
    assert (root / "Hero.gd").resolve().name == "Hero.gd"
    assert (root / "view.gd").read_bytes() == b'const A=load("res://hero.gd")\r\n'


def test_p1_unplanned_reference_and_foreign_uid_are_untouched(tmp_path):
    root, (_agent, ctx, ports) = project(tmp_path)
    (root / "old.gd").write_bytes(b"extends Node\r\n")
    (root / "view.gd").write_bytes(b'const A=load("res://old.gd")\n')
    (root / "foreign.gd.uid").write_bytes(b"uid://foreign\r\n")
    prepared = app.prepare({"old_path": "res://old.gd", "new_path": "res://new.gd",
                            "update_references": False}, ctx)
    plan = ports["journal"].read(prepared["plan_id"])[0]["plan"]
    assert "res://view.gd" not in plan["expected"] and "res://foreign.gd.uid" not in plan["expected"]
    app.apply(prepared, ctx)
    assert (root / "view.gd").read_bytes() == b'const A=load("res://old.gd")\n'
    assert (root / "foreign.gd.uid").read_bytes() == b"uid://foreign\r\n"
    assert not (root / "new.gd.uid").exists()


def test_parent_case_requires_rename_for_each_changed_segment(tmp_path, monkeypatch):
    """D9 pins the primitive, not an OS-dependent equivalence with replace."""
    from pathlib import Path
    from python.substrate.fs.atomic_write import AtomicFileWriter
    directory = tmp_path / "chars/items"
    directory.mkdir(parents=True)
    raw = b"\xef\xbb\xbfraw\r\n\x00\xff\rlf\n"
    (directory / "raw.bin").write_bytes(raw)
    rename, calls = os.rename, []

    def observe(source, destination):
        calls.append((Path(source).relative_to(tmp_path).as_posix(),
                      Path(destination).relative_to(tmp_path).as_posix()))
        return rename(source, destination)

    monkeypatch.setattr(os, "rename", observe)
    writer = AtomicFileWriter(tmp_path)
    writer.rename_dir_case("chars/items", "Chars/Items")
    assert writer.actual_rel("Chars/Items") == "Chars/Items"
    assert (tmp_path / "Chars/Items/raw.bin").read_bytes() == raw
    assert calls == [("chars/items", "chars/Items"), ("chars", "Chars")]
    writer.rename_dir_case("Chars/Items", "chars/items")
    assert writer.actual_rel("chars/items") == "chars/items"
    assert (tmp_path / "chars/items/raw.bin").read_bytes() == raw
    assert calls[2:] == [("Chars/Items", "Chars/items"), ("Chars", "chars")]
