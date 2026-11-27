"""Behavioral ToolSpec checks; generated-artifact drift belongs to the frozen gate."""
import json
from pathlib import Path

import pytest

from python.kernel.schema import validate

ROOT = Path(__file__).resolve().parents[3]


def test_read_only_descriptor():
    from python.modules.editing.split_py.tools import APPLY, PLAN, SCAN, TOOLS
    assert TOOLS==(SCAN,PLAN,APPLY) and SCAN.name=='split_scan' and SCAN.effects=='read' and SCAN.idempotent
    assert SCAN.errors==('invalid_input','not_found','denied') and SCAN.availability=='*' and SCAN.cost=='cheap'
    assert SCAN.limits=={'max_file_bytes':4*1024*1024} and not SCAN.requires_preview


def test_generated_card_surface():
    card = json.loads((ROOT/'contract/capabilities/split_scan.json').read_bytes())
    assert card['module_id']=='editing.split_py' and card['tool_name']=='split_scan'
    assert card['capability_id']=='editing.split_py' and card['schema_version']==1
    assert card['effects']==['read'] and card['idempotent'] and not card['requires_preview']
    assert card['errors']==['invalid_input','not_found','denied'] and card['limits']=={'max_file_bytes':4194304}


@pytest.mark.parametrize('args, valid', [({'path':'res://donor.py'},True),({},False),
    ({'path':7},False),({'path':''},False),({'path':'res://donor.py','extra':1},False)])
def test_input_schema(args, valid):
    from python.modules.editing.split_py.tools import ARGS
    assert (not validate(args,ARGS)) is valid


@pytest.mark.parametrize('casefile', [p for p in sorted((ROOT/'fixtures/corpus/editing/split_py').glob('[0-9]*.json'))
                                     if json.loads(p.read_bytes())['tool']=='split_scan'],ids=lambda p:p.stem)
def test_success_payload_schema(casefile):
    from python.modules.editing.split_py.tools import RESULT
    case = json.loads(casefile.read_bytes())
    if case['expect']['ok']:
        assert not validate(case['expect']['result'],RESULT)


def test_schema_rejects_wrong_categories_and_extra_fields():
    from python.modules.editing.split_py.tools import RESULT
    result = json.loads((ROOT/'fixtures/corpus/editing/split_py/003-from_import.json').read_bytes())['expect']['result']
    assert not validate(result,RESULT)
    result['occurrences'][0]['kind']='call'
    assert validate(result,RESULT)
    result['occurrences'][0]['kind']='import'
    result['schema']=1
    assert validate(result,RESULT)
