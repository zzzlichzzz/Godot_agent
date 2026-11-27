"""Strict read-only node contract; no scene writes, execution or editor state."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec


NODE = ToolSpec(name='node', description='Карточка узла .tscn/.scn по пути, имени или %unique; пустое имя — корень.',
    args={'type':'object','required':['path','node'],'additionalProperties':False,
           'properties':{'path':{'type':'string'},'node':{'type':'string'}}},
    result={'type':'object','required':['name','type','parent','path','depth','script','instance',
                                      'unique_name','parent_path','children'], 'additionalProperties':False,
            'properties':{'name':{'type':'string'},'type':{'type':'string'},
                          'parent':{'type':['string','null']},'path':{'type':'string'},
                          'depth':{'type':'integer','minimum':0},'script':{'type':['string','null']},
                          'instance':{'type':['string','null']},'unique_name':{'type':'boolean'},
                          'parent_path':{'type':['string','null']},
                          'children':{'type':'array','items':{'type':'string'}}}},
    effects='read', idempotent=True, cost='cheap', availability='*',
    errors=('invalid_input','not_found','denied'), limits={'max_file_bytes':READ_TEXT_MAX_BYTES})
TOOLS = (NODE,)
