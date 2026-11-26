"""Native model actions become previews, never implicit confirmation."""
import json
from python.kernel.errors import AppError
from ...shared.prompts import system_prompt
from ...shared.read_actions import READ_ACTIONS, execute_read
from .prepare import call as prepare_call

WRITE={'create_file','patch_file','move_file','transaction','plan','project_command','rename_file','rename_symbol','rename_node',
       'reparent_node','delete_node','edit_scene','create_scene','edit_resource','edit_project_settings'}

def read_feedback(ctx,action,user_prompt):
    try:
        _,feedback=execute_read(ctx,action,30000)
    except AppError as error:
        feedback=json.dumps({'error':{'kind':error.kind,'message':error.message}},ensure_ascii=False)
    return 'Результат чтения:\n'+feedback+'\nИсходный запрос: '+user_prompt[:2000]

def call(args,ctx):
    try:gateway=ctx.port('interactive_gateway')
    except AppError as error:
        if error.kind!='unavailable':raise
        gateway=ctx.port('chat_gateway')
    user_prompt=args['text'];text=user_prompt;parts=[]
    consent=getattr(gateway,'approved_read',None)
    prompt=system_prompt(ctx,preview=True,on_demand=consent is not None)
    if consent is not None and consent.get() is not None:
        text=read_feedback(ctx,consent.get(),user_prompt)
    for number in range(1,args.get('max_turns',8)+1):
        packet=gateway.send(text,system_text=prompt)
        if not isinstance(packet,dict) or len(str(packet.get('raw','')))>200000:
            raise AppError('invalid_input','ответ модели превышает контракт')
        if packet.get('finish_reason')=='error':
            raise AppError('unavailable',str(packet.get('text') or 'ошибка шлюза чата'))
        if packet.get('finish_reason') in ('length','interrupted') or packet.get('parse_error'):
            text='Ответ оборвался или не разобран. Повтори ответ полностью. Исходный запрос: '+user_prompt[:2000];continue
        action=packet.get('action') or {}
        if not isinstance(action,dict):raise AppError('invalid_input','действие модели должно быть объектом')
        kind=action.get('action')
        if action and not isinstance(kind,str):raise AppError('invalid_input','имя действия должно быть строкой')
        raw=packet.get('raw') or packet.get('text') or ''
        if kind in READ_ACTIONS:
            if consent is not None:
                return dict(state='pending_read',text=packet.get('text',''),action=action,plan=None,turns_used=number)
            text=read_feedback(ctx,action,user_prompt);continue
        if kind=='plan' and action.get('continues'):
            steps=action.get('steps')
            if not isinstance(steps,list) or len(parts)+len(steps)>100:
                raise AppError('invalid_input','слишком много частей плана')
            parts.extend(steps);text='Продолжи план; ни один шаг ещё не применён.';continue
        if parts:
            if kind!='plan': raise AppError('invalid_input','ожидалась заключительная часть плана')
            checked=ctx.call_tool('judge',{'full_text':raw})
            if checked.get('action')!=action:
                raise AppError('invalid_input','заключительная часть плана не совпадает с ответом')
            action=dict(action,steps=parts+(action.get('steps') or []))
            raw='```agent_action\n'+json.dumps(action,ensure_ascii=False)+'\n```'
        if kind in WRITE:
            checked=ctx.call_tool('judge',{'full_text':raw})
            if not checked['acceptable'] or checked.get('action')!=action:
                text='Исправь действие по проверке:\n'+json.dumps(checked,ensure_ascii=False)[:12000]+'\nИсходный запрос: '+user_prompt[:2000];continue
            preview=prepare_call({'action':action},ctx)
            if preview['state']=='ALREADY_SATISFIED':
                return {'state':'final','text':packet.get('text',''),'action':None,'plan':None,'turns_used':number}
            return {'state':'pending_confirmation','text':packet.get('text',''),'action':action,'plan':preview,'turns_used':number}
        if kind and kind not in ('done','none'):
            raise AppError('denied','действие не даёт разрешения: '+str(kind))
        checked=ctx.call_tool('judge',{'full_text':raw})
        if checked['acceptable'] and packet.get('done'):
            return {'state':'final','text':packet.get('text',''),'action':None,'plan':None,'turns_used':number}
        text='Исправь ответ; заверши маркером DONE. '+json.dumps(checked,ensure_ascii=False)[:12000]+'\nИсходный запрос: '+user_prompt[:2000]
    raise AppError('unavailable','исчерпан лимит шагов диалога')
