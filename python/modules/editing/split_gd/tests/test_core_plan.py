import copy

import pytest

from python.kernel.errors import AppError
from ..domain import core
from .plan_corpus import ROOT, NATIVE, SUCCESS, project, source


def project_root(case):
    return ROOT / 'fixtures/projects' / case['fixture'] / case['reference_addon']


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_raw_native_preparation_and_safe_projection(case):
    info = copy.deepcopy(case['reference_inventory'])
    methods = set(case['reference_engine']['methods'])
    props = set(case['reference_engine']['properties'])
    args = (case['reference_donor'], source(case), info, methods, props,
            copy.deepcopy(case['args'].get('groups')), case['args'].get('target_lines') or 1100)
    if case['reference_error']:
        # Target occupation belongs to the IO boundary; all other native checks are pure.
        if case['reference_error']['type'] == 'StaleSplitGdError':
            assert list(core.targets(args[0], info, core.plan_groups(args[0], info, args[5], args[6])))
        else:
            with pytest.raises(AppError) as exc:
                core.prepare(*args)
            assert exc.value.kind == 'invalid_input'
            assert exc.value.message == case['reference_error']['message']
    else:
        raw = core.prepare(*args)
        expected = {k: v for k, v in case['reference_result'].items() if k not in ('addon_dir', 'project_root', 'donor_abs')}
        assert raw == expected
        donor_raw = (project_root(case) / case['reference_donor']).read_bytes()
        newline = '\r\n' if b'\r\n' in donor_raw else '\r' if b'\r' in donor_raw else '\n'
        projected = project(case['reference_result'])
        assert projected['newline'] == '\n'
        projected['newline'] = newline  # C.16: raw oracle remains native LF, output is factual.
        assert core.plan(*args, newline=newline) == projected == case['expect']['result']
    assert info == case['reference_inventory']


@pytest.mark.parametrize('case', SUCCESS, ids=lambda c: c['id'])
def test_independent_public_projection_is_native(case):
    projected = project(case['reference_result'])
    if case['id'] in ('141-bom_crlf', '142-crlf', '143-cr_only'):
        assert projected['newline'] == '\n'
        projected['newline'] = '\r' if case['id'] == '143-cr_only' else '\r\n'
    assert projected == case['expect']['result']


@pytest.mark.parametrize('value,expected', [(0, 1100), (100, 100), (5000, 5000)])
def test_bridge_target_normalization(value, expected):
    assert core.target_lines(value) == expected


@pytest.mark.parametrize('value', [99, 5001, -1, '100', True])
def test_bridge_target_refusal(value):
    with pytest.raises(AppError) as exc:
        core.target_lines(value)
    assert exc.value.kind == 'invalid_input'
