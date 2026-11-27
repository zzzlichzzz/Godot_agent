"""C.20: одинаковые file-операции memory/disk портов."""
from pathlib import Path

import pytest

from python.substrate.fs.disk_fs import DiskFileSystem
from python.substrate.fs.memory_fs import MemoryFileSystem


@pytest.mark.parametrize("factory", [
    lambda tmp: MemoryFileSystem({"old.py": "old\n"}),
    lambda tmp: DiskFileSystem(_disk(tmp)),
])
def test_write_create_delete_and_absence(factory, tmp_path):
    fs = factory(tmp_path)
    fs.write_text("old.py", "changed\n")
    assert fs.read_text("old.py") == "changed\n"
    fs.create("new.py", "new\n")
    assert fs.read_text("new.py") == "new\n"
    with pytest.raises(FileExistsError):
        fs.create("new.py", "lost\n")
    fs.delete("new.py")
    assert not fs.exists("new.py")
    with pytest.raises(FileNotFoundError):
        fs.delete("new.py")


def test_disk_delete_rejects_directory(tmp_path):
    root = Path(_disk(tmp_path))
    (root / "folder").mkdir()
    fs = DiskFileSystem(root)
    with pytest.raises(IsADirectoryError):
        fs.delete("folder")
    assert (root / "folder").is_dir()


def _disk(tmp_path):
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    (root / "old.py").write_text("old\n", encoding="utf-8")
    return str(root)
