"""D39 precise project-directory class, never a widened default or entry cap."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import check_limits

BOUNDARIES = [
    ('python/substrate/project/project_tools.py', 1960, True),
    ('python/substrate/project/reference.py', 2000, True),
    ('python/substrate/project/reference.py', 2001, False),
    ('python/substrate/project/nested/reference.py', 2000, True),
    ('python/substrate/project/project_settings_actions.py', 251, True),
    ('python/substrate/project_extra/reference.py', 401, False),
    ('python/substrate/project.py', 401, False),
    ('python/modules/project_ops/reference.py', 401, False),
    ('python/substrate/project/app.py', 81, False),
    ('python/substrate/project/module.py', 151, False),
    ('python/substrate/project/tools.py', 151, False),
    ('python/substrate/editor/transport.py', 401, False),
    ('python/substrate/project/reference.py', 400, True),
    ('python/substrate/project_other/reference.py', 400, True),
    ('python/substrate/llm/backends/reference.py', 3400, True),
]


@pytest.mark.parametrize('relative,count,accepted', BOUNDARIES)
def test_project_class_boundary(relative, count, accepted, monkeypatch):
    source = SimpleNamespace(name=Path(relative).name, relative_to=lambda root: Path(relative))
    monkeypatch.setattr(check_limits, 'python_files', lambda: [source])
    monkeypatch.setattr(check_limits, 'line_count', lambda path: count)
    assert bool(check_limits.check_files()) is (not accepted)


def test_project_class_does_not_change_other_limits():
    assert check_limits.FILE_MAX == 400
    assert check_limits.VERBATIM_FILE_MAX == 600
    assert check_limits.PARSER_VERBATIM_FILE_MAX == check_limits.API_VERBATIM_FILE_MAX == check_limits.ROUTING_VERBATIM_FILE_MAX == 3400
    assert check_limits.ENTRY_MAX == {'module.py': 150, 'tools.py': 150, 'app.py': 80}
    assert (check_limits.MODULE_MAX, check_limits.AREA_MAX, check_limits.AREA_COHESION_MAX) == (3000, 8000, 8400)
