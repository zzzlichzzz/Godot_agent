"""Actual frozen external-sync inputs, including its distinct edge behaviour."""
import hashlib
import json
from pathlib import Path

import pytest

from tools import snapshot_diff

CORPUS = Path(__file__).resolve().parents[3] / "fixtures/corpus/editing/file_refactor"
CARDS = json.loads((CORPUS / "manifest.json").read_bytes())["sync_cases"]


@pytest.mark.parametrize("card", CARDS, ids=lambda card: card["id"])
def test_external_sync_corpus(card):
    raw = (CORPUS / card["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == card["sha256"]
    native = (CORPUS / card["native_raw_file"]).read_bytes()
    assert hashlib.sha256(native).hexdigest() == card["native_raw_sha256"]
    record = json.loads(raw)
    assert record["scenario"] == "external_sync"
    assert snapshot_diff.file_refactor_answer(record) == snapshot_diff.file_refactor_expected(record)
