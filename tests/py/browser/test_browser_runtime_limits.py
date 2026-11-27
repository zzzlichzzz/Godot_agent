"""D32 red-before-rule boundary tests; ordinary and browser caps stay frozen."""
import importlib.util

import pytest

from tests.py.browser.runtime_cases import ROOT


@pytest.mark.parametrize(('relative', 'lines', 'allowed'), [
    ('python/substrate/llm/parsers/parser_base.py', 3352, True),
    ('python/substrate/llm/parsers/reference.py', 3400, True),
    ('python/substrate/llm/parsers/reference.py', 3401, False),
    ('python/substrate/llm/browser/reference.py', 601, False),
    ('python/substrate/llm/parsers_elsewhere/reference.py', 401, False),
])
def test_verbatim_class_boundary(relative, lines, allowed, tmp_path):
    spec = importlib.util.spec_from_file_location('runtime_limit_guard', ROOT / 'tools/check_limits.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.ROOT = tmp_path
    guard.PYTHON = tmp_path / 'python'
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b'# reference\n' * lines)
    violations = guard.check_files()
    assert (not violations) is allowed
