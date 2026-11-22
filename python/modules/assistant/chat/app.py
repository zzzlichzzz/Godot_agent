"""K1 orchestration: narrow port and existing dispatcher, no substrate imports."""
import json
from python.kernel.errors import AppError
from .domain.core import run_turn, read_requests, MAX_TURNS, MAX_TEXT


def setup(ctx):
    """No import-time activation or persistent writes."""


def execute_read(ctx, action, budget):
    names, values = [], []
    requests = read_requests(action, budget)
    for name, args in requests:
        entry = ctx.registry.get(name) if ctx.registry is not None else None
        if entry is None or entry.spec.effects != 'read' or name == 'chat':
            raise AppError('denied', 'инструмент не является доступным READ: '+name)
    for name, args in requests:
        names.append(name)
        try:
            values.append(ctx.call_tool(name, args))
        except AppError as error:
            values.append({'kind': error.kind, 'message': error.message})
    return names, json.dumps(values, ensure_ascii=False)[:budget]


def judge_reply(ctx, raw):
    entry = ctx.registry.get('judge') if ctx.registry is not None else None
    if entry is None or entry.spec.effects != 'read':
        raise AppError('denied', 'native judge недоступен')
    return ctx.call_tool('judge', {'full_text': raw})


def call(tool, args, ctx):
    gateway = ctx.port('chat_gateway')
    trace = {}
    def system_prompt():
        context = ctx.call_tool('context', {'sections': ['project']})
        tree = json.dumps(context, ensure_ascii=False)[:8000]
        return gateway.system_prompt(tree=tree)
    final = run_turn(args['text'], gateway.send, system_prompt,
        lambda action, budget: execute_read(ctx, action, budget),
        lambda raw: judge_reply(ctx, raw), max_turns=args.get('max_turns', MAX_TURNS),
        budget_chars=args.get('budget_chars', MAX_TEXT), trace=trace)
    return dict(text=final, turns_used=trace['turns_used'],
                actions_executed=trace['actions_executed'], judge_summary=trace['judge_summary'])
