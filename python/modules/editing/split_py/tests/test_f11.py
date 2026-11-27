"""F11: a missing donor wins before plugin.cfg lookup; accepted scan stays read-only."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.modules.editing.split_py.app import call

ROOT = Path(__file__).resolve().parents[5]
CASE = json.loads((ROOT/'fixtures/corpus/editing/split_py/048-plan-missing-no-addon.json').read_bytes())


class MissingFS:
    def __init__(self):
        self.calls = []

    def is_file(self, rel):
        self.calls.append(rel)
        return False


@pytest.mark.parametrize('rel',['missing.py','inner/missing.py','inner/deep/missing.py'])
def test_missing_before_plugin_lookup(rel):
    fs = MissingFS()
    ctx = SimpleNamespace(port=lambda name:fs,path_policy=SimpleNamespace(deny_reason=lambda rel:None))
    with pytest.raises(AppError) as raised:
        call('split_scan',{'path':'res://'+rel},ctx)
    assert raised.value.kind == CASE['expect']['kind'] == 'not_found'
    assert raised.value.message == CASE['expected_message'].replace('missing.py',rel)
    assert fs.calls == [rel]
