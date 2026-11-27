"""Raw SHA differs for BOM/EOL/trailingLF; prepare never serializes the resource."""
import hashlib
import re

import pytest

RAW = [b"[resource]\nx = 1\n", b"[resource]\r\nx = 1\r\n", b"[resource]\rx = 1\r",
       b"[resource]\r\nx = 1\ry = 2\nz = 3", b"\xef\xbb\xbf[resource]\n",
       b"[resource]\nx = 1", b"x" * (4 * 1024 * 1024 + 1)]


@pytest.mark.parametrize("raw", RAW, ids=["lf", "crlf", "lone-cr", "mixed", "bom", "no-trailing", "big"])
def test_prepare_raw_sha_and_public_projection(tmp_path, raw):
    from tools.probe import resource_client
    path = tmp_path / "data.tres"
    path.write_bytes(raw)
    declaration = {"action": "edit_resource", "resource": "res://data.tres", "operations": [
        {"op": "set_property", "target": [], "property": "x", "value": {"type": "int", "value": 9}}]}
    private = resource_client(tmp_path, declaration)["result"]
    public = resource_client(tmp_path, private, "public_prepared")["result"]
    assert re.fullmatch("[0-9a-f]{32}", private["action_id"])
    assert public == {"action_id": private["action_id"], "action_digest": private["action_digest"],
                      "expected_resource_hash": hashlib.sha256(raw).hexdigest(), "prepare_in_editor": True}
    assert private["before_hash"] == public["expected_resource_hash"]
    assert path.read_bytes() == raw
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data.tres"]
