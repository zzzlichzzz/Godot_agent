"""K1 pure bounded loop; IO and native semantics arrive only as callbacks."""
from python.kernel.errors import AppError

MAX_TURNS = 8
MAX_TEXT = 80000
MAX_REPLY = 200000
READ_ACTIONS = frozenset(('read_file', 'search_project', 'ask_librarian',
                          'gather_context', 'read_function', 'list_scene'))
REFUSE_ACTIONS = frozenset(('create_file', 'patch_file', 'move_file', 'copy_file',
    'rename_symbol', 'plan', 'write_apply', 'write_preview', 'rollback',
    'write_rollback', 'project_command', 'run_check', 'chat', 'edit_scene',
    'create_scene', 'edit_project_settings', 'edit_resource', 'transaction'))
REFUSAL = ('Режим read-only: я могу прочитать проект и объяснить изменения, '
           'но не буду выполнять запись, plan или команды.')


def read_requests(action, budget):
    """Translate only explicit native READ operations, never arbitrary commands."""
    name = action.get('action')
    if name == 'read_file':
        paths = action.get('paths')
        if not isinstance(paths, list) or not 1 <= len(paths) <= 5 or not all(isinstance(p, str) for p in paths):
            raise AppError('invalid_input', 'read_file требует от одного до пяти путей')
        return [('read', {'path': path, 'max_chars': min(30000, max(1, budget//len(paths)))}) for path in paths]
    if name == 'search_project':
        return [('search', {'query': action.get('query', '')})]
    if name == 'ask_librarian':
        return [('ask', {'query': action.get('query', ''), 'budget_chars': budget})]
    if name == 'gather_context':
        return [('context', {'sections': ['project', 'tools']})]
    if name == 'read_function':
        return [('functions', {'path': action.get('path', '')})]
    if name == 'list_scene':
        return [('scene', {'path': action.get('path', ''), 'max_chars': budget})]
    raise AppError('denied', 'действие не входит в read-only allowlist')


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
        refusal = name in REFUSE_ACTIONS
        judgment = judge(REFUSAL+'\n===DONE===' if refusal else response.get('raw') or final)
        trace['judge_summary'] = {'score': judgment.get('score', 0),
                                  'acceptable': bool(judgment.get('acceptable', False))}
        if refusal:
            return REFUSAL[:budget_chars]
        if response.get('finish_reason') in ('error', 'interrupted'):
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
