"""Read native deltas -> preview in existing WAL. Never writes project files."""
from python.kernel.approval import policy_snapshot
from python.kernel.errors import AppError
from ..domain.core import validate_action, compile_plan, timestamp
from ..domain.rename_guards import complete

def call(args,ctx):
    action=validate_action(_action(args));lock=ctx.port('lock')
    if not lock.acquire(): raise AppError('conflict','проект занят')
    try:
        prepared=ctx.port('native_planner').prepare(action,allow_addons=ctx.path_policy.allow_addons,
                                                   allow_self_edit=ctx.path_policy.allow_self_edit)
        for path in [item['path'] for item in prepared['files']]+prepared.get('parents',[]):
            rel=path[6:] if path.startswith('res://') else ''
            reason=ctx.path_policy.deny_reason(rel)
            if reason or rel.casefold().split('/')[-1]=='plugin.cfg' or rel.casefold().split('/')[0] in ('.agent_history','.godot'):
                raise AppError('denied','путь плана закрыт: '+path)
        policy=policy_snapshot(ctx.path_policy)
        if action['action']=='rename_symbol': complete(prepared,action)
        plan,diffs=compile_plan(prepared['files'],action,policy,ctx.ids('plan'),prepared.get('parents',[]))
        if plan.steps:
            ctx.port('journal').write_prepared(plan.as_dict(),{'tool':'assistant.write','requires_confirmation':True,'action':action,
                'policy':policy,'created_at':timestamp(ctx.clock.now_iso()),'diffs':diffs,'warnings':prepared.get('warnings',[])})
        return {'state':'PREPARED' if plan.steps else 'ALREADY_SATISFIED','plan_id':plan.plan_id,
                'digest':plan.digest,'diffs':diffs,'steps_count':len(plan.steps),'confirm_ttl':plan.confirm_ttl,
                'warnings':[str(w) for w in prepared.get('warnings',[])]}
    finally: lock.release()


def _action(args):
    # The kernel validates the field schemas; enforce the exclusive choices here.
    if set(args) == {'action'}:
        return args['action']
    if set(args) != {'operations'}:
        raise AppError('invalid_input', 'укажите ровно одно поле: action или operations')
    operations = []
    for item in args['operations']:
        if len(item) != 1:
            raise AppError('invalid_input', 'в каждом элементе operations требуется ровно одна операция')
        kind, fields = next(iter(item.items()))
        operations.append(dict(fields, action=kind))
    return {'action': 'transaction', 'operations': operations}
