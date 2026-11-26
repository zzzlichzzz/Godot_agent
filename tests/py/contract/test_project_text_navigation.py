"""Optional navigation parameters preserve the legacy tool responses."""
import pytest

from python.runtime.bootstrap import build_agent


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    for name, text in {
        'project.godot': 'config_version=5\n',
        'actors/a.gd': 'écho\r\nline two\r\nécho\r\n',
        'actors/a.md': 'écho\n',
        'group.txt': ('needle ' + 'x' * 80 + '\n') * 20 + '\n\n\nneedle\n',
        'actors_extra/b.gd': 'écho\n',
        'addons/other/hidden.gd': 'écho\n',
    }.items():
        file = root / name
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_bytes(text.encode('utf-8-sig'))
    return build_agent(root, 'test', state_dir=tmp_path / 'state')


def result(project, tool, **args):
    answer = project.call(tool, args)
    assert answer['ok'], answer
    return answer['result']


def test_line_range_and_unicode_continuation(project):
    path = 'res://actors/a.gd'
    first = result(project, 'read', path=path, start_line=2, end_line=3, max_chars=6)
    assert first['content'] == 'line t' and first['truncated'] and first['next_offset'] == 11
    last = result(project, 'read', path=path, start_line=2, end_line=3, offset=first['next_offset'])
    assert last['content'] == 'wo\nécho\n' and not last['truncated'] and last['next_offset'] is None
    assert result(project, 'read', path=path, start_line=20)['content'] == ''
    assert project.call('read', dict(path=path, start_line=3, end_line=2))['kind'] == 'invalid_input'
    assert set(result(project, 'read', path=path)) == {'path', 'content', 'chars', 'truncated'}


def test_search_pages_do_not_skip_or_duplicate_groups(project):
    args = dict(query='écho', context_lines=0, max_results=1,
                include_rel_prefixes=['actors/'], only_exts=['.GD'])
    first = result(project, 'search', **args, offset=0)
    assert [(m['path'], m['line']) for m in first['matches']] == [('res://actors/a.gd', 1)]
    assert first['truncated'] and first['next_offset'] == 1
    last = result(project, 'search', **args, offset=first['next_offset'])
    assert [m['line'] for m in last['matches']] == [3]
    assert not last['truncated'] and last['next_offset'] is None
    assert not result(project, 'search', **args, offset=2)['matches']
    assert result(project, 'search', query='écho', max_results=1)['truncated']
    assert not result(project, 'search', query='écho', include_rel_prefixes=['addons'], offset=0)['matches']
    assert project.call('search', dict(query='écho', include_rel_prefixes=['../actors']))['kind'] == 'invalid_input'


def test_read_directory_has_a_hint_only_for_an_allowed_directory(project):
    error = project.call('read', {'path': 'res://actors'})
    assert error['kind'] == 'not_found' and error['details'] == {'target_type': 'directory'}
    assert 'tree' in error['hint']
    for path, kind in [('res://missing', 'not_found'), ('res://addons/other', 'denied')]:
        error = project.call('read', {'path': path})
        assert error['kind'] == kind and not error.get('details')


def test_tree_public_depth_quota_and_policy(project):
    assert 'tree' in {tool['name'] for tool in project.tools()}
    root = result(project, 'tree', max_depth=0)
    assert [row['path'] for row in root['children']] == ['res://group.txt', 'res://project.godot']
    tree = result(project, 'tree', subdir='res://actors', only_exts=['.GD'])
    assert [row['path'] for row in tree['children']] == ['res://actors/a.gd']
    assert tree['count'] == 1 and not tree['truncated']
    capped = result(project, 'tree', subdir='res://actors', max_entries=1)
    assert capped['count'] == 1 and capped['truncated']
    assert 'addons' not in str(result(project, 'tree'))
    assert project.call('tree', {'max_entries': 501})['kind'] == 'invalid_input'


def test_public_tree_bounds_empty_directories_and_scan_budget(tmp_path, monkeypatch):
    from python.modules.project_text.tree.tools import TREE

    (tmp_path / 'project.godot').write_text('config_version=5\n', encoding='utf-8')
    for name in ('a', 'b', 'c'):
        (tmp_path / name).mkdir()
    agent = build_agent(tmp_path, 'test', state_dir=tmp_path / '.state')
    monkeypatch.setitem(TREE.limits, 'max_nodes', 3)
    root = result(agent, 'tree')
    assert root['truncated'] and root['count'] == 1
    assert [row['path'] for row in root['children']] == ['res://project.godot', 'res://a']
    monkeypatch.setitem(TREE.limits, 'max_scanned', 2)
    root = result(agent, 'tree')
    assert root['truncated'] and not root['children']
    assert not result(agent, 'tree', subdir='res://a')['truncated']


def test_snippet_cap_preserves_group_boundaries(project):
    args = dict(query='needle', max_results=1, context_lines=2, snippet_chars=64)
    first = result(project, 'search', **args, offset=0)
    assert first['matches'][0]['line'] == 1 and first['next_offset'] == 1
    snippet = first['matches'][0]['snippet']
    assert len(snippet) == 64 and snippet.endswith('…')
    second = result(project, 'search', **args, offset=first['next_offset'])
    assert second['matches'][0]['line'] == 24 and second['next_offset'] is None
