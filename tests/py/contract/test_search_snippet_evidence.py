"""A short search preview must provide evidence for its first matching line."""
from python.runtime.bootstrap import build_agent


def test_clipping_keeps_first_hit_and_real_page_boundaries(tmp_path):
    root = tmp_path / 'project'
    (root / 'src').mkdir(parents=True)
    (root / 'project.godot').write_text('config_version=5\n', 'utf8')
    source = 'x'*210+'\nsignal Collected()\n\n\n\n'+'İ'*350+' Collected() '+'z'*100
    (root / 'src/sample.gd').write_text(source, 'utf8')
    (root / 'notes.md').write_text('Collected()\n', 'utf8')
    agent = build_agent(root, 'test', state_dir=tmp_path/'state')
    def search(**args):
        reply = agent.call('search', dict(query='COLLECTED()', case_insensitive=True,
            snippet_chars=120, offset=0, context_lines=1) | args)
        assert reply['ok'], reply
        return reply['result']
    assert len(search()['matches']) == 3
    assert [r['path'] for r in search(exclude_rel_prefixes=['src/'])['matches']] == ['res://notes.md']
    rows = search(include_rel_prefixes=['src'])['matches']
    assert [r['line'] for r in rows] == [2, 6]
    for row in rows:
        assert len(row['snippet']) <= 120
        assert 'Collected()' in next(s for s in row['snippet'].splitlines() if s.startswith(f"{row['line']}: "))
    first = search(include_rel_prefixes=['src'], max_results=1)
    last = search(include_rel_prefixes=['src'], max_results=1, offset=first['next_offset'])
    assert first['matches'] + last['matches'] == rows and last['next_offset'] is None
    long_line = search(query='İİ Collected()', snippet_chars=16000)['matches'][0]['snippet']
    assert 'İİ Collected()' in long_line and len(long_line) <= 303
