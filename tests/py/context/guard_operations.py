"""New replay of the 72 native-first security cases, including real junctions."""
import builtins
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import _winapi
from tests.py.context.observations import CORPUS, normalize, references, state

MARK, OWNER = 'OUTSIDE_NATIVE_MARKER', 'DENIED_OWNER_MARKER'
PRIVATE = ('extends Node\nfunc '+MARK+'():\n\tvar private_local_marker = 17\n\treturn private_local_marker\n').encode()

@contextmanager
def trace(sandbox, records):
    original_open, original_io, original_walk = builtins.open, io.open, os.walk
    def opener(original):
        def opened(file, mode='r', *args, **kwargs):
            if isinstance(file,(str,bytes,os.PathLike)):
                path=Path(os.fsdecode(file)).resolve()
                assert sandbox==path or sandbox in path.parents, ('non-sandbox IO',str(path))
                frame=sys._getframe(1)
                records['opens'].append({'path':str(path),'mode':mode,'module':frame.f_globals.get('__name__'),
                    'function':frame.f_code.co_name,'line':frame.f_lineno})
            return original(file,mode,*args,**kwargs)
        return opened
    def walked(*args,**kwargs):
        for row in original_walk(*args,**kwargs):
            records['walks'].append(str(Path(row[0]).resolve()))
            yield row
    with patch.object(builtins,'open',opener(original_open)),patch.object(io,'open',opener(original_io)),patch.object(os,'walk',walked):
        yield

