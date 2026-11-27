"""Native scene tuple / script notes, named read-only projection."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec
from .settings import PROJECT_SCAN_MAX_BYTES


def _object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


_STRINGS={'type':'array','items':{'type':'string'}}
SCENE_DEPS=ToolSpec(
    name='scene_deps',
    description=('Анализ неподключённых _on_*: .tscn/.scn возвращает предложенный text, added '
                 'и notes; .gd возвращает text=null, added=[], notes. Не записывает текст, '
                 'не обходит граф ресурсов и не валидирует циклы. Скан .gd/.tscn рекурсивный; '
                 '512KiB только для скана, основной/привязанный скрипт — max_file_bytes.'),
    args=_object({'path':{'type':'string'}}),
    result=_object({'text':{'type':['string','null']},'added':_STRINGS,'notes':_STRINGS}),
    effects='read',idempotent=True,cost='heavy',availability='*',
    errors=('invalid_input','not_found','denied'),
    limits={'max_file_bytes':READ_TEXT_MAX_BYTES,'project_scan_max_file_bytes':PROJECT_SCAN_MAX_BYTES})
TOOLS=(SCENE_DEPS,)
