"""D62/D63 scanner inputs: AST only, never execute a snippet or bind/listen."""
import ast

import pytest

from tools import security_audit as audit

PIN = 'substrate/verification/godot_headless_validation.py'
CALL = 'subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)'


def source(call=CALL, prefix='import subprocess\n'):
    return prefix+'def timeout(proc):\n    '+call+'\n'


def scan(tmp_path, monkeypatch, text, relative=PIN, process=False):
    path = tmp_path/'python'/relative
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode('utf-8'))
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'PY', tmp_path/'python')
    monkeypatch.setattr(audit, 'LISTEN_ALLOWED', tmp_path/'python/channels/http')
    monkeypatch.setattr(audit, 'PROC_ALLOWED', [tmp_path/'python/substrate/engine',
                                             tmp_path/'python/substrate/llm/browser'])
    return audit.check_processes() if process else audit.check_listener()


@pytest.mark.parametrize('text', [source(), source(CALL.replace('str(proc.pid)', 'str(pid)')),
    source().replace('\n', '\r\n'), source(prefix='import subprocess\nmarker = "здоровье"\n')],
    ids=['exact-native-pid', 'str-Name', 'CRLF', 'unicode'])
def test_approved_run_is_not_a_listener(tmp_path, monkeypatch, text):
    assert scan(tmp_path, monkeypatch, text) == []


BAD_CALLS = [
    ('argv-variable', 'subprocess.run(cmd_var)'),
    ('string-command', 'subprocess.run("taskkill /PID 1")'),
    ('tuple-command', 'subprocess.run(("taskkill",))'),
    ('no-argv', 'subprocess.run()'),
    ('second-argument', 'subprocess.run(["taskkill"], 1)'),
    ('integer-element', 'subprocess.run([1])'),
    ('attribute-element', 'subprocess.run([proc.pid])'),
    ('subscript-element', 'subprocess.run([argv[0]])'),
    ('starred-element', 'subprocess.run([*argv])'),
    ('other-wrapped-attribute', 'subprocess.run([str(other.pid)])'),
    ('other-proc-attribute', 'subprocess.run([str(proc.other)])'),
    ('wrapped-subscript', 'subprocess.run([str(argv[0])])'),
    ('str-extra-arg', 'subprocess.run([str(pid, 1)])'),
    ('str-keyword', 'subprocess.run([str(object=pid)])'),
    ('qualified-str', 'subprocess.run([builtins.str(pid)])'),
    ('other-receiver', 'socket.run(["taskkill"])'),
    ('nested-receiver', 'subprocess.child.run(["taskkill"])'),
    ('shell-true', 'subprocess.run(["taskkill"], shell=True)'),
    ('shell-false', 'subprocess.run(["taskkill"], shell=False)'),
    ('keyword-name', 'subprocess.run(["taskkill"], stdout=output)'),
    ('keyword-subscript', 'subprocess.run(["taskkill"], stdout=outputs[0])'),
    ('keyword-foreign-attribute', 'subprocess.run(["taskkill"], stdout=other.DEVNULL)'),
    ('keyword-other-subprocess-attribute', 'subprocess.run(["taskkill"], stdout=subprocess.STDOUT)'),
    ('keyword-spread', 'subprocess.run(["taskkill"], **options)'),
]


@pytest.mark.parametrize(('name', 'call'), BAD_CALLS, ids=[value[0] for value in BAD_CALLS])
def test_noncanonical_run_stays_red(tmp_path, monkeypatch, name, call):
    found = scan(tmp_path, monkeypatch, source(call))
    assert len(found) == 1 and found[0].startswith('SEC-03 ')


@pytest.mark.parametrize('relative', ['substrate/verification/neighbor.py',
    'substrate/engine/godot_headless_validation.py', 'modules/verification/godot_headless_validation.py'])
