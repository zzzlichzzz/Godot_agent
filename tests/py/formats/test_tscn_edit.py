"""Offset-only edits: no reconstruction, BOM/newline/untouched-byte preservation."""

import json
from pathlib import Path

import pytest

from python.formats import tscn

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures" / "parity" / "tscn"
NAMES = sorted(json.loads((CORPUS / "expected.structure.json").read_bytes()))


@pytest.mark.parametrize("name", NAMES)
def test_empty_patch_is_byte_identical(name):
    raw = (CORPUS / name).read_bytes()
    text = raw.decode("utf-8")
    assert tscn.patch(text, []) == text
    assert tscn.patch(text, []).encode("utf-8") == raw


@pytest.mark.parametrize("name", ["basic.tscn", "spans.tscn", "player.tscn",
                                 "bom.tscn", "crlf.tscn", "bom_crlf.tscn"])
@pytest.mark.parametrize("backwards_input", [False, True])
def test_two_length_changing_edits_touch_only_their_spans(name, backwards_input):
    text = (CORPUS / name).read_bytes().decode("utf-8")
    root = tscn.structure(text)[1][0]
    header = root["header_span"]
    old_header = text[slice(*header)]
    replacement_header = old_header.replace(root["name"], "RenamedRootMuchLonger", 1)
    value_start = text.index("position = ") + len("position = ")
    value_end = text.index("\n", value_start)
    if text[value_end - 1] == "\r":
        value_end -= 1
    replacement_value = "Vector2(12345, -98765)"
    edits = [(header, replacement_header),
             ((value_start, value_end), replacement_value)]
    if backwards_input:
        edits.reverse()
    original_edits = list(edits)
    result = tscn.patch(text, edits)
    # Independent oracle: concatenate original untouched slices, not shifted text.
    expected = (text[:header[0]] + replacement_header + text[header[1]:value_start]
                + replacement_value + text[value_end:])
    assert result.encode("utf-8") == expected.encode("utf-8")
    assert edits == original_edits
    assert result.count("\r\n") == text.count("\r\n")
    assert result.startswith("\ufeff") == text.startswith("\ufeff")


@pytest.mark.parametrize("name,bom,crlf", [("bom.tscn", True, False),
                                        ("crlf.tscn", False, True),
                                        ("bom_crlf.tscn", True, True)])
def test_bom_and_crlf_are_present_and_survive_patch(name, bom, crlf):
    raw = (CORPUS / name).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") is bom
    assert (b"\r\n" in raw) is crlf
    text = raw.decode("utf-8")
    assert tscn.patch(text, []).encode("utf-8") == raw
    span = tscn.structure(text)[1][0]["header_span"]
    header = text[slice(*span)]
    result = tscn.patch(text, [(span, header + " ")])
    assert result.encode("utf-8") == (
        text[:span[0]] + header + " " + text[span[1]:]).encode("utf-8")


def test_patch_accepts_insertions_deletions_and_replacements():
    text = "αβγδε\r\n"
    assert tscn.patch(text, [((0, 0), "BOM?"), ((1, 3), ""), ((3, 4), "Δ")]) == (
        "BOM?αΔε\r\n")
