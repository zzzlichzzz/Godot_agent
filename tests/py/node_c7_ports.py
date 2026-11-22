"""Test composition only: consumer module tests receive real bound callables.

No foreign module imports in consumer tests and no accepted conftest changes.
"""
import pytest

from python.runtime.bootstrap import default_ports


@pytest.fixture
def c7_ports(tmp_path):
    return default_ports(tmp_path, profile='headless', state_dir=tmp_path / 'state')
