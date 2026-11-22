"""Whitelisted reference effects on owned fixture files; no host state imports."""
import functools
import hashlib
import json
import os
from pathlib import Path
import threading
from unittest.mock import patch
from tests.py.engine_cache.observations import attempt, digest

def bytes_at(path):
    return path.read_bytes() if path.is_file() else None

def run_history(storage,root,case):
    action = case['action']
    journal = Path(storage._journal_path(str(root)))
    if action=='storage':
        return {'storage':storage.get_storage_dir(str(root)),'new_chain_id':storage.new_chain_id()}
    if action=='load':
        if case.get('directory'):
            journal.mkdir()
        elif 'raw' in case:
            journal.write_bytes(bytes.fromhex(case['raw']))
        original = bytes_at(journal)
        if case.get('permission'):
            with patch.object(storage,'open',side_effect=PermissionError(13,'synthetic journal permission'),create=True):
                result = attempt(storage._load_journal,str(root))
        else:
            result = attempt(storage._load_journal,str(root))
        return {'result':result,'original':original,'after':bytes_at(journal),'preserved':bytes_at(journal)==original}
    if action=='save':
        if case.get('exists',True):
            journal.write_bytes(b'[]')
        original = bytes_at(journal)
        legacy = journal.with_name('journal.json.tmp')
        legacy.write_bytes(b'foreign-owned')
        events, names = [], []
        real_sync, real_replace = storage.os.fsync, storage.os.replace
        def sync(fd):
            events.append({'op':'fsync'})
            if case.get('failure')=='fsync':
                raise OSError(5,'synthetic fsync failure')
            real_sync(fd)
        def replace(source,target):
            names.append(str(source))
            events.append({'op':'replace','temporary':Path(source).name.startswith('.journal-'),'same_parent':Path(source).parent==Path(target).parent,'destination_before':bytes_at(Path(target)),'source':bytes_at(Path(source))})
            if case.get('failure')=='replace':
                raise PermissionError(13,'synthetic replace failure')
            return real_replace(source,target)
        handle = None
        if case.get('failure')=='busy':
            import _winapi
            handle = _winapi.CreateFile(str(journal),0x80000000,0,0,3,0,0)
        try:
            with patch.object(storage.os,'fsync',sync),patch.object(storage.os,'replace',replace):
                result = attempt(storage._save_journal,str(root),[{'id':'synthetic','type':'patch_file','path':'res://A.txt','committed':False}])
        finally:
            if handle is not None:
                _winapi.CloseHandle(handle)
        return {'result':result,'events':events,'unique_temp_names':len(names)==len(set(names)),'before':original,'after':bytes_at(journal),'preserved':bytes_at(journal)==original,'legacy_preserved':legacy.read_bytes()==b'foreign-owned','owned_temps_left':sorted(path.name for path in journal.parent.glob('.journal-*'))}
    if action=='decorator':
        events=[]
        class Lock:
            def __init__(self):
                self.inner,self.depth=threading.RLock(),0
            def __enter__(self):
                self.inner.acquire()
                self.depth+=1
                events.append(['acquire',self.depth])
            def __exit__(self,*args):
                events.append(['release',self.depth])
                self.depth-=1
                self.inner.release()
        identity=os.path.normcase(os.path.realpath(journal))
        storage._JOURNAL_LOCKS[identity]=Lock()
        def sample(project,value):
            return storage._load_journal(project),value
        wrapped=storage._journal_transaction(sample)
        result=wrapped(str(root),7)
        bypass=storage._journal_transaction(lambda project,value:value)(None,9)
        return {'result':result,'bypass':bypass,'name':wrapped.__name__,'wrapped_identity':wrapped.__wrapped__ is sample,'events':events}
    if action=='duplicate':
        return attempt(storage.record_batch_change,str(root),'batch',['res://A.txt',case['other']])
    if action=='reserved':
        target=root/'A.txt'
        absent=case.get('absent',False)
        if absent:
            target.unlink()
        entry=storage.record_batch_change(str(root),'batch',['res://A.txt'],states=[{'path':'res://A.txt','before_bytes':None if absent else target.read_bytes(),'after_bytes':b'external-stage'}])
        target.write_bytes(b'external-stage\r\n')
        current_hash=digest(target.read_bytes())
        if case.get('missing_snapshot'):
            for path in journal.parent.joinpath('snapshots').iterdir():
                path.unlink()
        supplied=None if case.get('no_hash') else 'wrong' if case.get('wrong_hash') else current_hash
        result=attempt(storage.restore_reserved_change,str(root),entry,current_hash=supplied,remove_created=case.get('remove_created',False))
        return {'result':result,'file':bytes_at(target),'journal':storage._load_journal(str(root))}
    if action=='case_only':
        target=root/'CaseDir/Nested/F.txt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'case original\r\n')
        source,destination='res://CaseDir/Nested/F.txt','res://casedir/nested/F.txt'
        entry=storage.record_batch_change(str(root),'batch',[source],states=[{'path':source,'before_bytes':target.read_bytes(),'after_bytes':target.read_bytes(),'case_only_dest':destination}])
        transaction=storage.begin_case_only_dir_casing(str(root),source,destination)
        transaction.commit()
        storage.commit_change(str(root),entry)
        return {'result':storage.rollback_entry(str(root),entry),'journal':storage._load_journal(str(root))}
    if action=='migrate':
        old=root/'.agent_history'
        old.joinpath('snapshots').mkdir(parents=True,exist_ok=True)
        (old/'journal.json').write_bytes(b'[]')
        (old/'snapshots/legacy.bin').write_bytes(b'legacy bytes')
        return storage.migrate_from_project(str(root))
    if action=='record_failure':
        before=bytes_at(journal)
        with patch.object(storage.os,'fsync',side_effect=OSError(5,'synthetic record fsync failure')):
            if case['batch']:
                result=attempt(storage.record_batch_change,str(root),'batch',['res://A.txt','res://B.txt'])
            else:
                result=attempt(storage.record_change,str(root),{'action':'patch_file','path':'res://A.txt'})
        return {'result':result,'journal_preserved':bytes_at(journal)==before,'snapshots_left':sorted(path.name for path in (journal.parent/'snapshots').iterdir()),'temps_left':sorted(path.name for path in journal.parent.glob('.journal-*'))}
    if action=='batch_failure':
        entry=storage.record_batch_change(str(root),'batch',['res://A.txt','res://B.txt'])
        (root/'A.txt').write_bytes(b'after A\n')
        (root/'B.txt').write_bytes(b'after B\n')
        storage.commit_change(str(root),entry)
        before=bytes_at(journal)
        real_replace=storage.os.replace
        def failing(source,target):
            if Path(target)==root/'B.txt':
                raise PermissionError(13,'synthetic second rollback replace failure')
            return real_replace(source,target)
        with patch.object(storage.os,'replace',failing):
            first=storage.rollback_entry(str(root),entry)
        retained={'journal_preserved':bytes_at(journal)==before,'A':bytes_at(root/'A.txt'),'B':bytes_at(root/'B.txt')}
        second=storage.rollback_entry(str(root),entry)
        return {'first':first,'retained':retained,'retry':second,'A':bytes_at(root/'A.txt'),'B':bytes_at(root/'B.txt'),'journal':storage._load_journal(str(root))}
    if action!='sequence':
        raise AssertionError('unlisted history action')
    kind,finish=case.get('kind','patch_file'),case.get('finish','rollback_last')
    source=root/'A.txt'
    if kind=='create_file' and not case.get('overwrites'):
        path='res://new.txt'
    else:
        path='res://A.txt'
    if kind=='batch':
        entry=storage.record_batch_change(str(root),'batch',['res://A.txt','res://B.txt'],chat_id='chat-one',chain_id='chain-one')
        (root/'A.txt').write_bytes(b'after A\n')
        (root/'B.txt').write_bytes(b'after B\n')
    else:
        entry=storage.record_change(str(root),{'action':kind,'path':path,'dest':'res://Moved.txt','search':'before','replace':'after'},chat_id='chat-one',chat_title='Synthetic chat',chain_id='chain-one')
        if kind=='move_file':
            os.rename(source,root/'Moved.txt')
        else:
            (root/path.removeprefix('res://')).write_bytes(b'after\n')
    storage.commit_change(str(root),entry)
    metadata=storage.entry_info(str(root),entry)
    if finish=='blocker':
        later=storage.record_change(str(root),{'action':'patch_file','path':'res://A.txt'},chat_id='chat-two')
        (root/'A.txt').write_bytes(b'later\n')
        storage.commit_change(str(root),later)
        result=storage.rollback_entry(str(root),entry,force=True)
    elif finish=='external':
        (root/path.removeprefix('res://')).write_bytes(b'foreign manual\n')
        result=storage.rollback_entry(str(root),entry,force=case.get('force',False))
    elif finish=='abort':
        result=storage.abort_change(str(root),entry)
    elif finish=='rollback_entry':
        result=storage.rollback_entry(str(root),entry)
    elif finish=='rollback_chain':
        result=storage.rollback_chain(str(root),'chain-one')
    elif finish=='rollback_last':
        result=storage.rollback_last(str(root))
    elif finish=='forget':
        result=storage.forget_chat(str(root),'chat-one')
    elif finish=='prune':
        storage.MAX_ENTRIES=1
        for index in range(3):
            pending=storage.record_change(str(root),{'action':'patch_file','path':'res://B.txt'})
            storage.commit_change(str(root),pending)
        result=storage.last_committed_info(str(root))
    else:
        result={'last':storage.last_committed_info(str(root)),'others_ts':storage.last_write_ts_by_others(str(root),path,'different-chat'),'summary':storage.summarize_changes_since(str(root),0)}
    return {'metadata':metadata,'result':result,'journal':storage._load_journal(str(root)),'files':{path.name:bytes_at(path) for path in (root/'A.txt',root/'B.txt',root/'Moved.txt',root/'new.txt')}}
