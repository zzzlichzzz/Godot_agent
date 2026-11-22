"""Agent source is not an external HTTP profile, before token/adapters IO."""
from pathlib import Path
import pytest
from python.channels.http.auth import ProjectAuth
from python.kernel.errors import AppError
from tests.py.transfer_t1.test_write import client

@pytest.mark.parametrize('child',[False,True],ids=['source-root','source-child'])
def test_http_refuses_agent_source_profile_before_reading_token(client,child,monkeypatch):
    _,root,_=client;source=Path(__file__).parents[3];profile=source/'http-profile-case' if child else source
    token=profile/'godot_agent_token.txt';calls=[];old_is_file=Path.is_file;old_read=Path.read_text
    def exists(path):return True if path==token else old_is_file(path)
    def read(path,*args,**kwargs):
        if path==token:calls.append(path);return 'SYNTHETIC-UNREAD-SOURCE-TOKEN'
        return old_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'is_file',exists);monkeypatch.setattr(Path,'read_text',read)
    with pytest.raises(AppError,match='outside project/source'):ProjectAuth(root,profile)
    assert calls==[]