def test_run_exception_is_exact_path(tmp_path, monkeypatch, relative):
    assert len(scan(tmp_path, monkeypatch, source(), relative)) == 1


@pytest.mark.parametrize('extra', ['socket.bind(address)', 'socket.listen(1)', 'socket.run()',
    'HTTPServer(address, handler)', 'subprocess.run(cmd_var)', CALL])
def test_another_call_is_not_hidden(tmp_path, monkeypatch, extra):
    assert len(scan(tmp_path, monkeypatch, source()+'\n'+extra+'\n')) == 1


@pytest.mark.parametrize('text', [source(prefix='import subprocess as sp\n').replace('subprocess.', 'sp.'),
    source(prefix='from subprocess import run\n').replace('subprocess.run', 'run'),
    source(prefix=''), source(prefix='def imports():\n    import subprocess\n'),
    source(prefix='import subprocess\nsubprocess = socket\n'),
    source(prefix='import subprocess\nstr = other\n'),
    source()+'\ndef broken(', source()+'\x00'])
def test_unproven_import_binding_or_parse_is_red(tmp_path, monkeypatch, text):
    assert len(scan(tmp_path, monkeypatch, text)) == 1


@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
def test_offset_is_utf8_bytes_not_characters(tmp_path, monkeypatch, newline):
    text = ('import subprocess\nmarker = "здоровье"; '+CALL+'\n').replace('\n', newline)
    assert scan(tmp_path, monkeypatch, text) == []
    path = audit.PY/PIN
    offset = audit._headless_run_start(path, text)
    assert offset == text.encode('utf-8').index(b'.run(')


def test_single_bare_top_level_import_is_allowed(tmp_path, monkeypatch):
    assert scan(tmp_path, monkeypatch, 'import subprocess\n', process=True) == []


BAD_IMPORTS = [
    ('from', 'from subprocess import run\n'),
    ('from-star', 'from subprocess import *\n'),
    ('alias', 'import subprocess as sp\n'),
    ('self-alias', 'import subprocess as subprocess\n'),
    ('multi-first', 'import subprocess, os\n'),
    ('multi-last', 'import os, subprocess\n'),
    ('duplicate', 'import subprocess\nimport subprocess\n'),
    ('nested', 'def imports():\n    import subprocess\n'),
    ('top-plus-nested', 'import subprocess\ndef imports():\n    import subprocess\n'),
    ('top-plus-from', 'import subprocess\nfrom subprocess import run\n'),
    ('unparseable', 'import subprocess\ndef broken('),
]


@pytest.mark.parametrize(('name', 'text'), BAD_IMPORTS, ids=[value[0] for value in BAD_IMPORTS])
def test_noncanonical_import_is_denied(tmp_path, monkeypatch, name, text):
    found = scan(tmp_path, monkeypatch, text, process=True)
    assert len(found) == 1 and found[0].startswith('SEC-04 ')


@pytest.mark.parametrize('text', ['import subprocess\n', 'import os, subprocess\n',
                                 'from subprocess import run\n'])
def test_neighbor_has_no_process_exemption(tmp_path, monkeypatch, text):
    assert len(scan(tmp_path, monkeypatch, text, 'substrate/verification/neighbor.py', True)) == 1


@pytest.mark.parametrize('relative', [PIN, 'substrate/engine/worker.py', 'substrate/llm/browser/worker.py'])
def test_shell_true_is_still_denied_everywhere(tmp_path, monkeypatch, relative):
    found = scan(tmp_path, monkeypatch, 'import subprocess\nsubprocess.run(["x"], shell=True)\n', relative, True)
    assert any('shell=True' in problem for problem in found)


def test_clarified_native_ast_shape_is_exact():
    tree = ast.parse(CALL, mode='eval')
    value = tree.body.args[0].elts[2].args[0]
    assert isinstance(value, ast.Attribute) and value.attr == 'pid'
    assert isinstance(value.value, ast.Name) and value.value.id == 'proc'
