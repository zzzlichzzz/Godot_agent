"""Listener lifetime releases its own session gateway, not a global browser."""
from types import SimpleNamespace
import pytest
from tests.py.channels_t1.test_endpoint_owner import owned_listener

@pytest.mark.parametrize('present',[True,False],ids=['owned-gateway','injected-no-gateway'])
def test_listener_finally_closes_only_its_session_gateway(owned_listener,present):
    listener,server,project,state=owned_listener;calls=[]
    gateway=SimpleNamespace(close=lambda:calls.append('owned-close')) if present else None
    app=SimpleNamespace(extensions={'godot_session':SimpleNamespace(gateway=gateway)})
    listener.serve(app,project,state)
    assert server.closed and calls==(['owned-close'] if present else [])
