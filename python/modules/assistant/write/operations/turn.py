"""Native model actions become previews, never implicit confirmation."""
import json
from python.kernel.errors import AppError
from .prepare import call as prepare_call

READ={'read_file':'read','search_project':'search','ask_librarian':'ask','gather_context':'context',
      'read_function':'functions','list_scene':'scene'}
WRITE={'create_file','patch_file','move_file','transaction','plan','project_command','rename_file','rename_symbol','rename_node',
       'reparent_node','delete_node','edit_scene','create_scene','edit_resource','edit_project_settings'}

def read_args(action):
    kind=action['action']
    if kind=='read_file': return {'path':action.get('path',''),'max_chars':30000}
    if kind=='ask_librarian': return {'query':action.get('query','')}
    if kind=='search_project': return {'query':action.get('query','')}
    if kind=='gather_context': return {'sections':['project']}
    if kind=='read_function': return {'path':action.get('path'),'names':action.get('names') or [action.get('name')]}
    return {'path':action.get('path') or action.get('scene')}

def call(args,ctx):
    try:gateway=ctx.port('interactive_gateway')
    except AppError as error:
        if error.kind!='unavailable':raise
        gateway=ctx.port('chat_gateway')
    text=args['text'];parts=[]
    for number in range(1,args.get('max_turns',8)+1):
        context=ctx.call_tool('context',{'sections':['project']})
        prompt=gateway.system_prompt(tree=json.dumps(context,ensure_ascii=False)[:8000])
        packet=gateway.send(text,system_text=prompt)
        if not isinstance(packet,dict) or len(str(packet.get('raw','')))>200000:
            raise AppError('invalid_input','ответ модели превышает контракт')
        action=packet.get('action') or {}
        if not isinstance(action,dict):raise AppError('invalid_input','действие модели должно быть объектом')
        kind=action.get('action')
        raw=packet.get('raw') or packet.get('text') or ''
        if kind in READ:
            entry=ctx.registry.get(READ[kind])
            if entry is None or entry.spec.effects!='read':raise AppError('denied','не является инструментом чтения')
            try:
                if kind=='read_file' and isinstance(action.get('paths'),list):
                    if not 1<=len(action['paths'])<=5:raise AppError('invalid_input','чтение принимает 1..5 путей')
                    feedback=[ctx.call_tool('read',{'path':p,'max_chars':6000}) for p in action['paths']]
                else:feedback=ctx.call_tool(READ[kind],read_args(action))
            except AppError as error: feedback={'error':{'kind':error.kind,'message':str(error)}}
            text='Результат чтения:\n'+json.dumps(feedback,ensure_ascii=False)[:args.get('budget',30000)];continue
        if kind=='plan' and action.get('continues'):
            steps=action.get('steps')
            if not isinstance(steps,list) or len(parts)+len(steps)>100:
                raise AppError('invalid_input','слишком много частей плана')
            parts.extend(steps);text='Продолжи план; ни один шаг ещё не применён.';continue
        if parts:
            if kind!='plan': raise AppError('invalid_input','ожидалась заключительная часть плана')
            action=dict(action,steps=parts+(action.get('steps') or []))
        if kind in WRITE:
            checked=ctx.call_tool('judge',{'full_text':raw})
            if not checked['acceptable']:
                text='Исправь действие по проверке:\n'+json.dumps(checked,ensure_ascii=False)[:12000];continue
            preview=prepare_call({'action':action},ctx)
            if preview['state']=='ALREADY_SATISFIED':
                return {'state':'final','text':packet.get('text',''),'action':None,'plan':None,'turns_used':number}
            return {'state':'pending_confirmation','text':packet.get('text',''),'action':action,'plan':preview,'turns_used':number}
        if kind and kind not in ('done','none'):
            raise AppError('denied','действие не даёт разрешения: '+str(kind))
        checked=ctx.call_tool('judge',{'full_text':raw})
        if checked['acceptable'] and packet.get('done'):
            return {'state':'final','text':packet.get('text',''),'action':None,'plan':None,'turns_used':number}
        text='Исправь ответ; заверши маркером DONE. '+json.dumps(checked,ensure_ascii=False)[:12000]
    raise AppError('unavailable','исчерпан лимит шагов диалога')
