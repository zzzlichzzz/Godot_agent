"""Native tuple/list named projection, no invented dependency graph."""
import json
from pathlib import Path
import pytest
from python.kernel.schema import validate
from python.modules.scene_model.scene_deps import tools
from tools.gen_contract import rendered

ROOT=Path(__file__).resolve().parents[3]


def test_generated_card_equals_current_toolspec():
    assert (ROOT/'contract/capabilities/scene_deps.json').read_bytes()==rendered()['scene_deps.json'].encode()


def test_read_only_declared_scan_and_read_limits():
    spec=tools.TOOLS[0]
    assert spec.name=='scene_deps' and spec.effects=='read' and spec.idempotent and spec.cost=='heavy'
    assert set(spec.errors)=={'invalid_input','not_found','denied'}
    assert spec.args['additionalProperties'] is False and spec.result['additionalProperties'] is False
    assert spec.limits=={'max_file_bytes':4*1024*1024,'project_scan_max_file_bytes':512*1024}


@pytest.mark.parametrize('case',[json.loads(p.read_bytes()) for p in sorted((ROOT/'fixtures/corpus/scene_model/scene_deps').glob('*.json')) if p.name!='manifest.json'],ids=lambda c:c['id'])
def test_captured_result_fits_strict_schema(case):
    if case['expect']['ok']:
        validate(case['expect']['result'],tools.TOOLS[0].result)
