"""External endpoint receipts: no socket and no guessed ownership."""
import json
import pytest

@pytest.fixture
def owned_listener(monkeypatch,tmp_path):
    from python.channels.http import listener
    import werkzeug.serving
    project=tmp_path/'project';project.mkdir();state=tmp_path/'profile';state.mkdir()
    class Server:
        server_port=54321;closed=False;action=lambda self:None
        def serve_forever(self):self.action()
        def server_close(self):self.closed=True
    server=Server();monkeypatch.setattr(werkzeug.serving,'make_server',lambda host,port,app,threaded:server)
    return listener,server,project,state

def test_unchanged_claim_is_removed_only_by_its_owned_server(owned_listener):
    listener,server,project,state=owned_listener;listener.serve(object(),project,state)
    assert server.closed and not (state/'http_endpoint.json').exists()

def test_preexisting_claim_is_not_adopted_or_removed(owned_listener):
    listener,server,project,state=owned_listener;endpoint=state/'http_endpoint.json'
    raw=b'{"session_id":"foreign-synthetic"}\n';endpoint.write_bytes(raw)
    with pytest.raises(FileExistsError):listener.serve(object(),project,state)
    assert server.closed and endpoint.read_bytes()==raw

def test_replaced_identity_with_equal_bytes_is_preserved(owned_listener):
    listener,server,project,state=owned_listener;endpoint=state/'http_endpoint.json';saved=[]
    def replace():
        raw=endpoint.read_bytes();endpoint.rename(state/'retained.json');endpoint.write_bytes(raw);saved.append(raw)
    server.action=replace;listener.serve(object(),project,state)
    assert server.closed and endpoint.read_bytes()==saved[0] and (state/'retained.json').read_bytes()==saved[0]

def test_inplace_foreign_byte_rewrite_is_preserved_even_if_json_equal(owned_listener):
    listener,server,project,state=owned_listener;endpoint=state/'http_endpoint.json';saved=[]
    def rewrite():
        original=endpoint.read_bytes();raw=json.dumps(json.loads(original),indent=2).encode()+b'\n'
        assert raw!=original;endpoint.write_bytes(raw);saved.append(raw)
    server.action=rewrite;listener.serve(object(),project,state)
    assert server.closed and endpoint.exists() and endpoint.read_bytes()==saved[0]
