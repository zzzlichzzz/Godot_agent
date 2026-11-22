"""SEC-03 scanner inputs only: no snippet executes and no socket is opened."""
from textwrap import dedent, indent

import pytest

from tools import security_audit


PROBE = """try:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', 9222))
except OSError as error: raise RuntimeError('9222 availability unknown; refusing launch') from error
"""
FACADE = 'substrate/llm/browser/facade.py'


def source(block=PROBE, before='', after='', prefix='import socket\n', argument='self'):
    return prefix + '\nclass ReadOnlyBrowser:\n    def __init__(' + argument + '):\n' + indent(before + block + after, '        ')


def scan(tmp_path, monkeypatch, text, path=FACADE):
    file = tmp_path / 'python' / path
    file.parent.mkdir(parents=True)
    file.write_bytes(text.encode('utf-8'))
    monkeypatch.setattr(security_audit, 'ROOT', tmp_path)
    monkeypatch.setattr(security_audit, 'PY', tmp_path / 'python')
    monkeypatch.setattr(security_audit, 'LISTEN_ALLOWED', tmp_path / 'python/channels/http')
    return security_audit.check_listener()


def denied(found):
    assert len(found) == 1 and 'SEC-03' in found[0] and 'слушающий сокет вне channels/http' in found[0]


@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
def test_only_canonical_nonlistening_probe_is_allowed(tmp_path, monkeypatch, newline):
    assert scan(tmp_path, monkeypatch, source().replace('\n', newline)) == []


def test_actual_frozen_b1_facade_is_allowed(tmp_path, monkeypatch):
    import hashlib
    data = (security_audit.PY / FACADE).read_bytes()
    assert hashlib.sha256(data).hexdigest() == '6abe81d207c963d9fa58775974aa1bf0828ae9d16edd6bdb7031055b1dcb0b98'
    assert scan(tmp_path, monkeypatch, data.decode('utf-8')) == []


BAD_BLOCKS = [
    ('constructor-args', PROBE.replace('socket.socket()', 'socket.socket(socket.AF_INET, socket.SOCK_STREAM)')),
    ('zero-port', PROBE.replace('9222))', '0))')),
    ('other-port', PROBE.replace('9222))', '9223))')),
    ('hostname', PROBE.replace('127.0.0.1', 'localhost')),
    ('wildcard', PROBE.replace('127.0.0.1', '0.0.0.0')),
    ('external', PROBE.replace('127.0.0.1', '192.0.2.1')),
    ('variable-address', PROBE.replace("('127.0.0.1', 9222)", 'address')),
    ('reuse-option', PROBE.replace('SO_EXCLUSIVEADDRUSE', 'SO_REUSEADDR')),
    ('zero-exclusive', PROBE.replace('ADDRUSE, 1)', 'ADDRUSE, 0)')),
    ('bind-before-option', PROBE.replace('        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)\n'
                                        "        probe.bind(('127.0.0.1', 9222))", "        probe.bind(('127.0.0.1', 9222))\n"
                                        '        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)')),
    ('listen-inside', PROBE.replace('except OSError', '        probe.listen(1)\nexcept OSError')),
    ('extra-inside', PROBE.replace('except OSError', '        observe(probe)\nexcept OSError')),
    ('escape-inside', PROBE.replace('except OSError', '        other = probe\nexcept OSError')),
    ('suppressed-error', PROBE[:PROBE.index('except')] + 'except OSError: pass\n'),
    ('wrong-catch', PROBE.replace('except OSError', 'except Exception')),
    ('no-cause', PROBE.replace(' from error', '')),
    ('else', PROBE + 'else: pass\n'),
    ('finally', PROBE + 'finally: pass\n'),
    ('no-try', dedent(PROBE[5:PROBE.index('except')])),
    ('alias', PROBE.replace('probe', 'other')),
    ('duplicate', PROBE + PROBE),
]


@pytest.mark.parametrize(('name', 'block'), BAD_BLOCKS, ids=[case[0] for case in BAD_BLOCKS])
def test_noncanonical_probe_remains_red(tmp_path, monkeypatch, name, block):
    denied(scan(tmp_path, monkeypatch, source(block)))


