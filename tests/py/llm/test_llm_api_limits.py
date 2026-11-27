"""D35 class boundaries, including unchanged default/browser/parser/entry caps."""
from pathlib import Path
from unittest.mock import patch
import pytest
from tools import check_limits as limits


class SourcePath:
    def __init__(self, relative):
        self.relative = relative
        self.name = Path(relative).name

    def relative_to(self, root):
        return Path(self.relative)


@pytest.mark.parametrize(('relative', 'count', 'accepted'), [
    ('python/substrate/llm/api/reference.py', 3400, True),
    ('python/substrate/llm/api/reference.py', 3401, False),
    ('python/substrate/llm/api/nested/reference.py', 3400, True),
    ('python/substrate/llm/api_wrong/reference.py', 401, False),
    ('python/substrate/llm/reference.py', 400, True),
    ('python/substrate/llm/reference.py', 401, False),
    ('python/substrate/llm/browser/reference.py', 600, True),
    ('python/substrate/llm/browser/reference.py', 601, False),
    ('python/substrate/llm/parsers/reference.py', 3400, True),
    ('python/substrate/llm/parsers/reference.py', 3401, False),
    ('python/substrate/llm/api/module.py', 150, True),
    ('python/substrate/llm/api/module.py', 151, False),
    ('python/substrate/llm/api/app.py', 81, False),
])
def test_api_verbatim_class_limit(relative, count, accepted):
    with patch.object(limits, 'python_files', return_value=[SourcePath(relative)]), \
            patch.object(limits, 'line_count', return_value=count):
        assert (not limits.check_files()) is accepted
