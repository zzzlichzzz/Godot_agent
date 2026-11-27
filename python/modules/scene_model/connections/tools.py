"""Two literal reference views, one read-only connections card."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec


def _object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


_STRING={'type':'string'}
CONNECTIONS=ToolSpec(
    name='connections',
    description=('Связи .tscn/.scn: connections — raw parse_scene; text — только строки '
                 'describe_scene с <root>. Пустые атрибуты остаются в raw; display требует '
                 'signal/method. Не проверяет существование функции, не пишет файлы.'),
    args=_object({'path':_STRING}),
    result=_object({'connections':{'type':'array','items':_object({
        'signal':_STRING,'from':_STRING,'to':_STRING,'method':_STRING})},'text':_STRING}),
    effects='read',idempotent=True,cost='cheap',availability='*',
    errors=('invalid_input','not_found','denied'),limits={'max_file_bytes':READ_TEXT_MAX_BYTES})
TOOLS=(CONNECTIONS,)
