"""formats/gdscript - один разбор GDScript на весь агент (R-04, R-14).

Публичное API ровно то же, что у эталонного `gd_semantic_parser`:
`tokenize(text)` и `parse(text, path="")`, плюс `script_parent` — факт
`extends`, нужный поиску использований. Внутри пакета нет ни IO, ни Godot.
"""

from python.formats.gdscript.declarations import line_indents, parse
from python.formats.gdscript.parent import exact_string_value, script_parent
from python.formats.gdscript.tokens import tokenize

__all__ = ["tokenize", "parse", "line_indents", "script_parent",
           "exact_string_value"]

# C.5: coarse reference facts, without changing tokenize/parse.
from python.formats.gdscript.handler_facts import handlers, custom_signals, method_connected
__all__ += ["handlers", "custom_signals", "method_connected"]

# C.6 append-only literal rewrite; tokenizer/parse unchanged.
from .node_paths import rename_node_paths
# Explicit C.6 API, without changing accepted star exports.

# C.7 append-only explicit API; accepted star exports stay closed.
from .node_paths import reparent_node_paths, deleted_node_references
