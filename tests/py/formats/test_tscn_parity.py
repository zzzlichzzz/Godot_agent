"""Literal .tscn/.tres parity with both frozen parsers (R-07/R-09).

Expected answers were captured before the port. JSON turns the reference's
tuples into arrays; only that transport conversion is used in comparisons.
Text is decoded as UTF-8, without stripping BOM or translating newlines.
"""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from python.formats import tscn

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures" / "parity" / "tscn"
STRUCTURE = json.loads((CORPUS / "expected.structure.json").read_bytes())
FIELDS = json.loads((CORPUS / "expected.fields.json").read_bytes())
MANIFEST = json.loads((CORPUS / "manifest.json").read_bytes())
BANNED_IN_FORMATS = ("import os", "import pathlib", "import io", "open(")


def _text(name):
    return (CORPUS / name).read_bytes().decode("utf-8")


@pytest.mark.parametrize("name", sorted(STRUCTURE))
def test_structure_matches_reference(name):
    actual = tscn.structure(_text(name))
    assert isinstance(actual, tuple) and len(actual) == 4
    assert json.loads(json.dumps(actual)) == STRUCTURE[name]


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_fields_matches_reference(name):
    actual = tscn.fields(_text(name))
    assert isinstance(actual, tuple) and len(actual) == 3
    assert json.loads(json.dumps(actual)) == FIELDS[name]


@pytest.mark.parametrize("name", sorted(STRUCTURE))
def test_spans_are_character_offsets_in_untouched_text(name):
    text = _text(name)
    _ext, nodes, connections, tracks = tscn.structure(text)
    for node in nodes:
        header = node["header_span"]
        body = node["body_span"]
        assert isinstance(header, tuple) and isinstance(body, tuple)
        assert 0 <= header[0] < header[1] == body[0] <= body[1] <= len(text)
        assert text[slice(*header)].startswith("[node ")
        assert text[slice(*header)].endswith("]")
    for connection in connections:
        assert isinstance(connection["span"], tuple)
        assert text[slice(*connection["span"])] == connection["raw"]
    for track in tracks:
        assert isinstance(track["full_span"], tuple)
        assert isinstance(track["path_span"], tuple)
        assert text[slice(*track["path_span"])] == track["path"]
        assert track["full_span"][0] <= track["path_span"][0]
        assert track["path_span"][1] <= track["full_span"][1]


def test_corpus_and_captured_answers_match_manifest():
    inputs = {p.name for p in CORPUS.iterdir() if p.suffix in (".tscn", ".tres")}
    assert len(inputs) >= 12
    assert inputs == set(STRUCTURE) == set(FIELDS) == set(MANIFEST["files"])
    for name, entry in MANIFEST["files"].items():
        raw = (CORPUS / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["bytes"]
    for name, digest in MANIFEST["expected"].items():
        assert hashlib.sha256((CORPUS / name).read_bytes()).hexdigest() == digest
    assert (CORPUS / "player.tscn").read_bytes() == (
        ROOT / MANIFEST["copied"]["player.tscn"]).read_bytes()


def test_tscn_has_no_io():
    path = ROOT / "python" / "formats" / "tscn.py"
    text = path.read_text(encoding="utf-8")
    for banned in BANNED_IN_FORMATS:
        assert banned not in text, "%s: %s" % (path.name, banned)
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in ("os", "pathlib", "io")
                       for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in ("os", "pathlib", "io")


def test_public_api_preserves_three_format_operations_and_adds_rows():
    assert tuple(tscn.__all__) == ("structure", "fields", "patch", "rows")
    assert all(callable(getattr(tscn, name)) for name in tscn.__all__)
