"""Bounded data/argument translation; policy and all effects stay in Agent."""
import json
from python.kernel.errors import AppError

MAX_ACTION_BYTES = 800000

def add_parsers(commands):
    turn = commands.add_parser('turn', help='chat with a preview, never implicit approval')
    turn.add_argument('text')
    turn.add_argument('--max-turns', type=int)
    plan = commands.add_parser('plan', help='prepare a native action without project writes')
    action = plan.add_mutually_exclusive_group(required=True)
    action.add_argument('--action')
    action.add_argument('--action-file')
    confirm = commands.add_parser('confirm', help='explicitly approve or reject a preview')
    confirm.add_argument('plan_id'); confirm.add_argument('digest')
    choice = confirm.add_mutually_exclusive_group(required=True)
    choice.add_argument('--approve', action='store_true')
    choice.add_argument('--reject', action='store_true')
    rollback = commands.add_parser('rollback', help='restore the confirmed receipt')
    rollback.add_argument('plan_id'); rollback.add_argument('entry_id')

def action_data(args):
    try:
        if args.action is not None:
            raw = args.action.encode('utf-8')
        else:
            with open(args.action_file, 'rb') as stream:
                raw = stream.read(MAX_ACTION_BYTES + 1)
        if len(raw) > MAX_ACTION_BYTES:
            raise AppError('invalid_input', 'action JSON exceeds the CLI data limit')
        return json.loads(raw.decode('utf-8'))
    except (OSError, UnicodeError, ValueError) as error:
        raise AppError('invalid_input', 'action must be bounded UTF-8 JSON data') from error

def run(args, agent, stdout):
    if args.command == 'plan':
        tool, params = 'assistant_plan', {'action': action_data(args)}
    elif args.command == 'confirm':
        tool, params = 'assistant_confirm', {'plan_id': args.plan_id, 'digest': args.digest,
                                             'approved': args.approve is True}
    elif args.command == 'rollback':
        tool, params = 'assistant_rollback', {'plan_id': args.plan_id, 'entry_id': args.entry_id}
    else:
        tool, params = 'assistant_turn', {'text': args.text}
        if args.max_turns is not None:
            params['max_turns'] = args.max_turns
    answer = agent.call(tool, params)
    print(json.dumps(answer, ensure_ascii=False), file=stdout)
    return 0 if answer.get('ok') else 1
