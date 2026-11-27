"""K1 pure bounded loop; IO and native semantics arrive only as callbacks."""
from python.kernel.errors import AppError
from ...shared.read_actions import READ_ACTIONS

MAX_TURNS = 8
MAX_TEXT = 80000
MAX_REPLY = 200000
REFUSE_ACTIONS = frozenset(('create_file', 'patch_file', 'move_file', 'copy_file',
    'rename_symbol', 'plan', 'write_apply', 'write_preview', 'rollback',
    'write_rollback', 'project_command', 'run_check', 'chat', 'edit_scene',
    'create_scene', 'edit_project_settings', 'edit_resource', 'transaction',
    'rename_file', 'rename_node', 'reparent_node', 'delete_node'))
REFUSAL = ('Режим read-only: я могу прочитать проект и объяснить изменения, '
           'но не буду выполнять запись, plan или команды.')


def run_turn(text, send, system_prompt, execute, judge, *, max_turns=MAX_TURNS,
             budget_chars=MAX_TEXT, trace=None):
    """Return final STRING. Only app.call may construct the public object."""
    trace = trace if trace is not None else {}
    trace.update(turns_used=0, actions_executed=[], judge_summary={})
    prompt, final = text, ''
    feedback_left = budget_chars
    for turn in range(max_turns):
        response = send(prompt[:MAX_TEXT], system_text=system_prompt(), max_chars=MAX_REPLY)
        trace['turns_used'] = turn+1
        final = response.get('text') or ''
        action = response.get('action')
        name = action.get('action') if isinstance(action, dict) else None
        name = name if isinstance(name, str) else None
        refusal = name in REFUSE_ACTIONS
        judgment = judge(REFUSAL+'\n===DONE===' if refusal else response.get('raw') or final)
        trace['judge_summary'] = {'score': judgment.get('score', 0),
                                  'acceptable': bool(judgment.get('acceptable', False))}
        if refusal:
            return REFUSAL[:budget_chars]
        if response.get('finish_reason') in ('error', 'interrupted', 'length'):
            feedback = 'Поток ответа не завершён; повторите полный ответ без частичных действий.'
        elif response.get('parse_error'):
            feedback = 'Ошибка agent_action: '+str(response['parse_error'])
        elif name in READ_ACTIONS:
            try:
                names, feedback = execute(action, feedback_left)
                trace['actions_executed'].extend(names)
            except AppError as error:
                feedback = 'Чтение недоступно: '+error.message
        elif action is not None:
            feedback = 'Неизвестное действие: '+str(name)
            final = feedback
        elif response.get('done') and judgment.get('acceptable'):
            return final[:budget_chars]
        else:
            feedback = 'Оценка judge: %s. Исправьте ответ и завершите ===DONE===.' % judgment.get('score', 0)
        feedback = str(feedback)[:feedback_left]
        feedback_left -= len(feedback)
        if not feedback_left:
            return (final or 'Бюджет контекста исчерпан.')[:budget_chars]
        prompt = 'Результат предыдущего хода:\n'+feedback+'\nПродолжите исходную задачу: '+text
    return (final+'\nЛимит ходов исчерпан.')[:budget_chars]
