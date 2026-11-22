"""Only native preparation and raw deltas; no native apply entrypoint."""
from importlib import import_module
from pathlib import Path

def refactor(root,action,policy):
    kind=action['action']
    if kind=='rename_symbol':
        prepared=import_module('python.substrate.code_intel.symbol_refactor').prepare_rename(root,action,**policy)
    else:
        prepared=import_module('python.substrate.editing.file_refactor').prepare_file_rename(root,action.get('path') or action.get('old_path'),
            action.get('dest') or action.get('new_path'),update_references=action.get('update_references',True),**policy)
    files=[]
    for item in prepared['files']:
        if item.get('action')=='move_file':
            files.extend([dict(path=item['path'],before_bytes=item['before_bytes'],after_bytes=None,move_to=item['dest']),
                          dict(path=item['dest'],before_bytes=None,after_bytes=item['after_bytes'])])
            source=Path(root)/item['path'][6:];uid=source.with_name(source.name+'.uid')
            if uid.is_file():
                raw=uid.read_bytes();files.extend([dict(path=item['path']+'.uid',before_bytes=raw,after_bytes=None,move_to=item['dest']+'.uid'),
                                                  dict(path=item['dest']+'.uid',before_bytes=None,after_bytes=raw)])
        else:files.append(dict(path=item['path'],before_bytes=item['before_bytes'],after_bytes=item['after_bytes']))
    move=prepared.get('file_rename')
    if move:
        source=move['from'];dest=move['to'];file=next((f for f in files if f['path']==source),None)
        raw=(Path(root)/source[6:]).read_bytes()
        if file:after=file['after_bytes'];files.remove(file)
        else:after=raw
        files.extend([dict(path=source,before_bytes=raw,after_bytes=None,move_to=dest),dict(path=dest,before_bytes=None,after_bytes=after)])
        uid=Path(root)/(source[6:]+'.uid')
        if uid.is_file():
            raw=uid.read_bytes();files.extend([dict(path=source+'.uid',before_bytes=raw,after_bytes=None,move_to=dest+'.uid'),dict(path=dest+'.uid',before_bytes=None,after_bytes=raw)])
    return dict(files=files,warnings=prepared.get('warnings',[]))
