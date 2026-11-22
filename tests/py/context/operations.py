"""Behavioral cases, not copies of old native tests."""
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch
from tests.py.context.observations import ROOT, attempt

def run(subjects, project, sandbox, case, native):
    lib, index, data, api = (subjects[name] for name in ('lib','index','data','api'))
    root, query = str(project), case.get('query', '')
    operation = case['operation']
    kwargs = {'addon_dir':str(sandbox/'cache-addon')}
    if operation == 'edge':
        from tests.py.context.edge_operations import run as edge
        return edge(subjects,project,sandbox,case)
    if operation == 'tokens':
        return {'tokens':lib._query_tokens(query),'subtokens':lib._query_subtokens(query),
                'expanded':lib._expanded_query(query),'card_request':lib._card_request(query),
                'phrase':index._phrase_keys(query),'path_keys':index._path_keys(query)}
    if operation == 'answer':
        return lib.answer(root, query, budget_chars=case.get('budget',6000), **kwargs)
    if operation == 'budget-boundaries':
        complete = lib.answer(root, query, budget_chars=100000, **kwargs)
        lines = complete.splitlines()[:-1]
        total, budgets = 0, {0,1,299,300,301,400,500,600,1000}
        for line in lines[:20]:
            total += len(line)+1
            edge = total + len(lib.FOOTER)+8
            budgets.update((edge-1,edge,edge+1))
        return {str(b):lib.answer(root,query,budget_chars=b,**kwargs) for b in sorted(budgets)}
    if operation == 'layers':
        index.build_index(root)
        hits = index.search(root,query,limit=24)
        return {'structure':lib._structure(root,hits),'fragments':lib._fragments(root,query),
                'callers':lib._callers(root,query,hits),'autoloads':lib._autoload_lines(root,query),
                'signals':lib._signal_wiring(root,query,hits),'card':attempt(lib._symbol_card,root,query),
                'near':lib._near_tokens(root,query),'reranked':lib._rerank_hits(hits,query,lib._expanded_query(query)[1])}
    if operation == 'index':
        return {'build':index.build_index(root),'snapshot':index.semantic_snapshot(root),
                'search':index.search(root,query),'meta':index.index_meta(root),
                'declarations':index.find_declarations(root,name=query),
                'facts':index.find_name_facts(root,query),'prompt':index.describe_for_prompt(root,query)}
    if operation == 'invalidate':
        before = index.build_index(root)
        path = project/'scripts/changed.gd'
        path.write_bytes(b'extends Node\nfunc new_entry():\n\treturn 42\n')
        os.utime(path,(1000,1000))
        lib.note_files_changed(root, changed=['res://scripts/changed.gd','../outside/private.gd'])
        changed = index.semantic_snapshot(root)
        path.unlink()
        lib.note_files_changed(root,deleted=['scripts\\changed.gd'])
        return {'before':before,'changed':changed,'deleted':index.semantic_snapshot(root)}
    if operation == 'card':
        index.build_index(root)
        return attempt(lib._symbol_card,root,query)
    if operation == 'api':
        addon = sandbox/'cache-addon'
        folder = addon/'agent_api_cache'
        folder.mkdir(parents=True)
        path = folder/'default_api_cache.json'
        mode = case['mode']
        if mode == 'deployed':
            source = (native.parent if native else ROOT)/'agent_api_cache/default_api_cache.json'
            shutil.copyfile(source,path)
        elif mode == 'malformed':
            path.write_bytes(b'{invalid json')
        elif mode == 'empty':
            pass
        else:
            raise AssertionError(mode)
        return {'has_cache':api.has_cache(root,addon_dir=str(addon)),
                'api':attempt(lib._godot_api,root,query,addon_dir=str(addon)),
                'answer':lib.answer(root,query,**kwargs)}
    if operation == 'log':
        mode = case['mode']
        record = {'query':'synthetic русский','result':'ok','kept':[1,2]}
        if mode == 'missing-parent':
            with patch.dict('sys.modules',{'minilich':None}):
                lib._log_query(root,record)
        elif mode == 'missing-data':
            parent = subjects['parent']
            del parent.ml_data
            try:
                # A native filename loader cached this descendant while loading .ml_data.
                # Remove that cache too: otherwise this is NOT a missing dependency.
                with patch.dict('sys.modules'):
                    sys.modules.pop('minilich.ml_data',None)
                    lib._log_query(root,record)
            finally:
                parent.ml_data = data
        elif mode == 'storage-error':
            with patch.object(data,'storage_dir',side_effect=OSError('synthetic denied')):
                lib._log_query(root,record)
        else:
            if mode == 'history':
                data.set_storage_base(None)
            elif mode == 'fallback':
                data.set_storage_base(None)
                # Explicit external project parameter: fallback never targets repository.
                with patch.object(data.history,'get_storage_dir',return_value=None):
                    lib._log_query(str(sandbox/'fallback-project'),record)
                return {'record_unmutated':record,'fallback':(sandbox/'fallback-project/.agent_history/minilich/librarian_log.jsonl').read_bytes()}
            path = Path(data.storage_dir(root))/lib._LOG_FILE
            if mode.startswith('rotation-'):
                path.write_bytes(b'x'*int(mode.split('-')[1]))
            lib._log_query(root,record)
            if mode == 'append':
                lib._log_query(root,{'query':'second','result':'no_matches'})
        return {'record_unmutated':record}
    if operation == 'policy-path':
        path = case['path']
        return {'guard':subjects['guard'].can_read_project_path(path,root),
                'entry':index._build_entry(root,path),'semantic':index._build_semantic_entry(root,path)}
    raise AssertionError(operation)
