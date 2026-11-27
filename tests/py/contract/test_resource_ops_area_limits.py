"""D18/R-22: bounded area cohesion, selfcheck resource_ops feature mask."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def gate():
    spec = importlib.util.spec_from_file_location("d18_limits", ROOT / "tools/check_limits.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.mark.parametrize("area", ["editing", "unrelated_area"])
@pytest.mark.parametrize("total,status", [(8000, "clean"), (8001, "warning"),
                                        (8400, "warning"), (8401, "error")])
def test_cohesion_boundaries(tmp_path, monkeypatch, area, total, status):
    check = gate()
    folder = tmp_path / "python/modules" / area
    folder.mkdir(parents=True)
    (folder / "witness.py").write_bytes(b"# line\n" * total)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check, "MODULES", tmp_path / "python/modules")
    violations, warnings = check.check_totals()
    assert bool(violations) == (status == "error")
    assert bool(warnings) == (status == "warning")
    if warnings:
        assert "8000" in warnings[0] and "8400" in warnings[0]
    if violations:
        assert "8401" in violations[0] and "8400" in violations[0]


def test_hard_limits_unchanged(tmp_path, monkeypatch):
    check = gate()
    assert check.AREA_MAX == 8000 and check.MODULE_MAX == 3000 and check.FILE_MAX == 400
    assert check.ENTRY_MAX == {"module.py": 150, "tools.py": 150, "app.py": 80}
    folder = tmp_path / "python/modules/editing/witness"
    folder.mkdir(parents=True)
    for name, total in [("module.py", 151), ("app.py", 81), ("domain.py", 401)]:
        (folder / name).write_bytes(b"# line\n" * total)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check, "PYTHON", tmp_path / "python")
    assert len(check.check_files()) == 3
