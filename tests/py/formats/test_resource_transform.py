"""D18 pure byte contract and six native-derived operation cases."""
import pytest

from python.kernel.errors import AppError
from tests.py.contract.test_resource_apply_cases import ANIMATION, CASES, DEPENDENCIES, action


def transformed(raw, operation):
    from python.modules.editing.resource_ops.domain import transform
    facts = {"res://data.tres": {"relative": "data.tres", "contained": True, "is_file": True}}
    facts.update({path: {"relative": path[6:], "contained": True, "is_file": True} for path in DEPENDENCIES})
    from python.modules.editing.resource_ops.domain.core import normalize_action
    normalized, _ = normalize_action(facts, action(operation))
    return transform.transform(raw, normalized, DEPENDENCIES)


@pytest.mark.parametrize("name,raw,operation,marker", CASES, ids=[c[0] for c in CASES])
def test_six_operation_success(name, raw, operation, marker):
    output = transformed(raw, operation)
    assert isinstance(output, bytes) and output != raw and marker in output
    assert output.endswith((b"\n", b"\r")) == raw.endswith((b"\n", b"\r"))
    assert raw.splitlines()[0].split(b'uid="')[1].split(b'"')[0] in output.splitlines()[0]
    assert transformed(raw, operation) == output


@pytest.mark.parametrize("eol", [b"\n", b"\r\n", b"\r"])
@pytest.mark.parametrize("final", [False, True])
def test_existing_value_preserves_every_other_byte(eol, final):
    source = ANIMATION.replace(b"; input comment must not be mistaken for an operation\n", b"") if eol == b"\r" else ANIMATION
    raw = source.replace(b"\n", eol) + (eol if final else b"")
    assert transformed(raw, CASES[0][2]) == raw.replace(b"length = 1.0", b"length = 2.0")


def test_mixed_eol_replacement_and_insertion():
    raw = ANIMATION.replace(b"\n", b"\r\n").replace(b"length = 1.0", b"length = 1.0\n")
    output = transformed(raw, CASES[2][2])
    assert raw in output and b'tracks/0/type = "value"\r\n' in output
    # An existing multiline property is replaced using its own first EOL.
    existing = raw + b'tracks/0/keys = {\n"times": PackedFloat32Array(0)\n}\r\n'
    with pytest.raises(AppError):
        transformed(existing, CASES[2][2])


def test_bom_refused_with_literal_native_error():
    with pytest.raises(AppError) as caught:
        transformed(b"\xef\xbb\xbf" + ANIMATION, CASES[0][2])
    assert caught.value.kind == "invalid_input"
    assert caught.value.message == "ResourceLoader не смог загрузить ресурс"
    assert caught.value.details["native_code"] == "load_failed"


def test_existing_animation_mixed_spans_do_not_normalize():
    old = b'{\r\n"frames": [],\n"loop": true,\r"name": &"default",\r\n"speed": 5.0\n}'
    raw = b'[gd_resource type="SpriteFrames" format=3]\r\n[resource]\r\nanimations = [' + old + b']\r\n'
    output = transformed(raw, CASES[3][2])
    assert old in output and b"\r\r\n" not in output


@pytest.mark.parametrize("bad", [b"[gd_resource type=", ANIMATION + b'\nlength = 7',
                                ANIMATION.replace(b"1.0", b'"unterminated'),
                                ANIMATION.replace(b'type="Animation"', b'type="UnknownClass"')])
def test_ambiguous_or_unsupported_input_fails_closed(bad):
    with pytest.raises(AppError):
        transformed(bad, CASES[0][2])


@pytest.mark.parametrize("value", ['plain', 'quote"slash\\', 'строка', 'line\n\ttab'])
def test_pure_quoted_resource_codec_roundtrip(value):
    from python.modules.editing.resource_ops.domain.document import quote, unquote
    assert unquote(quote(value)) == value


@pytest.mark.parametrize("value", ['"bad\\x"', '"bad\x01"', 'not quoted'])
def test_pure_codec_refuses_unsupported_literal(value):
    from python.modules.editing.resource_ops.domain.document import unquote
    with pytest.raises(AppError):
        unquote(value)


def test_native_lone_cr_comment_is_not_a_supported_document():
    with pytest.raises(AppError) as caught:
        transformed(ANIMATION.replace(b"\n", b"\r"), CASES[0][2])
    assert caught.value.kind == "invalid_input"
