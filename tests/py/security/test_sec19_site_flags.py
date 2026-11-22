"""D30: inert native-shaped registries must not raise visibility masking."""
import json

import pytest

from tools import security_audit


def _scan(tmp_path, monkeypatch, source):
    contract = tmp_path / 'contract'
    contract.mkdir()
    (contract / 'browser_stealth.json').write_bytes(
        (security_audit.ROOT / 'contract/browser_stealth.json').read_bytes())
    target = tmp_path / 'python/substrate/llm/browser'
    target.mkdir(parents=True)
    (target / 'sites.py').write_bytes(source.encode('utf-8'))
    monkeypatch.setattr(security_audit, 'ROOT', tmp_path)
    monkeypatch.setattr(security_audit, 'PY', tmp_path / 'python')
    return security_audit.check_browser_stealth()


def _registry(site, flag, reverse=False, newline='\n'):
    fields = ["'id': " + repr(site), "'needs_visibility_spoof': " + flag]
    if reverse:
        fields.reverse()
    return ('SITES = [\n    {\n        ' + ',\n        '.join(fields)
            + ',\n    },\n]\n').replace('\n', newline)


@pytest.mark.parametrize('site', ['kimi', 'arena', 'arena_battle'])
@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
@pytest.mark.parametrize('reverse', [False, True], ids=['id-first', 'flag-first'])
def test_network_only_multiline_raises_are_denied(tmp_path, monkeypatch, site, newline, reverse):
    found = _scan(tmp_path, monkeypatch, _registry(site, 'True', reverse, newline))
    assert any('у сайта ' + site + ' спуф поднят с false на true' in item for item in found)


@pytest.mark.parametrize('site', ['aistudio', 'deepseek', 'qwen'])
def test_admitted_dom_masking_stays_admitted(tmp_path, monkeypatch, site):
    assert _scan(tmp_path, monkeypatch, _registry(site, 'True')) == []


@pytest.mark.parametrize('site', ['kimi', 'arena', 'arena_battle', 'unknown'])
def test_false_flags_stay_admitted(tmp_path, monkeypatch, site):
    assert _scan(tmp_path, monkeypatch, _registry(site, 'False')) == []


def test_unknown_true_is_not_admitted(tmp_path, monkeypatch):
    assert _scan(tmp_path, monkeypatch, _registry('unknown', 'True'))


@pytest.mark.parametrize('expression', ['flag', '1', 'bool(1)'])
def test_nonliteral_boolean_does_not_prove_a_pin(tmp_path, monkeypatch, expression):
    assert _scan(tmp_path, monkeypatch, 'flag = True\n' + _registry('kimi', expression))


def test_nonliteral_id_does_not_prove_an_admission(tmp_path, monkeypatch):
    source = _registry('kimi', 'True').replace("'id': 'kimi'", "'id': site")
    assert _scan(tmp_path, monkeypatch, "site = 'kimi'\n" + source)


def test_python_comment_cannot_create_or_hide_a_flag(tmp_path, monkeypatch):
    source = '# kimi needs_visibility_spoof True\n' + _registry('kimi', 'False')
    assert _scan(tmp_path, monkeypatch, source) == []


def test_js_comment_projection_does_not_hide_python_registry(tmp_path, monkeypatch):
    source = 'SCRIPT = """\n// kimi needs_visibility_spoof True\n"""\n'
    found = _scan(tmp_path, monkeypatch, source + _registry('kimi', 'True'))
    assert len(found) == 1 and 'у сайта kimi' in found[0]


def test_registry_syntax_error_is_denied(tmp_path, monkeypatch):
    assert _scan(tmp_path, monkeypatch, 'SITES = [\n')


def test_pinned_flags_are_independent_contract_data():
    data = json.loads((security_audit.ROOT / 'contract/browser_stealth.json').read_bytes())
    flags = {site: rule['needs_visibility_spoof'] for site, rule in data['sites'].items()}
    assert flags == {'aistudio': True, 'deepseek': True, 'qwen': True,
                     'kimi': False, 'arena': False, 'arena_battle': False}
