"""Bounded MCP newline JSON-RPC transport; no network or second dispatcher."""
import json
import math
from pathlib import Path
import sys
from .server import McpServer

MAX_LINE=1_000_000
MAX_DEPTH=64

def finite_json(raw):
    def reject(value):raise ValueError('Nonfinite JSON')
    body=json.loads(raw,parse_constant=reject);pending=[(body,0)]
    while pending:
        value,depth=pending.pop()
        if depth>MAX_DEPTH or isinstance(value,float) and not math.isfinite(value):raise ValueError('JSON limits')
        if isinstance(value,dict):pending.extend((item,depth+1) for item in value.values())
        elif isinstance(value,list):pending.extend((item,depth+1) for item in value)
    return body

def serve_stdio(agent,input_stream=None,output_stream=None):
    source=input_stream or sys.stdin.buffer;target=output_stream or sys.stdout
    server=McpServer(agent)
    while True:
        raw=source.readline(MAX_LINE+1)
        if not raw:break
        if len(raw)>MAX_LINE:
            while raw and not raw.endswith(b'\n'):raw=source.readline(MAX_LINE+1)
            reply=dict(jsonrpc='2.0',id=None,error=dict(code=-32700,message='Request exceeds limit'))
        else:
            try:
                body=finite_json(raw)
                reply=server.handle(body)
            except (ValueError,TypeError,RecursionError):reply=dict(jsonrpc='2.0',id=None,error=dict(code=-32700,message='Invalid JSON-RPC request'))
        if reply is not None:
            target.write(json.dumps(reply,ensure_ascii=False,allow_nan=False)+'\n');target.flush()

def main(argv=None):
    import argparse
    from python.runtime.bootstrap import build_agent,default_ports
    parser=argparse.ArgumentParser(description='Godot Agent MCP over local stdio')
    parser.add_argument('--project',required=True);parser.add_argument('--state',required=True)
    args=parser.parse_args(argv)
    try:
        root=Path(args.project).resolve();state=Path(args.state).resolve();source=Path(__file__).parents[3].resolve()
        if any(state==owner or owner in state.parents for owner in (root,source)):raise ValueError('External profile required')
        agent=build_agent(str(root),ports=default_ports(str(root),state_dir=str(state),profile='cli'))
    except (OSError,ValueError):parser.exit(2,'MCP startup refused: invalid project or external profile\n')
    try:serve_stdio(agent)
    except BrokenPipeError:return 0
    return 0

if __name__=='__main__':raise SystemExit(main())
