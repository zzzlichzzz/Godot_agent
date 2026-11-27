"""All native tree lines projected to D20 nodes, not an invented public tool."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / "fixtures/corpus/project_text/tree"


@pytest.mark.parametrize("case", sorted(CORPUS.glob("[0-9]*.json")), ids=lambda path: path.stem)
def test_actual_native_tree(case):
    from tools import probe
    record = json.loads(case.read_bytes())
    answer = probe.project_text_corpus_answer(record)
    assert {key: answer[key] for key in record["expect"]} == record["expect"]
