"""K1 orchestration: narrow port and existing dispatcher, no substrate imports."""
from python.kernel.errors import AppError
from ..shared.prompts import system_prompt
from ..shared.read_actions import available, execute_read as read_action
from .domain.core import run_turn, MAX_TURNS, MAX_TEXT


def setup(ctx):
    """No import-time activation or persistent writes."""


def execute_read(ctx, action, budget):
    return read_action(ctx, action, budget)


def judge_reply(ctx, raw):
    if not available(ctx, 'judge'):
        raise AppError('denied', 'native judge недоступен')
    return ctx.call_tool('judge', {'full_text': raw})


def call(tool, args, ctx):
    gateway = ctx.port('chat_gateway')
    trace = {}
    prompt = system_prompt(ctx)
    final = run_turn(args['text'], gateway.send, lambda: prompt,
        lambda action, budget: execute_read(ctx, action, budget),
        lambda raw: judge_reply(ctx, raw), max_turns=args.get('max_turns', MAX_TURNS),
        budget_chars=args.get('budget_chars', MAX_TEXT), trace=trace)
    return dict(text=final, turns_used=trace['turns_used'],
                actions_executed=trace['actions_executed'], judge_summary=trace['judge_summary'])
