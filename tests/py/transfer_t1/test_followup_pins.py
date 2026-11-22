"""D81 permits only exact declared tokens; every other old byte is pinned."""
import hashlib
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[3]
SPACED=(b"'api_check', 'ask', 'chat'",b"'api_check', 'ask', 'assistant_confirm', 'assistant_plan', 'assistant_rollback', 'assistant_turn', 'chat'")
COMPACT=(b"'api_check','ask','chat'",b"'api_check','ask','assistant_confirm','assistant_plan','assistant_rollback','assistant_turn','chat'")
NAME_EFFECT=(b"name == 'split_apply' or name.startswith('write_')",b"name == 'split_apply' or name.startswith('write_') or name in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn')")
N_EFFECT=(b"n == 'split_apply' or n.startswith('write_')",b"n == 'split_apply' or n.startswith('write_') or n in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn')")
CASES={
 'test_gd_lint.py':('3125a8d2393767bdb86983bb6541c5202ae1fe9d99d10f9f587c25ade8e03890',4444,90,[SPACED,NAME_EFFECT,(b"'count': 30",b"'count': 34")]),
 'test_node.py':('bbe8ab6e0863a5704139f1ea11e91ecc0dbae21061fb645805be693064917a5d',5578,105,[COMPACT,N_EFFECT,(b"'count':30",b"'count':34")]),
 'test_resource_ops.py':('7afdbf6c5541ec2d52967e2bf16dc9322d8888105855346100ca87dd6c7ba6ab',2752,55,[(b'"chat_gateway", "journal"',b'"chat_gateway", "native_planner", "journal"')]),
 'test_scene.py':('f619b22bdaa404f4aace2765ced3c1af522b67fc160c82a490566553a6d963d7',4993,96,[COMPACT,NAME_EFFECT,(b"'count':30",b"'count':34")]),
 'test_tscn_lint.py':('d4921e7c1a435b3c5a1a55fa1b5782d73633154fa3f6885f6795f603bef9aaac',2967,60,[(b"names + ['ask', 'chat', 'judge']",b"names + ['ask', 'assistant_confirm', 'assistant_plan', 'assistant_rollback', 'assistant_turn', 'chat', 'judge']"),N_EFFECT]),
 'test_verify.py':('7dfcd21232c16b34ee189fc6aceb46c49fee541ea295a231240ba1b18c085487',6572,128,[(b'len(agent.tools()) == 30',b'len(agent.tools()) == 34')]),
}

@pytest.mark.parametrize('name',CASES)
def test_six_inventory_files_reconstruct_exact_pre_delta_bytes(name):
    expected,size,lf,edits=CASES[name]
    raw=(ROOT/'tests/py/integration'/name).read_bytes()
    for before,after in reversed(edits):
        assert raw.count(after)==1,(name,after)
        raw=raw.replace(after,before,1)
    assert hashlib.sha256(raw).hexdigest()==expected
    assert (len(raw),raw.count(b'\n'),raw.count(b'\r\n'))==(size,lf,0)
