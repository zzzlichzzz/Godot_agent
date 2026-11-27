"""Literal scene_deps report over supplied data; formats own syntax facts."""
from python.formats import gdscript,tscn
from .signals import KNOWN_SIGNALS

_SKIP_DIRS={'.godot','.git','.import','__pycache__'}


def is_project_file(rel):
    return (rel.endswith(('.gd','.tscn')) and
            not any(part in _SKIP_DIRS for part in rel.split('/')[:-1]))


def resource_key(path):
    rel=(path or '').replace('res://','',1).replace('\\','/')
    if not rel or rel.startswith('/') or rel[1:2]==':' or '..' in rel.split('/'):
        return None
    return 'res://'+'/'.join(part for part in rel.split('/') if part not in ('','.'))


def prepare_script(text):
    return gdscript.handlers(text)


def prepare_scene(text):
    ext,nodes,connections=tscn.fields(text.replace('\r\n','\n'))
    script_nodes=[]
    for node in nodes:
        info=ext.get(node.get('script_id'))
        if info and info.get('type')=='Script' and info.get('path','').endswith('.gd'):
            script_nodes.append((node,info['path']))
    return ext,nodes,connections,script_nodes


def _connected(method,gd,scenes,exclude=None):
    return (any(gdscript.method_connected(text,method) for text in gd.values()) or
            any(tscn.method_referenced(text,method) for path,text in scenes.items() if path!=exclude))


def _find_candidates(handler,nodes,script_node):
    suffix=handler[len('_on_'):]
    seen,candidates=set(),[]
    for node in nodes:
        ntype=node.get('type')
        if not ntype:
            continue
        snake=tscn.to_snake(node.get('name',''))
        for signal,types in KNOWN_SIGNALS.items():
            if ntype not in types:
                continue
            if suffix=='%s_%s'%(snake,signal) or (node is script_node and suffix==signal):
                key=(node['path'],signal)
                if key not in seen:
                    seen.add(key);candidates.append((node,signal))
    return candidates


def scene_action(scene_text,scene_res_path,view,gd,scenes,attached):
    ext,nodes,connections,script_nodes=view
    added,notes,new_lines=[],[],[]
    custom=set().union(*(gdscript.custom_signals(text) for text in gd.values()))
    existing_methods={c['method'] for c in connections}
    existing_from_signal={(c['from'],c['signal']) for c in connections}
    for node,script_res in script_nodes:
        script_text=attached.get(resource_key(script_res))
        if script_text is None:
            continue
        for handler in prepare_script(script_text):
            if handler in existing_methods or _connected(handler,gd,scenes,resource_key(scene_res_path)):
                continue
            candidates=_find_candidates(handler,nodes,node)
            if len(candidates)==1:
                src,sig=candidates[0]
                if (src['path'],sig) in existing_from_signal:
                    notes.append('сигнал %s узла %s уже подключен к другому методу, а обработчик '
                                 '%s в %s остался неподключённым — проверь, какой из них нужен'
                                 %(sig,src['path'],handler,script_res))
                    continue
                new_lines.append('[connection signal="%s" from="%s" to="%s" method="%s"]'
                                 %(sig,src['path'],node['path'],handler))
                existing_methods.add(handler);existing_from_signal.add((src['path'],sig))
                added.append('%s: %s -> %s.%s'%(sig,src['path'],node['path'],handler))
                if (src.get('type') or '').startswith('RigidBody'):
                    notes.append('для сигнала %s у %s (RigidBody) нужны contact_monitor = true и '
                                 'max_contacts_reported > 0, иначе сигнал не будет срабатывать'
                                 %(sig,src['path']))
            elif len(candidates)>1:
                variants=', '.join('%s.%s'%(src['path'],sig) for src,sig in candidates[:4])
                notes.append('обработчик %s в %s нигде не подключен, но подходят несколько '
                             'источников (%s) — добавь [connection] вручную для нужного'
                             %(handler,script_res,variants))
            elif handler[len('_on_'):] in custom:
                notes.append('обработчик %s в %s похож на обработчик пользовательского сигнала '
                             '%s, но нигде не подключен — подключи его через connect() в коде '
                             'или [connection] в сцене'%(handler,script_res,handler[len('_on_'):]))
    out=scene_text
    if new_lines:
        out=scene_text.replace('\r\n','\n')
        if not out.endswith('\n'):
            out+='\n'
        out+='\n'+'\n'.join(new_lines)+'\n'
    return {'text':out,'added':added,'notes':notes}


def script_action(script_text,script_res_path,gd,scenes,handlers=None):
    notes=[]
    handlers=prepare_script(script_text) if handlers is None else handlers
    if not handlers:
        return {'text':None,'added':[],'notes':notes}
    gd=dict(gd)
    key=resource_key(script_res_path)
    if key:
        gd[key]=script_text
    for scene_res,scene_text in scenes.items():
        if not tscn.script_referenced(scene_text,script_res_path):
            continue
        ext,nodes,connections=tscn.fields(scene_text)
        sid=next((eid for eid,info in ext.items() if
                  info.get('path')==script_res_path and info.get('type')=='Script'),None)
        if sid is None:
            continue
        existing_methods={c['method'] for c in connections}
        for node in nodes:
            if node.get('script_id')!=sid:
                continue
            for handler in handlers:
                if handler in existing_methods or _connected(handler,gd,scenes):
                    continue
                candidates=_find_candidates(handler,nodes,node)
                if candidates:
                    src,sig=candidates[0]
                    notes.append('в скрипте %s есть обработчик %s, но в сцене %s нет [connection] '
                                 'для него (похоже на сигнал %s узла %s) — добавь подключение в сцену '
                                 'или через connect() в _ready()'
                                 %(script_res_path,handler,scene_res,sig,src['path']))
    return {'text':None,'added':[],'notes':notes}
