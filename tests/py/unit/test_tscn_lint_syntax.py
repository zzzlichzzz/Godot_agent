"""Red specification for append-only tokenizers, before new formats code."""
import importlib
import importlib.util

import pytest


def syntax():
    name = 'python.formats.tscn_lint_syntax'
    assert importlib.util.find_spec(name) is not None
    return importlib.import_module(name)


@pytest.mark.parametrize('text', ['[node name="Root" type="Node"]\n',
    '\ufeff[gd_scene format=3]\r\n[node name="Root" type="Node"]\r\n'])
def test_neutral_header_tokens_preserve_source_spans_and_attrs(text):
    fmt = syntax()
    tokens = list(fmt.node_finditer(text))
    assert len(tokens) == 1
    token = tokens[0]
    assert text[token.start():token.end()] == '[node name="Root" type="Node"]'
    assert fmt.attrs(token.group(1)) == {'name': 'Root', 'type': 'Node'}
    assert token.group(0) == text[token.start():token.end()]
    assert not hasattr(token, 're')


@pytest.mark.parametrize('line,wanted', [('[/node]', True), (' [/node]', False),
                                      ('[/node] extra', False), ('[/gd_scene]', True)])
def test_closing_tags_have_original_anchored_grammar(line, wanted):
    assert bool(syntax().closing_tag_match(line)) is wanted


def test_attribute_references_are_neutral_kind_id_pairs():
    assert syntax().attrs(' name="Root" instance=ExtResource("1_scene") id=5') == {
        'name': 'Root', 'instance': ('ExtResource', '1_scene'), 'id': '5'}


def test_instance_text_parsing_is_pure_and_preserves_fuzzy_paths():
    fmt = syntax()
    assert fmt.scene_node_paths(None) == (None, None)
    text = ('[gd_scene format=3]\n[node name="Root" type="Node"]\n'
            '[node name="Kid" parent="." instance_placeholder="res://child.tscn"]\n')
    assert fmt.scene_node_paths(text) == ({'', 'Kid'}, {'Kid'})
