"""C.8 strict schemas and generated artifact; P1/M6 protection."""
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.modules.verification.tscn_lint.tools import CHECK, RESULT, TOOLS

ROOT = Path(__file__).resolve().parents[3]


def test_exact_read_only_spec():
    assert TOOLS == (CHECK,)
    assert CHECK.effects == 'read' and CHECK.idempotent and CHECK.cost == 'cheap'
    assert CHECK.errors == ('invalid_input', 'not_found', 'denied')
    assert CHECK.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES}
    assert set(RESULT['properties']) == set(RESULT['required']) == {'fixed', 'changed', 'problems'}
    assert RESULT['additionalProperties'] is False
    assert CHECK.args['additionalProperties'] is False
    assert CHECK.args['required'] == ['path', 'content']


def test_generated_card_matches_toolspec_bytes():
    card = ROOT / 'contract/capabilities/check.json'
    assert card.is_file()
    assert json.loads(card.read_bytes()) == CHECK.contract('verification.tscn_lint', 'verification.tscn_lint')


@pytest.mark.parametrize('answer', [{}, {'fixed': '', 'changed': False},
    {'fixed': '', 'changed': 0, 'problems': []},
    {'fixed': '', 'changed': False, 'problems': [{'line': 1, 'message': 'broken'}]},
    {'fixed': '', 'changed': False, 'problems': [1]},
    {'fixed': '', 'changed': False, 'problems': {}},
    {'fixed': '', 'changed': False, 'problems': [], 'extra': True}])
def test_result_schema_refuses_non_literal_or_extra_fields(answer):
    assert validate(answer, RESULT)


def test_result_schema_accepts_literal_strings():
    assert not validate({'fixed': 'x\r\n', 'changed': True, 'problems': ['полная строка']}, RESULT)


@pytest.mark.parametrize('args', [{}, {'path': 'res://x.tscn'},
    {'path': 1, 'content': ''}, {'path': 'res://x.tscn', 'content': False},
    {'path': 'res://x.tscn', 'content': '', 'planned_paths': [1]},
    {'path': 'res://x.tscn', 'content': '', 'extra': 'bad'}])
def test_args_schema_refuses_wrong_types_and_extra_fields(args):
    assert validate(args, CHECK.args)
