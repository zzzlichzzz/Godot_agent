"""Payload assembly against raw native observations, not copied old test code."""
import copy

import pytest

from python.modules.editing.split_gd.domain import core
from python.kernel.errors import AppError
from .corpus import NATIVE


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_payload_projection(case):
    raw = copy.deepcopy(case['reference_result'])
    inventory = copy.deepcopy(case['reference_inventory'])
    references = {k: raw[k] for k in ('counts', 'occurrences', 'truncated', 'hard_files', 'soft_files')}
    actual = core.assemble(raw['donor'], inventory, references)
    assert actual == case['expect']['result']
    assert 'schema' not in actual
    assert raw == case['reference_result'] and inventory == case['reference_inventory']


def test_public_methods_sorted_unique_private_excluded():
    funcs = [{'name': n} for n in ('zebra', '_private', 'alpha', 'zebra')]
    assert core.public_methods({'funcs': funcs}) == ['alpha', 'zebra']


@pytest.mark.parametrize('value,message', [(99, 'target_lines must be between 100 and 5000'),
    (5001, 'target_lines must be between 100 and 5000'), ('100', 'target_lines must be an integer')])
def test_target_refusal_exact_text(value, message):
    with pytest.raises(AppError) as exc:
        core.target_lines(value)
    assert exc.value.kind == 'invalid_input' and exc.value.message == message


@pytest.mark.parametrize('value', [0, None])
def test_target_default_is_1100(value):
    assert core.target_lines(value) == 1100
