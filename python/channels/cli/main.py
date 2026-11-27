"""Run: python -m python.channels.cli.main --project PATH chat TEXT."""
import argparse
import json
import sys
from python.channels.cli.commands import run
from python.kernel.errors import AppError

def parser():
    value = argparse.ArgumentParser(description='Godot Agent CLI: read-only chat and confirmed writes')
    value.add_argument('--project', default='.')
    value.add_argument('--state-dir')
    value.add_argument('--json', action='store_true')
    value.add_argument('--verbose', action='store_true')
    commands = value.add_subparsers(dest='command', required=True)
    for name in ('chat', 'repl', 'tools', 'health'):
        command = commands.add_parser(name)
        command.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
        command.add_argument('--verbose', action='store_true', default=argparse.SUPPRESS)
        if name in ('chat', 'repl'):
            command.add_argument('--max-turns', type=int)
            command.add_argument('--budget-chars', type=int)
        if name == 'chat':
            command.add_argument('text')
        if name == 'tools':
            command.add_argument('operation', choices=['list'])
    from python.channels.cli.write_commands import add_parsers
    add_parsers(commands)
    return value

def main(argv=None, *, agent_factory=None, stdin=None, stdout=None):
    args = parser().parse_args(argv)
    stdout = stdout if stdout is not None else sys.stdout
    stdin = stdin if stdin is not None else sys.stdin
    if agent_factory is None:
        from python.runtime.bootstrap import build_agent
        agent_factory = build_agent
    try:
        agent = agent_factory(project_root=args.project, profile='cli', state_dir=args.state_dir)
        return run(args, agent, stdin, stdout)
    except AppError as error:
        value = error.payload(); value['ok'] = False
        print(json.dumps(value, ensure_ascii=False), file=stdout)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
