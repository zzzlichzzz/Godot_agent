"""tests/py/formats/test_gdscript_parity.py - разбор .gd против эталона (R-09).

Корпус S1 лежит в `fixtures/parity/gdscript/`: восемь .gd-файлов и
`expected.json`, снятый с эталонного `gd_semantic_parser.parse`. Эталон
отдаёт `{"kind","name","owner","start","end","line","column"}` для объявлений,
`context` для ссылок и `value` для строк — перенос обязан совпасть целиком,
включая смещения: на них держатся координаты `usages`.
"""

import json
from pathlib import Path

import pytest

from python.formats import gdscript

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures" / "parity" / "gdscript"
EXPECTED = json.loads((CORPUS / "expected.json").read_text(encoding="utf-8"))
BANNED_IN_FORMATS = ("import os", "import pathlib", "import io", "open(")


def _text(name):
    """Текст файла корпуса без BOM и без нормализации переводов строк."""
    return (CORPUS / name).read_bytes().decode("utf-8-sig")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_parse_matches_reference(name):
    assert gdscript.parse(_text(name), name) == EXPECTED[name]


def test_token_offsets_point_at_their_value():
    text = _text("declarations.gd")
    for token in gdscript.tokenize(text):
        assert text[token["start"]:token["end"]] == token["value"]
        assert token["column"] >= 1 and token["line"] >= 1


def test_comment_with_declaration_produces_no_declaration():
    parsed = gdscript.parse(_text("comments.gd"), "comments.gd")
    functions = [item["name"] for item in parsed["declarations"]
                 if item["kind"] == "function"]
    assert functions == ["real"]
    assert all("take_damage" not in token["value"]
               for token in gdscript.tokenize(_text("comments.gd")))


def test_unclosed_string_is_partial_but_not_a_crash():
    parsed = gdscript.parse(_text("strings.gd"), "strings.gd")
    assert parsed["parse_status"] == "partial"
    assert parsed["errors"] == ["line 11: unclosed string"]
    last = parsed["strings"][-1]
    assert last["value"].strip() == '"no end'
    assert last["line"] == 11


@pytest.mark.parametrize("name,line", [("bom.gd", 3), ("crlf.gd", 3)])
def test_bom_and_crlf_keep_line_numbers(name, line):
    declarations = gdscript.parse(_text(name), name)["declarations"]
    assert [(item["kind"], item["line"]) for item in declarations] == [("function", line)]


def test_annotations_do_not_hide_the_declaration():
    declarations = gdscript.parse(_text("annotations.gd"), "annotations.gd")["declarations"]
    assert [item["kind"] for item in declarations] == ["variable", "function",
                                                       "parameter"]
    assert declarations[0]["is_export"] is True
    assert declarations[0]["export_annotation"] == "export"


def test_typed_collections_are_type_context():
    parsed = gdscript.parse(_text("typing.gd"), "typing.gd")
    typed = sorted({item["name"] for item in parsed["references"]
                    if item["context"] == "type"})
    assert "Player" in typed


def test_formats_has_no_io():
    for path in (ROOT / "python" / "formats").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in BANNED_IN_FORMATS:
            assert banned not in text, "%s: %s" % (path.name, banned)


def test_script_parent_reads_res_and_inner_class():
    assert gdscript.script_parent('extends "res://base.gd"\n', "res://a.gd") == (
        "res://base.gd", None)
    assert gdscript.script_parent("extends Node\n\nclass Inner extends Base:\n\tpass\n",
                                  "res://a.gd") == (None, "Node")
    assert gdscript.script_parent('extends "base.gd"\n', "res://src/a.gd") == (
        "res://src/base.gd", None)
