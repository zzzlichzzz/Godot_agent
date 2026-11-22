"""Fresh pure architecture map and index with native segmented glob policy."""
import json

import pytest


@pytest.mark.parametrize('raw', [None,{},[],{'zones':{}}])
def test_map_missing_or_broken(raw):
    from python.modules.editing.split_py.domain.arch import load_map
    assert load_map(raw) is None


def test_map_globs_defaults_and_no_cache():
    from python.modules.editing.split_py.domain import arch
    raw = json.dumps({'zones':[{'glob':'**/*.py','role':'core'}]}).encode()
    first, second = arch.load_map(json.loads(raw)), arch.load_map(json.loads(raw))
    first['zones'][0]['role'] = 'changed'
    assert arch.zone_for(second,'a.py')['role'] == 'core'
    assert arch.zone_for(second,'a/b.py')['role'] == 'core'
    assert arch.zone_for(second,'a.gd') is None
    assert arch.line_policy(None) == {'warn':1500,'max':2000,'exts':['.py','.gd'],
                                     'exempt_roles':['workflow','generated','tasks','reports']}


def test_native_name_index_skips_private_broken_and_only_native_dirs():
    from python.modules.editing.split_py.domain import arch
    raw = b'def public(): pass\nasync def async_fn(): pass\nclass Public: pass\ndef _private(): pass\n'
    result = arch.name_index([('a.py',raw),('dist/b.py',raw),('.hidden/c.py',raw),
                              ('_tmp/d.py',raw),('broken.py',b'def broken(:'),('a.gd',raw)])
    assert result == {name:[('_tmp/d.py',kind),('a.py',kind)]
                      for name,kind in [('public','def'),('async_fn','def'),('Public','class')]}
