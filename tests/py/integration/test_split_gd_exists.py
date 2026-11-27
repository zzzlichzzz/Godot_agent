"""ADR-0011 substrate seam: occupied directories are not ordinary files."""
import hashlib

import pytest

from python.substrate.fs.disk_fs import DiskFileSystem


def tree(root):
    return [(p.relative_to(root).as_posix(), p.is_dir(),
             None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(root.rglob('*'))]


def test_real_directory_is_occupied_but_not_file(tmp_path):
    (tmp_path / 'module.gd').mkdir()
    fs = DiskFileSystem(tmp_path)
    before = tree(tmp_path)
    assert fs.exists('module.gd') is True
    assert fs.is_file('module.gd') is False
    assert fs.exists('missing.gd') is False
    assert tree(tmp_path) == before


def test_real_file_is_occupied_without_reading_contents(tmp_path):
    (tmp_path / 'module.gd').write_bytes(b'large enough to exceed the reader')
    fs = DiskFileSystem(tmp_path, max_bytes=1)
    before = tree(tmp_path)
    assert fs.exists('module.gd') is True
    assert fs.is_file('module.gd') is True
    assert tree(tmp_path) == before


@pytest.mark.parametrize('rel', ['../outside', '/absolute', 'bad\x00path'])
def test_exists_preserves_containment(tmp_path, rel):
    with pytest.raises(PermissionError):
        DiskFileSystem(tmp_path).exists(rel)
