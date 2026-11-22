"""Strict generated read-only card, no stale ToolSpec or foreign schema edits."""
import json
from pathlib import Path
import pytest
from python.kernel.schema import validate
from python.modules.scene_model.connections import tools
from tools.gen_contract import rendered

ROOT=Path(__file__).resolve().parents[3]


def test_generated_card_equals_current_toolspec():
    assert (ROOT/'contract/capabilities/connections.json').read_bytes()==rendered()['connections.json'].encode()


def test_read_only_strict_limits_and_schema():
    spec=tools.TOOLS[0]
    assert spec.name=='connections' and spec.effects=='read' and spec.idempotent and spec.cost=='cheap'
    assert set(spec.errors)=={'invalid_input','not_found','denied'}
    assert spec.args['additionalProperties'] is False and spec.result['additionalProperties'] is False
    assert spec.limits['max_file_bytes']==4*1024*1024


@pytest.mark.parametrize('case',[json.loads(p.read_bytes()) for p in sorted((ROOT/'fixtures/corpus/scene_model/connections').glob('*.json')) if p.name!='manifest.json'],ids=lambda c:c['id'])
def test_captured_cards_fit_strict_result(case):
    if case['expect']['ok']:
        validate(case['expect']['result'],tools.TOOLS[0].result)
