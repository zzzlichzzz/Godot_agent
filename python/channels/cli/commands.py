"""Thin CLI formatting/stdin translation; chat policy stays in its module."""
import json

def emit(value, stdout, diagnostics=False):
    if diagnostics or not value.get('ok'):
        print(json.dumps(value, ensure_ascii=False), file=stdout)
    else:
        print(value['result']['text'], file=stdout)
    return 0 if value.get('ok') else 1

def run(args, agent, stdin, stdout):
    if args.command in ('turn', 'plan', 'confirm', 'rollback'):
        from python.channels.cli.write_commands import run as write_run
        return write_run(args, agent, stdout)
    if args.command == 'health':
        print(json.dumps({'status': 'ok', 'tools': len(agent.tools()), 'profile': 'cli',
                          'read_only_chat': True}, ensure_ascii=False), file=stdout)
        return 0
    if args.command == 'tools':
        tools = agent.tools()
        if args.json or args.verbose:
            print(json.dumps(tools, ensure_ascii=False), file=stdout)
        else:
            print('\n'.join(tool['name'] for tool in tools), file=stdout)
        return 0
    def chat(text):
        params = {'text': text}
        for name in ('max_turns', 'budget_chars'):
            if getattr(args, name, None) is not None:
                params[name] = getattr(args, name)
        return emit(agent.call('chat', params), stdout, args.json or args.verbose)
    if args.command == 'chat':
        return chat(args.text)
    status = 0
    for line in stdin:
        text = line.strip()
        if text in (':quit', ':exit'):
            break
        if text:
            status = max(status, chat(text))
    return status
