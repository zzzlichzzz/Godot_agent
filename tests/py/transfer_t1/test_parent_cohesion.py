"""Real editing footprint stays inside the original frozen limits."""
import importlib.util
from pathlib import Path

def test_parent_proof_extension_fits_frozen_real_area_budget():
    root=Path(__file__).resolve().parents[3]
    spec=importlib.util.spec_from_file_location('t1_frozen_area',root/'tools/check_limits.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    assert (checker.FILE_MAX,checker.MODULE_MAX,checker.AREA_MAX,checker.AREA_COHESION_MAX)==(400,3000,8000,8400)
    violations,warnings=checker.check_totals()
    assert not violations,violations
    assert any('python/modules/editing:' in line for line in warnings)
