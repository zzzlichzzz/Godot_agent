"""ADR-0010: one exact app edge, not an area-wide shared exemption."""
from pathlib import Path

import pytest

from tools import lint_arch as lint


def edge(tmp_path, monkeypatch, source, target):
    python = tmp_path / 'python'
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    monkeypatch.setattr(lint, 'PYTHON', python)
    (python / 'modules/engine_kb/shared').mkdir(parents=True)
    (python / 'modules/engine_kb/shared/inheritance.py').write_text('', encoding='utf-8')
    path = tmp_path / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('from ' + target + ' import resolve_chain\n', encoding='utf-8')
    return lint.check_edges(path)


def test_exact_api_check_app_edge_is_allowed(tmp_path, monkeypatch):
    assert edge(tmp_path, monkeypatch, 'python/modules/verification/api_check/app.py',
                'python.modules.engine_kb.shared.inheritance') == []


@pytest.mark.parametrize('source,target', [
    ('python/modules/verification/api_check/domain/core.py', 'python.modules.engine_kb.shared.inheritance'),
    ('python/modules/verification/api_check/tools.py', 'python.modules.engine_kb.shared.inheritance'),
    ('python/modules/verification/check/app.py', 'python.modules.engine_kb.shared.inheritance'),
    ('python/modules/verification/api_check/app.py', 'python.modules.engine_kb.shared'),
    ('python/modules/verification/api_check/app.py', 'python.modules.engine_kb.shared.other'),
    ('python/modules/verification/api_check/app.py', 'python.modules.engine_kb.class_api.domain.core'),
    ('python/modules/verification/api_check/app.py', 'python.substrate.store.api_cache_store'),
])
def test_neighbor_edges_still_fail(tmp_path, monkeypatch, source, target):
    assert len(edge(tmp_path, monkeypatch, source, target)) == 1
