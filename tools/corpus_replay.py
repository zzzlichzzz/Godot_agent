"""D52 record loading and the explicitly authorized librarian reference route."""
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
            return ordinary(agent_cache, folder, only)
        return run
    return decorate
