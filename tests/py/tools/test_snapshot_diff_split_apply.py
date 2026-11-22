"""C.20 write corpus executes on copies through the generic snapshot gate."""
import json
from pathlib import Path

from tools import snapshot_diff

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/split_py"


def _case(number):
    path = next(CORPUS.glob("%03d-*.json" % number))
    return json.loads(path.read_bytes())


def test_split_apply_scenario_projects_native_fields():
    answer = snapshot_diff.scenario_answer(_case(97))
    assert answer["ok"]
    projected = snapshot_diff.project_split_apply(answer["result"])
    assert projected == _case(97)["expect"]["result"]


def test_split_apply_scenario_injects_second_effect_failure():
    answer = snapshot_diff.scenario_answer(_case(106))
    assert not answer["ok"] and answer["kind"] == "internal"
