"""L2 §4: a manifest-owned corpus is discoverable without an alias copy."""
from tools import selfcheck


def test_context_ask_discovers_frozen_librarian_manifest():
    expected = selfcheck.ROOT / "fixtures/corpus/context/librarian"
    assert selfcheck.corpus_folders("context.ask") == [expected]
