"""Only the two new reference directory classes receive the 3400-line cap."""
from unittest.mock import patch

import pytest

from tools import check_limits as limits
from tests.py.llm.test_llm_api_limits import SourcePath


@pytest.mark.parametrize('path,count,expected', [
    ('python/substrate/editor/references/runtime_debug.py', 3400, False),
    ('python/substrate/editor/references/runtime_debug.py', 3401, True),
    ('python/substrate/editor/references/nested/file.py', 3400, False),
    ('python/substrate/editor/references_wrong/file.py', 401, True),
    ('python/substrate/editor/client.py', 401, True),
    ('python/substrate/llm/backends/api_backend.py', 3400, False),
    ('python/substrate/llm/backends/api_backend.py', 3401, True),
    ('python/substrate/llm/backends_wrong/file.py', 401, True),
    ('python/substrate/editor/references/app.py', 81, True),
    ('python/substrate/llm/backends/module.py', 151, True),
    ('python/substrate/llm/backends/tools.py', 151, True),
    ('python/substrate/llm/api/file.py', 3400, False),
    ('python/substrate/llm/browser/file.py', 601, True),
    ('python/ordinary/file.py', 401, True),
])
def test_narrow_routing_reference_class(path, count, expected):
    with patch.object(limits, 'python_files', return_value=[SourcePath(path)]), \
         patch.object(limits, 'line_count', return_value=count):
        assert bool(limits.check_files()) is expected


def test_existing_size_totals_unchanged():
    assert (limits.FILE_MAX, limits.MODULE_MAX, limits.AREA_MAX, limits.AREA_COHESION_MAX) == (400, 3000, 8000, 8400)
    assert limits.ENTRY_MAX == {'module.py': 150, 'tools.py': 150, 'app.py': 80}
