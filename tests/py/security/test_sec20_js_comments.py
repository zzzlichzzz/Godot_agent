"""D28: full-line JS comments are not code; actual and inline markers stay red."""
import pytest

from tools import security_audit


def _scan(tmp_path, monkeypatch, source):
    contract = tmp_path / 'contract'
    contract.mkdir()
    (contract / 'browser_stealth.json').write_bytes(
        (security_audit.ROOT / 'contract/browser_stealth.json').read_bytes())
    browser = tmp_path / 'python/substrate/llm/browser'
    browser.mkdir(parents=True)
    (browser / 'fixture.py').write_bytes(source.encode('utf-8'))
    monkeypatch.setattr(security_audit, 'ROOT', tmp_path)
    monkeypatch.setattr(security_audit, 'PY', tmp_path / 'python')
    return security_audit.check_browser_stealth()


def _js(body):
    # This is only scanner input: never executed in Python or a browser.
    return 'SCRIPT = r"""\n' + body + '\n"""\n'


def _forbidden_pair():
    return [
        'SEC-20 python/substrate/llm/browser/fixture.py: запрещённая маскировка hasFocus',
        'SEC-20 python/substrate/llm/browser/fixture.py: запрещённая маскировка toString',
    ]


def test_a_executable_js_markers_remain_red(tmp_path, monkeypatch):
    source = _js("Object.defineProperty(window, 'hasFocus', {value: 0});\n"
                 'const marker = window.toString;')
    assert _scan(tmp_path, monkeypatch, source) == _forbidden_pair()


@pytest.mark.parametrize('indent', ['', ' ', '\t'], ids=['column0', 'spaces', 'tabs'])
@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
def test_b_tokens_only_in_full_line_js_comments_are_ignored(
        tmp_path, monkeypatch, indent, newline):
    source = _js(indent + '// hasFocus is intentionally not changed.\n'
                 + indent + '// Native toString must stay intact.\nvoid 0;')
    assert _scan(tmp_path, monkeypatch, source.replace('\n', newline)) == []


def test_full_line_comments_do_not_trigger_any_of_the_four_scans(tmp_path, monkeypatch):
    source = _js('// hasFocus toString\n'
                 "// arena = {'needs_visibility_spoof': True}\n"
                 '// webdriver.Chrome()\n'
                 '// profile = "Google/Chrome/User Data"\nvoid 0;')
    assert _scan(tmp_path, monkeypatch, source) == []


@pytest.mark.parametrize(('body', 'reason'), [
    ("arena = {'needs_visibility_spoof': True}", 'у сайта arena спуф поднят с false на true'),
    ('webdriver.Chrome()', 'selenium запускает браузер сам'),
    ('profile = "Google/Chrome/User Data"', 'обращение к профилю пользователя'),
], ids=['pinned-site', 'selenium-launch', 'user-profile'])
def test_actual_code_stays_red_in_the_other_three_scans(tmp_path, monkeypatch, body, reason):
    found = _scan(tmp_path, monkeypatch, _js(body))
    assert len(found) == 1 and reason in found[0]


@pytest.mark.parametrize('body', [
    'void 0; // hasFocus toString',
    'const address = "https://example.invalid/hasFocus/toString";',
    '/* hasFocus toString */',
], ids=['inline-comment', 'https-string', 'block-comment'])
def test_unapproved_comment_projections_are_not_applied(tmp_path, monkeypatch, body):
    assert _scan(tmp_path, monkeypatch, _js(body)) == _forbidden_pair()


def test_python_comment_projection_is_preserved(tmp_path, monkeypatch):
    assert _scan(tmp_path, monkeypatch, '# hasFocus toString\n' + _js('void 0;')) == []


def test_commented_debugger_address_cannot_authorize_actual_selenium_launch(tmp_path, monkeypatch):
    source = _js('webdriver.Chrome()\n// debuggerAddress is not executable configuration')
    found = _scan(tmp_path, monkeypatch, source)
    assert len(found) == 1 and 'selenium запускает браузер сам' in found[0]
