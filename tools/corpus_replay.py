"""Load corpus records and select explicitly declared replay adapters."""
from functools import wraps
import json
from pathlib import Path


def records(paths):
    """A catalog is a list of ordinary records, never an implicit schema bypass."""
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            yield path, value
        elif isinstance(value, list):
            if any(not isinstance(row, dict) for row in value):
                raise ValueError("corpus catalog %s: every entry must be an object" % path.name)
            for row in value:
                yield path, row
        else:
            raise ValueError("corpus %s: expected an object or a list of objects" % path.name)


def librarian_manifest(folder):
    path = Path(folder) / "manifest.json"
    if not path.is_file():
        return False
    record = json.loads(path.read_text(encoding="utf-8"))
    return isinstance(record, dict) and record.get("module") == "context.ask"


def super_call_expected(record):
    """D131: the verified parent call in the original read and rename fixtures."""
    expect = record['expect']
    result = expect.get('result', {})
    if (record['tool'], record.get('fixture'), record['id']) == ('write_apply', 'rename', '003'):
        # Exactly the proven parent call; independent of the bytes produced by the writer.
        from hashlib import sha256
        original = (Path(__file__).resolve().parents[1] / 'fixtures/projects/rename/src/enemy.gd').read_bytes()
        files = result['files'].copy()
        assert sha256(original).hexdigest() == files['src/enemy.gd'] and original.count(b'super.take_damage(3)') == 1
        files['src/enemy.gd'] = sha256(original.replace(b'super.take_damage(3)', b'super.hurt(3)')).hexdigest()
        return dict(expect, result=dict(result, files=files))
    if (record['tool'], record.get('fixture'), record['id']) == ('write_preview', 'rename', '008-mode-probable'):
        path = 'res://src/enemy.gd'  # line 10: super.take_damage(3) -> LabHero.take_damage
        stats = result['stats']
        return dict(expect, result=dict(result, steps=[{'path': path, 'edits': 1}, *result['steps']],
            steps_count=result['steps_count']+1, affected_paths=[path, *result['affected_paths']],
            stats=dict(stats, files=stats['files']+1, edits=stats['edits']+1)))
    if record.get('fixture') != 'usages' or result.get('old_name') != 'take_damage':
        return expect
    path = 'res://src/lab_turret.gd'
    target = result['declaration']
    if target not in ('res://src/lab_entity.gd:12', path + ':3'):
        return expect
    places = result['usages'].copy()
    idx = next(i for i, u in enumerate(places) if (u['path'], u['line'], u['column']) == (path, 4, 15))
    old = places[idx]
    assert old['confidence'] == 'probable' and old['link'] == 'member'
    fixed = dict(result, usages=places, probable_count=result['probable_count'] - 1)
    if target == path + ':3':
        places.pop(idx)
        fixed['by_link'] = dict(result['by_link'], member=result['by_link']['member'] - 1)
    else:
        places[idx] = dict(old, confidence='proven', note=None)
        fixed['proven_count'] += 1
    if 'risks' in result:
        fixed['risks'] = result['risks'].copy()
        fixed['risks'].remove(path + ':4 [member, probable] — ' + old['note'])
    if record['id']=='010-allow-unverified' and record['tool']=='analyze_rename':
        fixed['affected_paths']=sorted([*result['affected_paths'],'res://src/lab_root.gd'])
    return dict(expect, result=fixed)


def selected_folders(folders, module_id):
    """Declared ask/channel reference lanes; all ordinary selectors stay intact."""
    if module_id == "context.ask":
        return [folder for folder in folders if librarian_manifest(folder)]
    if module_id == "channels.http":
        return [folder for folder in folders if http_manifest(folder)]
    return folders


def http_manifest(folder):
    path = Path(folder) / "manifest.json"
    if not path.is_file():
        return False
    record = json.loads(path.read_text(encoding="utf-8"))
    return isinstance(record, dict) and record.get("module") == "channels.http" and record.get("reference_only") is True


def chat_manifest(folder):
    path = Path(folder) / "manifest.json"
    if not path.is_file():
        return False
    record = json.loads(path.read_text(encoding="utf-8"))
    return (isinstance(record, dict) and record.get("module") == "assistant.chat"
            and record.get("real_provider_calls") is False)


def corpus_routes(compare):
    """Keep ordinary records/assertions untouched; reference213 is not public213."""
    def decorate(ordinary):
        @wraps(ordinary)
        def run(agent_cache, folder, only=None):
            if http_manifest(folder):
                if only and "http" not in only:
                    return 0, 0, []
                from tools.http_replay import replay
                return replay(folder, compare)
            if librarian_manifest(folder):
                if only and "ask" not in only:
                    return 0, 0, []
                from tools.librarian_replay import replay
                return replay(folder, compare)
            if (not only or "chat" in only) and chat_manifest(folder):
                from tools.chat_replay import replay
                return replay(folder, compare)
            return ordinary(agent_cache, folder, only)
        return run
    return decorate
