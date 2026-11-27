"""SEC24 attacks: no plan/effect/leak for a forbidden target or dependency."""
import json

import pytest

from python.kernel.errors import AppError
from tests.py.contract.test_resource_apply_cases import CASES, TEXTURE, action, context


@pytest.mark.parametrize("path", ["res://addons/bad.tres", "res://ADDONS/bad.tres",
                                    "res://.AGENT_HISTORY/bad.tres", "res://project.godot", "res://../bad.tres"])
@pytest.mark.parametrize("dependency", [False, True])
def test_forbidden_identity_before_plan(tmp_path, path, dependency):
    from python.modules.editing.resource_ops import app
    project, ctx, _ = context(tmp_path)
    if ".." not in path:
        file = project / path[6:]
        file.parent.mkdir(exist_ok=True)
        file.write_bytes(TEXTURE)
    operation = CASES[0][2] if not dependency else dict(CASES[1][2], new=path)
    request = action(operation, "res://data.tres" if dependency else path)
    before = {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    with pytest.raises(AppError) as caught:
        app.prepare_write(request, ctx)
    assert caught.value.kind == "denied"
    assert before == {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert ctx.port("journal").plan_ids() == []


def test_raw_second_read_rechecks_policy_before_io(tmp_path):
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.substrate.fs.disk_fs import DiskFileSystem
    (tmp_path / "data.tres").write_bytes(CASES[0][1])

    class ReadWitness(DiskFileSystem):
        reads = []

        def read_raw(self, rel):
            self.reads.append(rel)
            return super().read_raw(rel)

    class PolicyWitness(ResourceRead):
        identities = 0

        def identity(self, path):
            self.identities += 1
            if self.identities >= 3:
                return {"relative": None, "contained": False, "is_file": False}
            return super().identity(path)

    disk = ReadWitness(str(tmp_path))
    with pytest.raises(AppError) as caught:
        PolicyWitness(disk).read_raw("res://data.tres")
    assert caught.value.kind == "denied" and disk.reads == ["data.tres"]


def test_public_projection_has_no_raw_or_absolute(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, _ = context(tmp_path)
    response = app.prepare_write(action(CASES[0][2]), ctx)
    encoded = json.dumps(response, ensure_ascii=False)
    assert "bytes_b64" not in encoded and str(project) not in encoded and "[gd_resource" not in encoded


@pytest.mark.parametrize("path", ["res://ADDONS/bad.tres", "res://project.godot"])
def test_existing_external_dependency_uses_module_policy_before_common_guard(tmp_path, path):
    from python.modules.editing.resource_ops import app
    from python.modules.editing.resource_ops.domain.core import POLICY_MESSAGE
    raw = CASES[0][1].replace(b"[resource]", ('[ext_resource type="Texture2D" path="' + path + '" id="bad"]\n\n[resource]').encode())
    project, ctx, _ = context(tmp_path, raw)
    before = {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    with pytest.raises(AppError) as caught:
        app.prepare_write(action(CASES[0][2]), ctx)
    assert caught.value.kind == "denied" and str(caught.value) == POLICY_MESSAGE
    assert before == {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    assert ctx.port("journal").plan_ids() == []
