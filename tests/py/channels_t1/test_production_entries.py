"""Own production RED before replacing the HTTP/MCP skeleton."""
import importlib
import pytest

def test_http_factory_is_present_in_production_not_only_external_candidate():
    app=importlib.import_module('python.channels.http.app')
    assert callable(getattr(app,'create_app',None))

def test_bounded_mcp_stream_is_present_in_production_not_only_external_candidate():
    try: stdio=importlib.import_module('python.channels.mcp.stdio')
    except ModuleNotFoundError: pytest.fail('bounded MCP transport missing from production')
    assert callable(getattr(stdio,'serve_stdio',None))
