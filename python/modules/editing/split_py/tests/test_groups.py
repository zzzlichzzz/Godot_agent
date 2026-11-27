"""Native symbol chunks and the consumer's declared target-lines boundary."""
import pytest

from python.kernel.errors import AppError
from python.modules.editing.split_py.tests.plan_cases import SUCCESSES, inputs


@pytest.mark.parametrize('case', [c for c in SUCCESSES if c['reference_result']['auto_groups']], ids=lambda c:c['id'])
def test_native_auto_groups(case):
    from python.modules.editing.split_py.domain import groups, inventory, walk
    _, donor, raw, _ = inputs(case)
    info = inventory.file_inventory(inventory.decode(raw))
    actual = groups.suggest_groups(info, walk.stem(donor.rsplit('/',1)[-1]), case['args'].get('target_lines',900))
    expected = [{'module':m['module'], 'symbols':m['names']} for m in case['reference_result']['modules']]
    assert actual == expected


@pytest.mark.parametrize('value', [0,99,5001,-1])
def test_target_range(value):
    from python.modules.editing.split_py.domain.groups import target_lines
    with pytest.raises(AppError) as error:
        target_lines(value)
    assert error.value.kind == 'invalid_input'
    assert error.value.message == 'target_lines must be between 100 and 5000'


@pytest.mark.parametrize('value', ['499','garbage',None,True,100.0])
def test_target_strict_type(value):
    from python.modules.editing.split_py.domain.groups import target_lines
    with pytest.raises(AppError) as error:
        target_lines(value)
    assert error.value.message == 'target_lines must be an integer'
