"""T-E new documentation/startup contracts, authored before correcting README."""
import shlex
from pathlib import Path
from python.channels.cli.main import parser
ROOT=Path(__file__).resolve().parents[3]

def readme(): return (ROOT/'README.md').read_text(encoding='utf-8')

def test_documented_cli_startup_matches_actual_parser_and_external_state():
    commands=[]
    for line in readme().splitlines():
        if line.startswith('python -m python.channels.cli.main '):
            args=shlex.split(line)[3:]
            assert '--state-dir' in args, 'all startup examples require explicit external state'
            commands.append(parser().parse_args(args))
    assert {row.command for row in commands}>={'health','tools','chat','repl','turn','plan','confirm','rollback'}

def test_documented_write_boundary_is_explicit_and_keeps_K1_read_only():
    text=readme()
    for token in ('assistant_plan','assistant_confirm','assistant_rollback','assistant_turn',
                  'plan_id','digest','entry_id','--approve','--reject','USER_CONFIRMED',
                  'read-only `chat`','единственный executor','конфликт'):
        assert token in text,token

def test_documentation_reports_native_reference_and_unverified_gaps_truthfully():
    text=readme()
    for token in ('GODOT_AGENT_GODOT_BIN','GODOT_AGENT_STATE_DIR','127.0.0.1','http_endpoint.json',
                  'python -m python.channels.http','python -m python.channels.mcp',
                  'скриптовые ресурсы','WinError1314','NN','doh.py','n8n/scripts',
                  'independent_acceptance=false','не являются доказательством provider/browser live',
                  'user://godot_agent/port.json','отдельный Godot user-data namespace'):
        assert token in text,token
    assert 'Статус: **скелет**' not in text
    assert 'contract/' in text and 'ToolSpec' in text and 'R-01…R-22' in text
