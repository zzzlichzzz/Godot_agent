"""C.18 native plan projection: bool state, object reexports, no generated text."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

STRINGS = {'type':'array','items':{'type':'string'}}
GROUP = {'type':'object','required':['module','symbols'],
         'properties':{'module':{'type':'string','minLength':1},'symbols':STRINGS},
         'additionalProperties':False}
PLAN_MODULE = {'type':'object','required':['rel','names','lines'],
               'properties':{'rel':{'type':'string','minLength':1},'names':STRINGS,'lines':{'type':'integer'}},
               'additionalProperties':False}
REEXPORT = {'type':'object','required':['module','names'],
            'properties':{'module':{'type':'string','minLength':1},'names':STRINGS},
            'additionalProperties':False}
SYMBOL = {'type':'object','required':['name','kind','lines','is_public','state'],
          'properties':{'name':{'type':'string','minLength':1},'kind':{'type':'string'},
                        'lines':{'type':'integer'},'is_public':{'type':'boolean'},'state':{'type':'boolean'}},
          'additionalProperties':False}
PLAN_ARGS = {'type':'object','required':['path'],
             'properties':{'path':{'type':'string','minLength':1},
                           'groups':{'type':'array','items':GROUP},'target_lines':{'type':'integer'}},
             'additionalProperties':False}
PLAN_RESULT = {'type':'object',
               'required':['donor','donor_sha256','donor_lines','target_lines','auto_groups',
                           'modules','facade','moved_names','errors','warnings','inventory','refs'],
               'properties':{
                   'donor':{'type':'string','minLength':1},
                   'donor_sha256':{'type':'string','minLength':64,'maxLength':64},
                   'donor_lines':{'type':'integer'},'target_lines':{'type':'integer'},
                   'auto_groups':{'type':'boolean'},'modules':{'type':'array','items':PLAN_MODULE},
                   'facade':{'type':'object','required':['rel','lines','reexports'],
                             'properties':{'rel':{'type':'string','minLength':1},'lines':{'type':'integer'},
                                           'reexports':{'type':'array','items':REEXPORT}},
                             'additionalProperties':False},
                   'moved_names':STRINGS,'errors':STRINGS,'warnings':STRINGS,
                   'inventory':{'type':'object','required':['symbols','imports','other','docstring'],
                                'properties':{'symbols':{'type':'array','items':SYMBOL},
                                              'imports':{'type':'integer'},'other':{'type':'integer'},
                                              'docstring':{'type':'boolean'}},'additionalProperties':False},
                   'refs':{'type':['object','null']}},'additionalProperties':False}
PLAN = ToolSpec(name='split_plan',
                description='План разбиения .py агента: модули, имена, фасад, ошибки плана. Только чтение.',
                args=PLAN_ARGS,result=PLAN_RESULT,effects='read',idempotent=True,
                errors=('invalid_input','not_found','denied'),availability='*',cost='cheap',
                limits={'max_file_bytes':READ_TEXT_MAX_BYTES})
