"""T-F.5 entry selection, rollback assets and frozen lifecycle contract."""
from configparser import ConfigParser
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def test_native_plugin_entry_is_selected():
    config = ConfigParser()
    config.read(ROOT / 'plugin.cfg', encoding='utf-8')
    entry = config['plugin']['script'].strip('"')
    assert entry == 'editor/native/agent_entry.gd'
    assert (ROOT / entry).is_file()


@pytest.mark.parametrize('path,digest', [
    ('editor/native/agent_entry.gd',
     'fea207f0296d429d372a9465c854cee3480b97da2ca5d09150357460a832f31f'),
    ('plugin.gd',
     'c20fc1628bd17f63e05fe2a2120aab3cc99471161bf7074d4d1d5b50ceba7886'),
    ('editor/t1_panel.gd',
     '354e15371f77870f5ebfe0427923a8a49a859fc0c439c76c66bd0ef701bbaf9e'),
])
def test_native_and_rollback_assets_remain_byte_exact(path, digest):
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


def test_fixture_import_boundary_is_empty_file():
    assert (ROOT / 'fixtures/.gdignore').read_bytes() == b''


def test_native_activation_reports_real_dock_not_a_placeholder():
    source = (ROOT / 'editor/native/agent_entry.gd').read_text('utf-8')
    assert 'func _report_entry_ready()' in source
    assert '"да" if _dock != null else "нет"' in source
    assert 'add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)' in source
