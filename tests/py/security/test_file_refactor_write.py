"""SEC-22: endpoint policy and sole shared executor; written before effects."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.editing.shared import funnel

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("path", ["res://../outside.bin", "res://addons/asset.bin", "res://ADDONS/asset.bin",
                                  "res://AdDoNs/asset.bin", "res://project.godot", "res://.agent_history/log.bin"])
def test_transfer_denies_protected_endpoints(path):
    ctx = SimpleNamespace(path_policy=PathPolicy("C:/project"))
    for old, new in [(path, "res://new.bin"), ("res://old.bin", path)]:
        with pytest.raises(AppError) as error:
            funnel.guard_transfer(ctx, old, new)
        assert error.value.kind in ("denied", "invalid_input")


def test_root_plugin_transfer_does_not_weaken_ordinary_guard():
    ctx = SimpleNamespace(path_policy=PathPolicy("C:/project"))
    funnel.guard_transfer(ctx, "res://plugin.cfg", "res://renamed.cfg")
    with pytest.raises(AppError):
        funnel.guard_path(ctx, "plugin.cfg")


@pytest.mark.parametrize("flags", [(False, False), (True, False), (False, True), (True, True)])
def test_agent_tree_transfer_denied_even_with_trusted_flags(flags):
    policy = PathPolicy("C:/project", *flags, agent_dir="C:/project/addons/godot_agent")
    ctx = SimpleNamespace(path_policy=policy)
    with pytest.raises(AppError) as error:
        funnel.guard_transfer(ctx, "res://addons/godot_agent", "res://elsewhere")
    assert error.value.kind == "denied"


def test_no_direct_io_in_file_refactor_production():
    for path in (ROOT / "python/modules/editing/file_refactor").rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                assert name not in {"open", "os.replace", "os.rename", "os.remove", "shutil.move", "shutil.copy"}, path


def test_public_edge_is_narrow_and_foreign_domain_remains_forbidden(monkeypatch):
    from tools import lint_arch
    path = ROOT / "python/modules/editing/file_refactor/domain/core.py"
    monkeypatch.setattr(lint_arch, "imports_of", lambda _: ["python.modules.editing.paths_preview"])
    assert lint_arch.check_edges(path) == []
    monkeypatch.setattr(lint_arch, "imports_of", lambda _: ["python.modules.editing.paths_preview.domain.refs"])
    assert lint_arch.check_edges(path)
