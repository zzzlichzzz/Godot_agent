"""Pure native delta -> existing WritePlan compiler; never performs IO."""
import base64
import hashlib
import re
from datetime import datetime
from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.kernel.write_plan import Step, WritePlan, canonical_json

MAX_ACTION=200000
MAX_FILES=100
MAX_PARENTS=256

def validate_id(value):
    if not isinstance(value,str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',value) is None:
        raise AppError('invalid_input','некорректный plan_id')

def timestamp(iso):
    return datetime.fromisoformat(iso).timestamp()

def validate_action(action):
    if not isinstance(action,dict) or not isinstance(action.get('action'),str):
        raise AppError('invalid_input','action должен быть объектом нативного действия')
    if len(canonical_json(action))>MAX_ACTION:
        raise AppError('invalid_input','действие превышает лимит')
    validate_targets(action)
    return dict(action)

def validate_targets(value):
    if isinstance(value,list):
        for item in value:validate_targets(item)
    elif isinstance(value,dict):
        fields={'path','dest','old_path','new_path','scene','resource','script','main_scene','declaration'}
        for key,item in value.items():
            if isinstance(item,str) and (key in fields or (key=='value' and value.get('type')=='ResourcePath')):
                target=re.sub(r':\d+(?::\d+)?$','',item) if key=='declaration' else item
                target=target[6:] if target.startswith('res://') else target
                if ':' in target:raise AppError('denied','Windows ADS/drive path запрещён')
            validate_targets(item)

def compile_plan(files, action, policy, plan_id, parents=()):
    if not isinstance(files,list) or len(files)>MAX_FILES:
        raise AppError('invalid_input','слишком много файлов в плане')
    steps=[];expected={};diffs=[];moves={};moved_dest=set();after_moves=[]
    operations=action.get('operations',action.get('steps',[])) if action.get('action') in ('transaction','plan') else [action]
    by_path={f['path']:f for f in files}
    operations=operations+[dict(action='move_file',path=f['path'],dest=f['move_to']) for f in files if f.get('move_to')]
    for operation in operations:
        if operation.get('action')!='move_file':continue
        source,dest=operation.get('path'),operation.get('dest');old=by_path.get(source);new=by_path.get(dest)
        if old and new and old['after_bytes'] is None and new['before_bytes'] is None and new['after_bytes'] is not None:
            moves[source]=dest;moved_dest.add(dest)
            if old['before_bytes']!=new['after_bytes']:
                after_moves.append(Step('replace_raw',dest,{'bytes_b64':base64.b64encode(new['after_bytes']).decode('ascii')},hashlib.sha256(old['before_bytes']).hexdigest(),'restore'))
    for item in files:
        path=item['path'];rel=normalize_rel(path[6:] if path.startswith('res://') else '')
        if not rel or ':' in rel or path!='res://'+rel or path in expected:
            raise AppError('denied','некорректный или повторный путь плана')
        before,after=item['before_bytes'],item['after_bytes']
        if before==after: continue
        old='' if before is None else hashlib.sha256(before).hexdigest()
        expected[path]=old
        if path in moved_dest:step=None
        elif path in moves:step=Step('move',path,{'dest':moves[path]},old,'move')
        elif after is None: step=Step('delete',path,{},old,'restore')
        elif before is None:
            try: text=after.decode('utf-8')
            except UnicodeDecodeError: raise AppError('invalid_input','создание требует UTF-8') from None
            step=Step('create',path,{'text':text,'newline':'lf'},'','delete')
        else:
            step=Step('replace_raw',path,{'bytes_b64':base64.b64encode(after).decode('ascii')},old,'restore')
        if step is not None:steps.append(step)
        diffs.append({'path':path,'before':None if before is None else before.decode('utf-8','replace'),
                      'after':None if after is None else after.decode('utf-8','replace')})
    steps.extend(after_moves)
    if not isinstance(parents,(list,tuple)) or len(parents)>MAX_PARENTS:
        raise AppError('invalid_input','слишком много parent-каталогов')
    directory_steps=[];seen=set()
    destinations=[item['path'] for item in files if item['after_bytes'] is not None and item['before_bytes']!=item['after_bytes']]
    for path in parents:
        rel=normalize_rel(path[6:] if isinstance(path,str) and path.startswith('res://') else '')
        if not rel or ':' in rel or path!='res://'+rel or path in seen or path in expected:
            raise AppError('denied','некорректный или повторный parent-каталог')
        if not any(target.startswith(path+'/') for target in destinations):
            raise AppError('invalid_input','parent вне footprint плана')
        seen.add(path);expected[path]=''
        directory_steps.append(Step('mkdir',path,{},'','rmdir'))
    steps=sorted(directory_steps,key=lambda s:(s.target.count('/'),s.target))+steps
    body={'action':action,'policy':policy,'steps':[s.as_dict() for s in steps],'expected':expected}
    digest=hashlib.sha256(canonical_json(body).encode('utf-8')).hexdigest()
    return WritePlan(plan_id,digest,tuple(steps),expected),diffs

def require_owned(entries):
    prepared=next((row for row in entries if row.get('state')=='PREPARED'),None)
    if not prepared or prepared.get('detail',{}).get('tool')!='assistant.write':
        raise AppError('not_found','нет ожидающего плана assistant.write')
    return prepared

def confirmation(entries, args, policy, now):
    prepared=next((r for r in entries if r.get('state')=='PREPARED'),None)
    if not prepared or (prepared.get('detail') or {}).get('tool')!='assistant.write':
        raise AppError('not_found','нет ожидающего плана assistant')
    plan=prepared['plan'];detail=prepared['detail']
    if args['digest']!=plan['digest']: raise AppError('stale_plan','digest плана изменился')
    if detail['policy']!=policy: raise AppError('denied','проект или политика изменились')
    state=next((r['state'] for r in reversed(entries) if r.get('state') in ('PREPARED','EXPIRED','APPLYING','COMMITTED','ROLLING_BACK','ROLLED_BACK')),'')
    if state!='PREPARED': raise AppError('conflict','план больше не ожидает подтверждения')
    if any(r.get('state')=='USER_CONFIRMED' for r in entries):
        raise AppError('conflict','план уже подтверждён')
    if now-float(detail['created_at'])>plan['confirm_ttl']:
        raise AppError('not_found','срок подтверждения истёк')
    return plan
