"""Native bool/state, object reexports, strict shapes; drift checked by generator."""
import copy
import json
from pathlib import Path

import pytest

from python.kernel.schema import validate

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT/'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json'))
         if (c := json.loads(p.read_bytes()))['tool'] == 'split_plan']


def test_descriptor_and_module():
    from python.modules.editing.split_py.tools import APPLY, PLAN, SCAN, TOOLS
    from python.modules.editing.split_py.module import MODULE
    assert TOOLS == (SCAN,PLAN,APPLY) and MODULE.provides_tools == ('split_scan','split_plan','split_apply')
    assert MODULE.requires_ports == ('fs','journal') and MODULE.requires == ('editing.write_apply',)
    assert PLAN.name == 'split_plan' and PLAN.effects == 'read' and PLAN.idempotent
    assert PLAN.errors == ('invalid_input','not_found','denied') and PLAN.availability == '*'
    assert PLAN.cost == 'cheap' and PLAN.limits == {'max_file_bytes':4194304} and not PLAN.requires_preview


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['id'])
def test_success_payload_schema(case):
    from python.modules.editing.split_py.tools import PLAN_RESULT
    if case['expect']['ok']:
        assert not validate(case['expect']['result'],PLAN_RESULT)


@pytest.mark.parametrize('args,valid', [({'path':'res://donor.py'},True),
    ({'path':'res://donor.py','groups':[],'target_lines':0},True),
    ({'path':'res://donor.py','groups':[{'module':'part','symbols':[]}]},True),
    ({},False),({'path':''},False),({'path':'res://donor.py','target_lines':'499'},False),
    ({'path':'res://donor.py','groups':[{'module':'part','funcs':[]}]},False),
    ({'path':'res://donor.py','extra':1},False)])
def test_args(args,valid):
    from python.modules.editing.split_py.tools import PLAN_ARGS
    assert (not validate(args,PLAN_ARGS)) is valid


@pytest.mark.parametrize('field', ['state','reexports','module_text','symbol_line_start','extra'])
def test_reject_private_fields_and_wrong_native_shapes(field):
    from python.modules.editing.split_py.tools import PLAN_RESULT
    result = copy.deepcopy(next(c['expect']['result'] for c in CASES if c['id']=='050-plan-explicit'))
    if field == 'state': result['inventory']['symbols'][0]['state'] = 'mutable'
    if field == 'reexports': result['facade']['reexports'] = ['fn']
    if field == 'module_text': result['modules'][0]['text'] = 'hidden'
    if field == 'symbol_line_start': result['inventory']['symbols'][0]['line_start'] = 1
    if field == 'extra': result['extra'] = 1
    assert validate(result,PLAN_RESULT)


def test_generated_card():
    card = json.loads((ROOT/'contract/capabilities/split_plan.json').read_bytes())
    assert card['tool_name'] == 'split_plan' and card['module_id'] == 'editing.split_py'
    assert card['capability_id'] == 'editing.split_py' and card['effects'] == ['read']
    assert card['idempotent'] and card['schema_version'] == 1 and not card['requires_preview']


def test_dispatched_payload_matches_strict_schema(tmp_path):
    from python.modules.editing.split_py.tools import PLAN_RESULT
    from python.runtime.bootstrap import build_agent
    case = next(c for c in CASES if c['id'] == '050-plan-explicit')
    agent = build_agent(ROOT/'fixtures/projects'/case['fixture'],state_dir=str(tmp_path/'state'))
    reply = agent.call('split_plan',case['args'])
    assert reply['ok']
    assert not validate(reply['result'],PLAN_RESULT)
