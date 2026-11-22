"""D51: scan external source bytes only; fixtures never execute or open sockets."""
import hashlib
from unittest.mock import patch
import pytest
from tools import security_audit as audit

LIBRARIAN_SHA='340b5dd2be96ebc4fd2e920889b275f66d9f70e4e1284bc11676db6a96551ad9'

def scan(tmp_path,text,relative='substrate/context/fixture.py'):
    root=tmp_path/'scan'
    path=root/'python'/relative
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode('utf-8'))
    with patch.object(audit,'ROOT',root),patch.object(audit,'PY',root/'python'),\
            patch.object(audit,'LISTEN_ALLOWED',root/'python/channels/http'):
        return audit.check_listener()

@pytest.mark.parametrize('text',[
    "s.bind(('127.0.0.1', 0))\n",'s.listen(1)\n',
    "s. bind(('127.0.0.1',0))\n",'s. listen(1)\n',
    "s.bind(\n    ('127.0.0.1',0)\n)\n",'s.listen(\n  1\n)\n',
    'app.run()\n','HTTPServer(address,handler)\n','http.HTTPServer(address,handler)\n',
    'ThreadingHTTPServer(address,handler)\n',
    'def later():\n    s.bind(address)\n',
    'marker = "здоровье"; s.listen(1)\n',
    'marker = f"{s.bind(address)}"\n',
],ids=['real-zero-bind','real-listen','spaced-bind','spaced-listen',
    'multiline-bind','multiline-listen','run','HTTPServer','qualified-HTTPServer',
    'threaded-HTTPServer','function-body','unicode-prefix','fstring-code'])
def test_real_listener_is_red(tmp_path,text):
    found=scan(tmp_path,text)
    assert len(found)==1 and found[0].startswith('SEC-03 ')

@pytest.mark.parametrize('text',[
    '# s.bind(address)\n', '# s.listen(1)\n',
    'marker = "s.bind(address)"\n', 'marker = "s.listen(1)"\n',
    '"""s.bind(address); s.listen(1)"""\n',
    'def doc():\n    """s.bind(address)"""\n    return 0\n',
    'marker = r"s.bind(address)"\n', 'marker = b"s.listen(1)"\n',
    'marker = "s." "bind(address)"\n',
    'marker = f"literal s.bind(address) {1}"\n',
    'marker = "# .bind("  # .listen(\n',
    'callback = s.bind\n', 'callback = s.listen\n',
    '# app.run(); HTTPServer(address,handler)\n',
    'marker = "app.run(); HTTPServer(address,handler)"\n',
    "s.bind\n(('127.0.0.1',0))\n",
],ids=['bind-comment','listen-comment','bind-string','listen-string','docstring',
    'function-docstring','raw-string','bytes-string','adjacent-string','fstring-literal',
    'mixed-comment-string','bind-reference','listen-reference','server-comment','server-string',
    'linebreak-noncall'])
def test_mentions_are_not_calls(tmp_path,text):
    assert scan(tmp_path,text)==[]

def test_corrected_native_librarian_present_is_ok(tmp_path):
    raw=(audit.ROOT/'python/substrate/context/librarian.py').read_bytes()
    assert len(raw)==97676 and hashlib.sha256(raw).hexdigest()==LIBRARIAN_SHA
    assert scan(tmp_path,raw.decode('utf-8'),'substrate/context/librarian.py')==[]

def test_librarian_path_cannot_hide_a_real_zero_port_bind(tmp_path):
    assert len(scan(tmp_path,"s.bind(('127.0.0.1', 0))\n",'substrate/context/librarian.py'))==1

@pytest.mark.parametrize('text',['def broken(', 's.bind(address)\n\x00', '\ufeffs.listen(1)\n'])
def test_unparseable_source_is_not_green(tmp_path,text):
    found=scan(tmp_path,text)
    assert len(found)==1 and found[0].startswith('SEC-03 ')
