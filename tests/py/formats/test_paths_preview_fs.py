"""D6 per-consumer five-MiB read seam; neighbors keep four MiB."""
import errno

import pytest

from python.substrate.fs.disk_fs import DiskFileSystem


def reader(root):
    from python.substrate.fs.read_only import ReadOnlyFileSystem
    return ReadOnlyFileSystem(root, max_bytes=5 * 1024 * 1024)


def test_five_mib_is_local_not_a_global_limit_change(tmp_path):
    raw = b"#" + b"x" * (4 * 1024 * 1024 + 1)
    (tmp_path / "large.gd").write_bytes(raw)
    with pytest.raises(OSError) as caught:
        DiskFileSystem(tmp_path).read_raw("large.gd")
    assert caught.value.errno == errno.EFBIG
    assert reader(tmp_path).read_raw("large.gd") == raw


def test_over_five_mib_stays_a_read_refusal(tmp_path):
    (tmp_path / "large.gd").write_bytes(b"#" * (5 * 1024 * 1024 + 1))
    with pytest.raises(OSError) as caught:
        reader(tmp_path).read_raw("large.gd")
    assert caught.value.errno == errno.EFBIG


def test_read_only_adapter_has_no_effect_methods_and_preserves_bytes(tmp_path):
    raw = b"\xef\xbb\xbfa\r\nb\rc\n"
    (tmp_path / "a.gd").write_bytes(raw)
    fs = reader(tmp_path)
    assert fs.read_raw("a.gd") == raw and fs.list_files() == ["a.gd"]
    assert fs.is_file("a.gd") and fs.exists("a.gd")
    assert not any(hasattr(fs, name) for name in ("write_text", "create", "delete", "write_raw"))
