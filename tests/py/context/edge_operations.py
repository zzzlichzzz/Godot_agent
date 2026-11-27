"""Native-measured quota, cutoff and exact budget-edge cases."""
from unittest.mock import patch
from tests.py.context.observations import attempt

def run(subjects,root,sandbox,case):
    lib,index,parser=(subjects[name] for name in ('lib','index','parser'))
    mode,query=case['mode'],case.get('query','take_damage')
    root=str(root)
    kwargs={'addon_dir':str(sandbox/'cache-addon')}
    if mode=='exact-budget-edges':
        full=lib.answer(root,query,budget_chars=100000,**kwargs)
        assert full.endswith(lib.FOOTER)
        lines=full[:-len(lib.FOOTER)].rstrip('\n').splitlines()
        total,budgets=0,{399,400,401}
        for line in lines:
            total+=len(line)+1
            edge=total+len(lib.FOOTER)+8
            budgets.update((edge-1,edge,edge+1))
        return {'full':full,'answers':{str(b):lib.answer(root,query,budget_chars=b,**kwargs) for b in sorted(budgets)}}
    if mode=='ranking':
        hits=[{'path':'scripts/take_damage.gd','kind':'gd','symbols':['func:take_damage'],'score':10},
              {'path':'scripts/take_damage_other.gd','kind':'gd','symbols':['var:health'],'score':10},
              {'path':'scenes/take_damage.tscn','kind':'tscn','symbols':['Hero:Node'],'score':10},
              {'path':'docs/take_damage.md','kind':'md','symbols':[],'score':10},
              {'path':'scripts/tie_a.gd','kind':'gd','symbols':[],'score':10},
              {'path':'scripts/tie_b.gd','kind':'gd','symbols':[],'score':10}]
        extra=lib._expanded_query(query)[1]
        phrase=lib._phrase_key(query)
        # Same-score ties and exact cutoff equality are observed, not guessed.
        return {'reranked':lib._rerank_hits(hits,query,extra),
                'phrase':[lib._phrase_rank(h['symbols'],phrase,phrase.replace('_','')) for h in hits],
                'cut_ratio':lib.MAP_CUT_RATIO,'expanded':lib._expanded_query(query)}
    if mode=='quotas':
        limits={name:1 for name in ('MAP_LIMIT','STRUCT_FILES','SIG_PER_FILE','FRAGMENT_LIMIT','FRAG_PER_FILE',
            'CALLERS_LIMIT','CALLERS_FUNCS','AUTOLOAD_LIMIT','SIGNALS_MAX','SIGNALS_LIMIT','CARD_MAX_REFS')}
        with patch.multiple(lib,**limits):
            index.build_index(root)
            hits=index.search(root,query,limit=24)
            return {'answer':lib.answer(root,query,budget_chars=100000,**kwargs),
                'structure':lib._structure(root,hits),'fragments':lib._fragments(root,query),
                'callers':lib._callers(root,query,hits),'signals':lib._signal_wiring(root,query,hits),
                'autoloads':lib._autoloads(root),'card':attempt(lib._symbol_card,root,query)}
    if mode=='incomplete-index':
        with patch.object(index,'MAX_FILES',1):
            return {'build':index.build_index(root),'meta':index.index_meta(root),
                'answer':lib.answer(root,query,budget_chars=6000,**kwargs)}
    if mode=='symbol-round-robin':
        symbols=['func:f1','func:f2','class:C','signal:changed','const:VALUE','var:health','var:speed']
        with patch.object(index,'MAX_SYMBOLS',2):
            return {'capped':index._cap_symbols(symbols,limit=2),'entry':index._build_entry(root,'scripts/player.gd'),
                'semantic':index._build_semantic_entry(root,'scripts/player.gd')}
    if mode=='grep-budgets':
        calls=[]
        def searching(*args,**kwargs):
            calls.append({'args':list(args),'kwargs':kwargs})
            return [],False
        with patch.object(lib,'search_project_text',side_effect=searching):
            fragments=lib._fragments(root,query)
            patterns=lib._grep_patterns(root,['take_damage','take_damage','health_changed'],2)
        return {'calls':calls,'fragments':fragments,'patterns':patterns,
            'expansion_limit':lib._SYN_EXPAND_LIMIT,'synonym_grep_limit':lib._SYN_GREP_LIMIT,
            'shared_synonym_budget':lib._FRAG_GREP_BUDGET,'expanded':lib._expanded_query(query)}
    if mode=='card-caps':
        source='extends Node\nfunc big_card(a, b, c):\n\tvar x = a\n\tvar y = b\n\tvar z = c\n\thealth = x + y + z\n\treturn velocity + speed\n'
        semantic=parser.parse(source,'scripts/player.gd')
        snapshot={'files':[{'path':'scripts/player.gd','semantic':semantic}],'complete':True}
        with patch.object(index,'semantic_snapshot',return_value=snapshot),patch.multiple(lib,
            CARD_MAX_PARAMS=1,CARD_MAX_LOCALS=1,CARD_MAX_USES=1,CARD_MAX_REFS=1):
            return lib._symbol_card(root,'big_card')
    if mode=='cached-search':
        index.build_index(root)
        first=index.search(root,query)
        calls=[]
        original=index._tokens
        def tokens(text):
            calls.append(text)
            return original(text)
        with patch.object(index,'_tokens',side_effect=tokens):
            second=index.search(root,query)
            third=index.search(root,query)
        return {'first':first,'second':second,'third':third,'tokenized':calls}
    raise AssertionError(mode)
