"""SEC-23: real containment/resolved identity; all trusted flags are inert."""
import os
from pathlib import Path
import subprocess

import pytest

POLICY = "Ресурсы аддонов разрешены только по явному запросу и текущей политике доступа"
PATHS = ["res://addons/tool/private.tres", "res://ADDONS/tool/private.tres",
         "res://.agent_history/private.tres", "res://.AGENT_HISTORY/private.tres",
         "res://project.godot", "res://PROJECT.GODOT", "res://../outside.tres"]


def action(path, dependency):
    return {"action": "edit_resource", "resource": "res://data.tres" if dependency else path,
            "operations": [{"op": "set_property", "target": [], "property": "value",
                            "value": {"type": "ResourcePath", "value": path} if dependency else
                                     {"type": "int", "value": 1}}]}


@pytest.mark.parametrize("flags", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("dependency", [False, True])
@pytest.mark.parametrize("path", PATHS)
def test_policy_both_roles_and_trusted_flags(tmp_path, flags, dependency, path):
    from tools.probe import resource_client
    (tmp_path / "data.tres").write_bytes(b"data")
    before = (tmp_path / "data.tres").read_bytes()
    answer = resource_client(tmp_path, action(path, dependency), kwargs={
        "allow_addons": flags[0], "allow_self_edit": flags[1]})
    assert answer == {"ok": False, "kind": "denied", "message": POLICY, "hint": ""}
    assert (tmp_path / "data.tres").read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data.tres"]


@pytest.mark.parametrize("target", ["addons/tool", ".agent_history", "outside"])
def test_real_junction_not_mocked(tmp_path, target):
    from tools.probe import resource_client
    project = tmp_path / "project"
    project.mkdir()
    (project / "data.tres").write_bytes(b"data")
    dest = tmp_path / "outside" if target == "outside" else project / target
    dest.mkdir(parents=True)
    (dest / "private.tres").write_bytes(b"secret")
    link = project / "alias"
    if os.name == "nt":
        run = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(dest)], capture_output=True)
        assert run.returncode == 0, run.stderr
    else:
        link.symlink_to(dest, target_is_directory=True)
    assert os.path.realpath(link) == os.path.realpath(dest)
    for dependency in (False, True):
        answer = resource_client(project, action("res://alias/private.tres", dependency))
        assert answer["kind"] == "denied" and answer["message"] == POLICY
    assert (dest / "private.tres").read_bytes() == b"secret"


def test_plugin_dependency_only_and_no_write_ports(tmp_path):
    from python.modules.editing.resource_ops import app
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.runtime.context import ModuleContext
    from python.substrate.fs.disk_fs import DiskFileSystem
    (tmp_path / "data.tres").write_bytes(b"data")
    (tmp_path / "plugin.cfg").write_bytes(b"[plugin]\n")
    port = ResourceRead(DiskFileSystem(str(tmp_path)))
    assert not any(hasattr(port, name) for name in ("write_raw", "write_text", "move", "remove"))
    ctx = ModuleContext("test", ports={"resource_read": port})
    prepared = app.prepare(action("res://plugin.cfg", True), ctx)
    assert prepared["action"]["wait_for_import"] == ["res://plugin.cfg"]
    assert set(prepared) == {"action_id", "action", "resource", "target", "action_digest", "before_hash", "state"}
    assert (tmp_path / "plugin.cfg").read_bytes() == b"[plugin]\n"


def test_raw_read_is_after_complete_schema_and_policy(tmp_path):
    from python.kernel.errors import AppError
    from python.modules.editing.resource_ops import app
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.runtime.context import ModuleContext
    from python.substrate.fs.disk_fs import DiskFileSystem
    (tmp_path / "data.tres").write_bytes(b"data")

    class SpyDisk(DiskFileSystem):
        reads = 0

        def read_raw(self, rel):
            self.reads += 1
            return super().read_raw(rel)
    disk = SpyDisk(str(tmp_path))
    ctx = ModuleContext("test", ports={"resource_read": ResourceRead(disk)})
    for declaration in ({"extra": 1}, dict(action("res://data.tres", False), summary=False),
                        action("res://addons/tool/private.tres", True)):
        with pytest.raises(AppError):
            app.prepare(declaration, ctx)
    assert disk.reads == 0


def test_changed_real_identity_during_read_fails_closed(tmp_path):
    from python.kernel.errors import AppError
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.substrate.fs.disk_fs import DiskFileSystem
    project, dest = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    dest.mkdir()
    (project / "data.tres").write_bytes(b"safe")
    (dest / "data.tres").write_bytes(b"outside")

    class AttackDisk(DiskFileSystem):
        def read_raw(self, rel):
            raw = super().read_raw(rel)
            (project / "data.tres").unlink()
            # Real directory junction retargets the old project identity after a safe read.
            project.rmdir()
            if os.name == "nt":
                done = subprocess.run(["cmd", "/c", "mklink", "/J", str(project), str(dest)], capture_output=True)
                assert done.returncode == 0
            else:
                project.symlink_to(dest, target_is_directory=True)
            return raw
    port = ResourceRead(AttackDisk(str(project)))
    with pytest.raises(AppError, match=POLICY) as error:
        port.file_sha256("res://data.tres")
    assert error.value.kind == "denied"
    assert (dest / "data.tres").read_bytes() == b"outside"
