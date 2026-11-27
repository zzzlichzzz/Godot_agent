"""Native cache reads/migration/refresh against disposable user/addon copies only."""
import json
from pathlib import Path
import shutil
from unittest.mock import patch
from tests.py.engine_cache.observations import attempt, digest

CLASSES = {'Node':{'inherits':'Object','methods':{'zero':0,'one':1,'ranged':[1,2]},'properties':['position'],'signals':['ready'],'method_signatures':{'one':'one(value: int) -> void'}},
           'Object':{'inherits':'','methods':{'base':0},'properties':[],'signals':[]}}

def run_cache(cache,storage,root,case,data_source,sandbox):
    primary=Path(storage.get_storage_dir(str(root)))/cache.CACHE_FILENAME
    addon=sandbox/'addon'
    addon.mkdir()
    backup=addon/cache.DEFAULT_CACHE_SUBDIR/cache.DEFAULT_CACHE_FILENAME
    if case.get('raw') is not None:
        primary.write_bytes(bytes.fromhex(case['raw']))
    elif case.get('variant')=='real':
        backup.parent.mkdir()
        shutil.copyfile(data_source,backup)
    elif case.get('variant')!='missing':
        classes=case.get('classes',CLASSES)
        primary.write_text(json.dumps({'godot_version':case.get('version','4.synthetic'),'classes':classes},ensure_ascii=False),encoding='utf-8')
    if case.get('fallback'):
        backup.parent.mkdir(exist_ok=True)
        backup.write_text(json.dumps({'godot_version':'fallback','classes':CLASSES}),encoding='utf-8')
    if case.get('legacy'):
        (addon/cache.DEFAULT_CACHE_FILENAME).write_text(json.dumps({'godot_version':'legacy','classes':CLASSES}),encoding='utf-8')
    arguments=(str(root),str(addon))
    def query():
        info=attempt(cache.get_class,*arguments[:1],'Node',addon_dir=arguments[1])
        return {'version':attempt(cache.get_cached_version,*arguments),'has_cache':attempt(cache.has_cache,*arguments),
                'class':info,'chain':attempt(cache.resolve_chain,str(root),'Node',addon_dir=str(addon)),
                'members':attempt(cache.collect_members,str(root),'Node',addon_dir=str(addon)),
                'signatures':attempt(cache.collect_signatures,str(root),'Node',addon_dir=str(addon))}
    action=case['action']
    if action=='read':
        return query()
    if action=='stale':
        first=query()
        primary.write_bytes(b'{broken-after-memory-load')
        return {'first':first,'second':query(),'root_same':cache._cache['root']==str(root)}
    if action=='save':
        before=primary.read_bytes() if primary.exists() else None
        snapshot=json.loads(data_source.read_bytes()) if case.get('native_snapshot') else {'godot_version':'refresh.synthetic','classes':case.get('save_classes',CLASSES)}
        if case.get('failure'):
            real_open=open
            def failing(path,*args,**kwargs):
                if (case['failure']=='primary' and Path(path)==primary) or (case['failure']=='backup' and Path(path)==backup):
                    raise PermissionError(13,'synthetic cache write denial')
                return real_open(path,*args,**kwargs)
            with patch.object(cache,'open',failing,create=True):
                result=attempt(cache.save_cache,str(root),snapshot['classes'],godot_version=snapshot['godot_version'],addon_dir=str(addon))
        else:
            result=attempt(cache.save_cache,str(root),snapshot['classes'],godot_version=snapshot['godot_version'],addon_dir=str(addon))
        after=primary.read_bytes() if primary.exists() else None
        return {'result':result,'before':{'bytes':len(before),'sha256':digest(before)} if before is not None else None,'after':{'bytes':len(after),'sha256':digest(after)} if after is not None else None,'query':query(),'primary_preserved':before==after,
                'input_snapshot_sha':digest(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode('utf-8'))}
    raise AssertionError('unlisted cache action')
