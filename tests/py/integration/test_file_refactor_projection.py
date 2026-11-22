"""C.22 consumes the C.21 public projection, never a second reference scanner."""
from python.modules.editing import paths_preview


def test_file_projection_preserves_literal_eol_and_relative_match_offsets():
    documents = {
        "res://src/a.gd": {"text": 'const B=preload("b.gd")\r\n', "bom": True},
        "res://ref.gd": {"text": 'const A=load("src/a.gd")\rOTHER\n', "bom": False},
    }
    projected = paths_preview.project_file(documents, {"src/a.gd", "src/b.gd", "ref.gd"},
                                           set(), "res://src/a.gd", "res://deep/a.gd", True)
    assert projected["res://src/a.gd"] == {
        "text": 'const B=preload("res://src/b.gd")\r\n', "occurrences": 1}
    assert projected["res://ref.gd"] == {
        "text": 'const A=load("res://deep/a.gd")\rOTHER\n', "occurrences": 1}


def test_directory_extraction_preserves_preexisting_reference_rows():
    from python.modules.editing.paths_preview.domain import directory
    documents = {
        "res://tree/a.gd": {"text": 'const S="res://tree"\n', "bom": False},
        "res://ref.gd": {"text": 'const A=load("tree/a.gd")\n', "bom": False},
    }
    rows = directory.references(documents, "res://tree", "res://new", {"tree/a.gd", "ref.gd"}, set())
    projected_rows, after = paths_preview.project_directory(
        documents, "res://tree", "res://new", {"tree/a.gd", "ref.gd"}, set())
    assert projected_rows == rows
    assert after == {"res://tree/a.gd": 'const S="res://new"\n',
                     "res://ref.gd": 'const A=load("res://new/a.gd")\n'}
