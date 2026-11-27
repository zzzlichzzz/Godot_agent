"""C.17 scan descriptor."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

ARGS = {'type':'object','required':['path'],'properties':{'path':{'type':'string','minLength':1}},
        'additionalProperties':False}
KINDS = ['import','source_read','patch','mention','doc']
COUNTS = {'type':'object','required':KINDS,'properties':{k:{'type':'integer'} for k in KINDS},
          'additionalProperties':False}
OCCURRENCE = {'type':'object','required':['file','line','kind','text'],
              'properties':{'file':{'type':'string','minLength':1},'line':{'type':'integer'},
                            'kind':{'type':'string','enum':KINDS},'text':{'type':'string'}},
              'additionalProperties':False}
RESULT = {'type':'object','required':['donor','stem','counts','occurrences','truncated','hard_files','soft_files'],
          'properties':{'donor':{'type':'string','minLength':1},'stem':{'type':'string','minLength':1},
                        'counts':COUNTS,'occurrences':{'type':'array','items':OCCURRENCE},
                        'truncated':{'type':'boolean'},'hard_files':{'type':'array','items':{'type':'string'}},
                        'soft_files':{'type':'array','items':{'type':'string'}}},'additionalProperties':False}
SCAN = ToolSpec(name='split_scan',
                description='Карта ссылок на .py агента: импорты, патчи, чтение исходника, упоминания. Только чтение.',
                args=ARGS,result=RESULT,effects='read',idempotent=True,
                errors=('invalid_input','not_found','denied'),availability='*',cost='cheap',
                limits={'max_file_bytes':READ_TEXT_MAX_BYTES})
