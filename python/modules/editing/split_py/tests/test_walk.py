"""Native lexical import quirks and scan eligibility; no AST improvements."""
import pytest


@pytest.mark.parametrize('line, expected', [
    ('import donor', (['donor'], [])), ('import donor as alias', (['donor'], ['alias'])),
    ('  import os, .donor as d, sys', (['os','donor','sys'], ['d'])),
    ('from ..pkg.donor import fn', (['pkg.donor'], [])),
    ('from ( donor ) import fn', (['donor'], [])), ('import\tdonor', (['donor'], [])),
    ('# import donor', ([], [])), ('x = "import donor"', ([], [])),
    ('from donor import fn as f', (['donor'], [])), ('import donor_other', (['donor_other'], [])),
])
def test_imports(line, expected):
    from python.modules.editing.split_py.domain.walk import imports
    assert imports(line) == expected


@pytest.mark.parametrize('candidate, expected', [('donor',True),('pkg.donor',True),
    ('deep.pkg.donor',True),('donor_other',False),('mydonor',False),('donor.pkg',False)])
def test_module_matches(candidate, expected):
    from python.modules.editing.split_py.domain.walk import module_matches
    assert module_matches(candidate, 'donor') is expected


@pytest.mark.parametrize('directory', ['__pycache__','.git','.godot','.import','.agent_history',
    'dist','build','minilich_brain','parser_corpus','agent_api_cache','node_modules','.venv','_tmp','.hidden'])
def test_skip_any_ancestor(directory):
    from python.modules.editing.split_py.domain.walk import eligible
    assert not eligible(directory+'/ref.py') and not eligible('nested/'+directory+'/ref.py')


@pytest.mark.parametrize('rel, expected', [('ref.py',True),('upper.PY',True),('.ref.py',True),
    ('ref.md',True),('ref.gd',True),('ref.cfg',True),('pkg/node_modules_like/ref.py',True),
    ('ref.bin',False),('ref',False)])
def test_extensions(rel, expected):
    from python.modules.editing.split_py.domain.walk import eligible
    assert eligible(rel) is expected
