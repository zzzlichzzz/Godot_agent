"""SEC-24: pointer exclusion before traversal; exact old list_files is frozen."""
import os
import subprocess

import pytest


def test_disk_and_memory_preserve_empty_directories(tmp_path):
    from python.substrate.fs.disk_fs import DiskFileSystem
    from python.substrate.fs.memory_fs import MemoryFileSystem
    (tmp_path / "empty").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.txt").write_bytes(b"a")
    memory = MemoryFileSystem({"src/a.txt": "a"})
    expected = [{"path": "empty", "type": "dir"}, {"path": "src", "type": "dir"},
                {"path": "src/a.txt", "type": "file"}]
    assert DiskFileSystem(tmp_path).list_entries() == memory.list_entries(directories=("empty",)) == expected
    assert memory.list_files() == DiskFileSystem(tmp_path).list_files() == ["src/a.txt"]


def test_real_junctions_are_neither_yielded_nor_followed(tmp_path):
    from python.substrate.fs.disk_fs import DiskFileSystem
    root = tmp_path / "project"
    root.mkdir()
    targets = [tmp_path / "outside", root / "safe", root / "addons/vendor", root / "addons/agent"]
    for index, target in enumerate(targets):
        target.mkdir(parents=True)
        (target / "a.txt").write_bytes(b"secret")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(root / ("alias" + str(index))), str(target)],
                              capture_output=True, shell=False)
        assert done.returncode == 0, done.stderr
    entries = DiskFileSystem(root).list_entries()
    assert entries and not any(row["path"].startswith("alias") for row in entries)
    from tools.probe import project_text_client
    answer = project_text_client(root, {}, agent_dir=root / "addons/agent", state_dir=tmp_path / "state")
    assert answer["ok"] and "alias" not in repr(answer["result"])
    for index in (0, 2, 3):
        denied = project_text_client(root, {"path": "res://alias%d/a.txt" % index}, "read",
                                     agent_dir=root / "addons/agent", state_dir=tmp_path / "state")
        assert not denied["ok"] and denied["kind"] == "denied"
    safe = project_text_client(root, {"path": "res://alias1/a.txt"}, "read",
                               agent_dir=root / "addons/agent", state_dir=tmp_path / "state")
    assert safe["ok"] and safe["result"]["path"] == "res://safe/a.txt"
    assert (tmp_path / "outside/a.txt").read_bytes() == b"secret"


@pytest.mark.parametrize("directory", [False, True])
def test_real_symlink_type_is_checked_before_traversal(tmp_path, directory):
    from python.substrate.fs.disk_fs import DiskFileSystem
    root, target = tmp_path / "project", tmp_path / "target"
    root.mkdir()
    if directory:
        target.mkdir()
        (target / "a.txt").write_bytes(b"secret")
    else:
        target.write_bytes(b"secret")
    try:
        os.symlink(target, root / "alias", target_is_directory=directory)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("symlink unsupported: WinError 1314")
        raise
    assert DiskFileSystem(root).list_entries() == []
