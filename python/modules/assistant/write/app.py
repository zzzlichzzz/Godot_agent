"""Assistant confirmation orchestration, all effects delegated to the funnel."""
from python.kernel.approval import policy_snapshot, require_explicit_confirmation
from python.kernel.errors import AppError
from .operations.prepare import call as prepare_call
from .operations.turn import call as turn_call
from .domain import core

def call(tool,args,ctx):
    if tool=='assistant_plan': return prepare_call(args,ctx)
    if tool=='assistant_turn': return turn_call(args,ctx)
    core.validate_id(args['plan_id'])
    if tool=='assistant_rollback':
        if not args['entry_id'].startswith(args['plan_id']+'#'):
            raise AppError('invalid_input','entry_id не принадлежит plan_id')
        entries=ctx.port('journal').read(args['plan_id'])
        core.require_owned(entries)
        require_explicit_confirmation(entries,ctx.path_policy)
        value=ctx.call_tool('write_rollback',{'entry_id':args['entry_id']})
        return {'state':'ROLLED_BACK','plan_id':args['plan_id'],'entry_id':args['entry_id'],'result':value}
    if tool!='assistant_confirm': raise AppError('unknown_tool','assistant.write не владеет инструментом')
    lock=ctx.port('lock')
    if not lock.acquire(): raise AppError('conflict','проект занят')
    try:
        journal=ctx.port('journal');entries=journal.read(args['plan_id'])
        core.confirmation(entries,args,policy_snapshot(ctx.path_policy),core.timestamp(ctx.clock.now_iso()))
        if not args['approved']:
            journal.append(args['plan_id'],{'state':'EXPIRED','reason':'user_rejected'})
            return {'state':'REJECTED','plan_id':args['plan_id'],'entry_id':'','result':{'files_count':0}}
        journal.append(args['plan_id'],{'state':'USER_CONFIRMED','approved':True,'digest':args['digest']})
    finally: lock.release()
    value=ctx.call_tool('write_apply',{'plan_id':args['plan_id'],'digest':args['digest']})
    return {'state':'COMMITTED','plan_id':args['plan_id'],'entry_id':value['entry_id'],'result':value}
