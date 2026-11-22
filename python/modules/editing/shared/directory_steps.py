"""Only receipt-proven plain directory effects, within the existing funnel."""
from python.kernel.errors import AppError
from .script_edits import rel_of

def prove_parents(ctx,plan,entry_id,target):
    prove(ctx.port('writer'),plan,ctx.port('journal').read(plan['plan_id']),entry_id,target,'stale_plan')

def prove(writer,plan,entries,entry_id,target,kind='conflict'):
    proofs={row['receipt']['step_id']:row['receipt']['applied_hash'] for row in entries
            if row.get('state')=='RECEIPT' and row.get('entry_id')==entry_id}
    parents={s['target']:True for s in plan['steps'] if s['op']=='mkdir' and target.startswith(s['target']+'/')}
    if any(row.get('state')=='PREPARED' and isinstance(row.get('detail'),dict) and row['detail'].get('tool')=='assistant.write' for row in entries):
        parts=rel_of(target).split('/')
        for index in range(1,len(parts)):parents.setdefault('res://'+ '/'.join(parts[:index]),False)
    for parent,receipted in parents.items():
        try:identity=writer.directory_identity(rel_of(parent))
        except OSError:identity=None
        if receipted and (not proofs.get(parent) or proofs[parent]!=identity):raise AppError(kind,'созданный parent-каталог заменён',details={'path':parent})
        if not identity:raise AppError(kind,'parent-каталог не доказан plain',details={'path':parent})

def apply(ctx,plan,plan_id,entry_id,step):
    writer,journal=ctx.port('writer'),ctx.port('journal');target=step['target'];rel=rel_of(target)
    if writer.exists(rel) or step.get('expected_hash')!='' or plan['expected'].get(target)!='':
        raise AppError('stale_plan','mkdir требует отсутствующий каталог',details={'path':target})
    journal.append(plan_id,dict(state='EFFECT_INTENT',entry_id=entry_id,op='mkdir',target=target,
                               dest='',expected_hash='',applied_hash='',undo_token=''))
    proof=writer.mkdir(rel)
    receipt=dict(step_id=target,applied_hash=proof,undo_token=proof)
    journal.append(plan_id,dict(state='RECEIPT',entry_id=entry_id,receipt=receipt))
    return receipt

def restore(writer,target,proof,applied):
    rel=rel_of(target)
    if not writer.exists(rel):return ''
    if not proof or proof!=applied or writer.directory_identity(rel)!=proof:
        raise AppError('conflict','каталог без matching receipt не удаляется',details={'path':target})
    try:writer.remove_empty_directory(rel,proof)
    except OSError as error:raise AppError('conflict','каталог занят или заменён',details={'path':target}) from error
    return ''

def pending(writer,target):
    if not writer.exists(rel_of(target)):return True
    raise AppError('conflict','каталог без receipt: recovery blocked',details={'path':target,'reason':'unreceipted_directory'})
