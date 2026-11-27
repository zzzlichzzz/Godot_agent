"""D20 typed native read; quotas count Unicode characters, never bytes."""
from python.kernel.tool_spec import ToolSpec

READ = ToolSpec(
    name="read",
    description="Read a project file (UTF-8, LF). Select an inclusive line range or continue with next_offset.",
    args={"type": "object", "properties": {
        "path": {"type": "string", "minLength": 6, "description": "Путь файла res://."},
        "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000, "default": 50000},
        "start_line": {"type": "integer", "minimum": 1, "description": "First line, 1-based."},
        "end_line": {"type": "integer", "minimum": 1, "description": "Last line, inclusive."},
        "offset": {"type": "integer", "minimum": 0, "description": "Absolute character offset in the decoded file. Keep the same range when continuing."}},
        "required": ["path"], "additionalProperties": False},
    result={"type": "object", "properties": {
        "path": {"type": "string", "description": "Канонический res:// путь, не абсолютный."},
        "content": {"type": "string"}, "truncated": {"type": "boolean"},
        "chars": {"type": "integer", "minimum": 0, "maximum": 200000},
        "next_offset": {"type": ["integer", "null"], "minimum": 0,
                        "description": "With a range or offset: next offset, or null at the end of the selection."}},
        "required": ["path", "content", "truncated", "chars"], "additionalProperties": False},
    effects="read", idempotent=True, errors=("invalid_input", "not_found", "denied"),
    limits={"default_chars": 50000, "max_chars": 200000})
TOOLS = (READ,)
