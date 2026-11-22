"""D20 native files-first order and file-only quota, including empty dirs."""


def test_files_first_empty_dirs_and_quota():
    from python.modules.project_text.tree.domain import core
    entries = [{"path": "z.txt", "type": "file"}, {"path": "a", "type": "dir"},
               {"path": "a/b.gd", "type": "file"}, {"path": "empty", "type": "dir"}]
    tree = core.build(entries, "", max_entries=1)
    assert tree == {"path": "res://", "type": "dir", "count": 1, "children": [
        {"path": "res://z.txt", "type": "file", "count": 1, "children": []},
        {"path": "res://a", "type": "dir", "count": 0, "children": []}]}
