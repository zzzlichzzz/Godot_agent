"""Bounded public view; the internal builder retains its original limits."""
from python.kernel.tool_spec import ToolSpec

NODE = {"type": "object", "properties": {
    "path": {"type": "string"}, "type": {"type": "string", "enum": ["dir", "file"]},
    "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
    "count": {"type": "integer", "minimum": 0}},
    "required": ["path", "type", "children", "count"], "additionalProperties": False}
TREE = ToolSpec(
    name="tree", description="List permitted project files and directories under res://. Narrow by subdir or max_depth if the scan is truncated, or filter the output with only_exts.",
    args={"type": "object", "properties": {
        "subdir": {"type": "string", "default": "res://", "maxLength": 1024},
        "max_depth": {"type": "integer", "minimum": 0, "maximum": 12, "default": 3,
                      "description": "0 lists only files directly in subdir."},
        "max_entries": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200,
                        "description": "Maximum files; directories have a separate node limit."},
        "only_exts": {"type": "array", "maxItems": 64,
                      "items": {"type": "string", "maxLength": 32}}},
        "additionalProperties": False},
    result=dict(NODE, properties=dict(NODE["properties"], truncated={"type": "boolean"}),
                required=NODE["required"] + ["truncated"], **{"$defs": {"node": NODE}}),
    effects="read", idempotent=True, errors=("invalid_input", "not_found", "denied"),
    limits={"max_depth": 12, "max_entries": 500, "max_nodes": 600, "max_scanned": 4096})
TOOLS = (TREE,)