def replay(sandbox,native=None):
    sandbox=sandbox.resolve()
    root,outside=sandbox/'project',sandbox/'outside'
    (root/'src').mkdir(parents=True)
    outside.mkdir()
    (root/'src/public.gd').write_bytes((CORPUS/'fixtures/guard/public.gd').read_bytes())
    (outside/'private.gd').write_bytes(PRIVATE)
    for path in (root/'src/public.gd',outside/'private.gd'):
        os.utime(path,(1000,1000))
    checks,observations,skips=[],{},[]
    records={'opens':[],'walks':[]}
    def check(name,condition,actual=None):
        checks.append({'name':name,'pass':bool(condition),'actual':normalize(actual,sandbox)})
    def clean(value):
        text=str(value).casefold()
        return MARK.casefold() not in text and OWNER.casefold() not in text
    def forbidden_reads(start):
        return [r for r in records['opens'][start:] if 'r' in r['mode'] and Path(r['path'])==outside/'private.gd']
    original_project,original_outside=state(root,sandbox),state(outside,sandbox)
    with references(sandbox,native) as subjects:
        guard,index,lib,data,parser=(subjects[n] for n in ('guard','index','lib','data','parser'))
        project=str(root)
        def answer(query,**kwargs):
            return lib.answer(project,query,addon_dir=str(sandbox/'cache-addon'),**kwargs)
        with trace(sandbox,records):
            allowed={'build':index.build_index(project),'snapshot':index.semantic_snapshot(project),
                'search':index.search(project,'public_symbol'),'card':lib._symbol_card(project,'public_symbol'),
                'answer':answer('public_symbol'),'typo':answer('publik_symbol')}
        check('allowed.public_declaration','public_symbol' in str(allowed['card']))
        check('allowed.project_bytes_unchanged',state(root,sandbox)==original_project)
        observations['allowed']=normalize(allowed,sandbox)
        start=len(records['opens'])
        with trace(sandbox,records):
            check('STOP.native_guard_denies',not guard.can_read_project_path('res://../outside/private.gd',project))
            lib.note_files_changed(project,changed=['res://../outside/private.gd'])
            snapshot=index.semantic_snapshot(project)
            card=lib._symbol_card(project,MARK)
            reply=answer(MARK)
        check('STOP.no_outside_read',not forbidden_reads(start),forbidden_reads(start))
        check('STOP.snapshot_no_forbidden_fact',clean(snapshot),snapshot)
        check('STOP.card_no_forbidden_declaration',clean(card),card)
        check('STOP.answer_no_forbidden_declaration','res://../outside/private.gd' not in reply and
              'private_local_marker' not in reply and '- decl function' not in reply,reply)
        check('STOP.project_bytes_unchanged',state(root,sandbox)==original_project)
        check('STOP.outside_bytes_unchanged',state(outside,sandbox)==original_outside)
        observations['STOP']=normalize({'snapshot':snapshot,'card':card,'answer':reply},sandbox)
        (root/'.agent_history').mkdir()
        (root/'.agent_history/private.gd').write_bytes(PRIVATE)
        (root/'Addons/RenamedWrapper/core').mkdir(parents=True)
        (root/'Addons/vendor').mkdir()
        for rel in ('Addons/vendor/private.gd','Addons/RenamedWrapper/core/private.gd'):
            (root/rel).write_bytes(PRIVATE)
        for target,link in ((outside,'outside_link'),(root/'Addons','addon_link'),(root/'.agent_history','history_link')):
            _winapi.CreateJunction(str(target),str(root/link))
        for link,target,directory in ((root/'outside_symlink',outside,True),(root/'private_symlink.gd',outside/'private.gd',False)):
            try:
                link.symlink_to(target,target_is_directory=directory)
            except OSError as error:
                assert error.winerror==1314,error
                skips.append({'case':link.name,'winerror':error.winerror,'reason':'genuine OS privilege gap'})
            else:
                assert not guard.can_read_project_path(str(link),project)
        paths=[('../outside/private.gd','traversal'),('..\\outside\\private.gd','backslash'),
            ('src/../../outside/private.gd','nested-traversal'),(str(outside/'private.gd'),'absolute'),
            ('outside_link/private.gd','outside-junction'),('addon_link/vendor/private.gd','addon-junction'),
            ('history_link/private.gd','history-junction'),('.agent_history/private.gd','history'),
            ('Addons/vendor/private.gd','mixed-case-addon'),('Addons/RenamedWrapper/core/private.gd','agent')]
        start=len(records['opens'])
        with trace(sandbox,records):
            for rel,label in paths:
                check('boundary.guard_denies.'+label,not guard.can_read_project_path(rel,project))
                entry=index._build_entry(project,rel)
                semantic=index._build_semantic_entry(project,rel)
                reused=index._reuse_or_build(project,rel,{rel:{'path':rel,'kind':'gd','symbols':[MARK],'mtime':1000,'size':len(PRIVATE)}})
                check('boundary.builder_omits.'+label,entry is None,entry)
                check('boundary.semantic_omits.'+label,semantic is None,semantic)
                check('boundary.reuse_omits.'+label,reused is None,reused)
            walk_start=len(records['walks'])
            index.build_index(project)
            snapshot=index.semantic_snapshot(project)
        check('boundary.scan_no_forbidden_fact',clean(snapshot),snapshot)
        denied_walks=[p for p in records['walks'][walk_start:] if Path(p) in (outside,root/'Addons',root/'.agent_history')]
        check('boundary.scan_prunes_actual_identities',not denied_walks,denied_walks)
        check('boundary.no_outside_read',not forbidden_reads(start),forbidden_reads(start))
        good=index._build_semantic_entry(project,'src/public.gd')
        private=parser.parse(PRIVATE.decode(),'../outside/private.gd')
        owner=next(d['id'] for d in good['semantic']['declarations'] if d['name']=='public_symbol')
        private['declarations'].append({'id':'forged-local','name':OWNER,'kind':'variable','owner':owner,'line':99,'start':999})
        private['references'].append({'name':OWNER,'owner':owner,'context':'member','line':99})
        poisoned={'schema':1,'root':project,'built':1000,'complete':True,'files':[good,
            {'path':'../outside/private.gd','sha256':'forged','mtime':1000,'size':len(PRIVATE),'semantic':private}]}
        raw={'root':project,'built':1000,'sym_limit':index.MAX_SYMBOLS,'complete':True,'files':[
            {'path':'src/public.gd','kind':'gd','symbols':['func:public_symbol']},
            {'path':'../outside/private.gd','kind':'gd','symbols':['func:'+MARK]}]}
        for path,value in ((index._index_path(project),raw),(index._semantic_index_path(project),poisoned)):
            Path(path).write_text(json.dumps(value),encoding='utf-8')
        index._MEM_CACHE.clear()
        index._SEM_MEM_CACHE.clear()
        with trace(sandbox,records):
            for turn in ('disk','memory'):
                value={'index':index._load_index(project,auto_build=False),'snapshot':index.semantic_snapshot(project),
                    'search':index.search(project,MARK),'declarations':index.find_declarations(project,name=MARK),'facts':index.find_name_facts(project,MARK)}
                check('stale.'+turn+'.no_forbidden_facts',clean(value),value)
            with patch.object(index,'semantic_snapshot',return_value=poisoned):
                card=lib._symbol_card(project,'public_symbol')
                check('librarian.semantic_both_passes_filter',clean(card) and '../outside/' not in str(card),card)
            with patch.object(index,'_load_index',return_value=raw):
                hint=lib._near_tokens(project,MARK[:-1],limit=100)
                check('librarian.near_hints_filter',clean(hint),hint)
            with patch.object(index,'_load_index',return_value={'files':[{'path':'../outside/private.gd','symbols':['func:Deniedhintsecret']}]}):
                hint=lib._near_tokens(project,'Deniedhintsecrex',limit=100)
                check('librarian.single_token_near_hint_filter','deniedhintsecret' not in str(hint).casefold(),hint)
            denied=raw['files'][1:]
            structure=lib._structure(project,denied)
            check('librarian.structure_no_denied_header','../outside/' not in str(structure),structure)
            needles=[]
            with patch.object(lib,'_grep_patterns',side_effect=lambda *a,**k:needles.append(a[1]) or {}):
                lib._callers(project,MARK,denied)
            check('librarian.callers_deny_source_symbols',MARK not in str(needles),needles)
            needles=[]
            with patch.object(lib,'_grep_patterns',side_effect=lambda *a,**k:needles.append(a[1]) or {}):
                lib._signal_wiring(project,MARK,[dict(denied[0],symbols=['signal:'+MARK])])
            check('librarian.signals_deny_source_symbols',MARK not in str(needles),needles)
            rows=[{'path':'res://../outside/private.gd','line':2,'text':'func '+MARK+'():','needle':MARK}]
            with patch.object(lib,'search_project_text',return_value=(rows,False)):
                grep=lib._grep_patterns(project,[MARK],20)
                fragments=lib._fragments(project,MARK)
            check('librarian.grep_patterns_output_filter',clean(grep),grep)
            check('librarian.fragments_output_guard',clean(fragments),fragments)
        _winapi.CreateJunction(str(root/'src'),str(root/'alias'))
        index.build_index(project)
        old=index.semantic_snapshot(project)
        os.rmdir(root/'alias')
        _winapi.CreateJunction(str(outside),str(root/'alias'))
        with trace(sandbox,records):
            current=index.semantic_snapshot(project)
            search=index.search(project,'public_symbol')
        check('retarget.snapshot_filters_cached_path',not any(row['path'].startswith('alias/') for row in current['files']),current)
        check('retarget.search_filters_cached_path',not any(row['path'].startswith('alias/') for row in search),search)
        observations['retarget']=normalize({'before':old,'after':current,'search':search},sandbox)
        agent=root/'Addons/RenamedWrapper/core'
        vendor=root/'Addons/vendor'
        entries=[{'path':rel,'semantic':parser.parse('func '+name+'():\n\treturn 1\n',rel)} for rel,name in
            (('Addons/RenamedWrapper/core/agent.gd','agent_symbol'),('Addons/vendor/vendor.gd','vendor_symbol'))]
        for entry in entries:
            (root/entry['path']).write_text('extends Node\n',encoding='utf-8')
        with patch.object(index,'semantic_snapshot',return_value={'files':entries,'complete':True}):
            for label,flags,identity,expected in (
                ('default',{},agent,(False,False)),('addons',{'allow_addons':True},agent,(False,True)),
                ('self',{'allow_self_edit':True},agent,(True,False)),
                ('invalid_identity',{'allow_addons':True,'allow_self_edit':True},outside,(False,False))):
                for name,visible in zip(('agent_symbol','vendor_symbol'),expected):
                    card=lib._symbol_card(project,name,addon_dir=str(identity),**flags)
                    reply=lib.answer(project,name,addon_dir=str(identity),**flags)
                    check('capabilities.'+label+'.'+name,(bool(card)==visible) and (('- decl function' in reply)==visible),
                        {'card':card,'answer':reply})
    assert len(checks)==72 and len({row['name'] for row in checks})==72
    return {'checks':checks,'observations':observations,'skips':skips,'trace':normalize(records,sandbox)}