CHANGES = [
    ('shadow-argument', {'argument': 'self, socket'}),
    ('probe-argument', {'argument': 'self, probe'}),
    ('shadow-assignment', {'before': 'socket = fake\n'}),
    ('probe-assignment', {'before': 'probe = fake\n'}),
    ('shadow-function', {'before': 'def socket(): pass\n'}),
    ('shadow-class', {'before': 'class probe: pass\n'}),
    ('wrong-import', {'prefix': 'from fake import socket\n'}),
    ('aliased-import', {'prefix': 'import socket as socket\n'}),
    ('duplicate-import', {'prefix': 'import socket\nfrom fake import socket\n'}),
    ('probe-import', {'prefix': 'import socket\nimport fake as probe\n'}),
    ('escape-after', {'after': 'other = probe\n'}),
    ('probe-after', {'after': 'getattr(probe, "listen")(1)\n'}),
    ('socket-after', {'after': 'other = socket.socket()\n'}),
    ('attribute-write', {'before': 'socket.socket = fake\n'}),
    ('dynamic-write', {'before': 'globals()["socket"] = fake\n'}),
    ('qualified-dynamic-write', {'before': 'builtins.globals()["socket"] = fake\n'}),
    ('module-dynamic-write', {'before': 'setattr(module, "socket", fake)\n'}),
    ('dict-dynamic-write', {'before': 'module.__dict__["socket"] = fake\n'}),
    ('string-indirection', {'before': 'key = "socket"\n'}),
    ('socket-delete', {'after': 'del socket\n'}),
]


@pytest.mark.parametrize(('name', 'change'), CHANGES, ids=[case[0] for case in CHANGES])
def test_rebinding_or_escape_cannot_authorize_probe(tmp_path, monkeypatch, name, change):
    denied(scan(tmp_path, monkeypatch, source(**change)))


@pytest.mark.parametrize('path', ['substrate/llm/browser/other.py', 'substrate/llm/other/facade.py', 'modules/facade.py'])
def test_exception_is_not_a_file_or_directory_allowlist(tmp_path, monkeypatch, path):
    denied(scan(tmp_path, monkeypatch, source(), path))


@pytest.mark.parametrize('extra', ['other.bind(address)\n', 'other.listen(1)\n', 'app.run()\n', 'HTTPServer(address, handler)\n',
                                  '# other.bind(address)\n', 'marker = "other.bind(address)"\n'])
def test_all_other_listener_matches_stay_red(tmp_path, monkeypatch, extra):
    denied(scan(tmp_path, monkeypatch, source(after=extra)))


def test_inline_comment_match_on_approved_bind_line_is_not_removed(tmp_path, monkeypatch):
    denied(scan(tmp_path, monkeypatch, source(PROBE.replace('9222))', '9222))  # other.bind(address)'))))


@pytest.mark.parametrize('text', [source() + '\ndef broken(', '\ufeff' + source()])
def test_parse_failure_is_fail_closed(tmp_path, monkeypatch, text):
    denied(scan(tmp_path, monkeypatch, text))


CONTEXT_CHANGES = [
    ('decorated-class', source().replace('class ReadOnlyBrowser:', '@decorate\nclass ReadOnlyBrowser:')),
    ('decorated-method', source().replace('    def __init__', '    @decorate\n    def __init__')),
    ('base-class', source().replace('class ReadOnlyBrowser:', 'class ReadOnlyBrowser(Base):')),
    ('metaclass', source().replace('class ReadOnlyBrowser:', 'class ReadOnlyBrowser(metaclass=Meta):')),
    ('generic-class', source().replace('class ReadOnlyBrowser:', 'class ReadOnlyBrowser[socket]:')),
    ('generic-method', source().replace('def __init__(', 'def __init__[socket](')),
    ('except-socket', source(before='try: work()\nexcept Exception as socket: pass\n')),
    ('except-probe', source(before='try: work()\nexcept Exception as probe: pass\n')),
    ('match-socket', source(before='match value:\n    case socket: pass\n')),
    ('match-probe', source(before='match value:\n    case probe: pass\n')),
    ('wrong-class', source().replace('class ReadOnlyBrowser:', 'class Other:')),
    ('wrong-method', source().replace('def __init__(', 'def connect(')),
    ('missing-import', source(prefix='')),
]


@pytest.mark.parametrize(('name', 'text'), CONTEXT_CHANGES, ids=[case[0] for case in CONTEXT_CHANGES])
def test_changed_context_or_hidden_binding_stays_red(tmp_path, monkeypatch, name, text):
    denied(scan(tmp_path, monkeypatch, text))


@pytest.mark.parametrize('host', ['127.0.0.1', '0.0.0.0'])
def test_http_channel_location_and_host_rules_unchanged(tmp_path, monkeypatch, host):
    found = scan(tmp_path, monkeypatch, 'HTTPServer(host="' + host + '")\n', 'channels/http/server.py')
    assert found == ([] if host == '127.0.0.1' else ['SEC-03 python/channels/http/server.py: адрес 0.0.0.0'])



def test_reflection_built_name_is_the_only_deny(tmp_path, monkeypatch):
    denied(scan(tmp_path, monkeypatch,
                source(before="globals()['soc' + 'ket'] = fake_socket_impl\n")))
