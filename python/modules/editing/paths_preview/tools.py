"""D1/D4: one native public read tool; projected references, never a write plan."""
from python.kernel.tool_spec import ToolSpec

MAX_FILE_BYTES = 5 * 1024 * 1024


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


ARGS = object_schema({"old_path": {"type": "string"}, "new_path": {"type": "string"}})
REL_MATCH = {"type": "array", "minItems": 3, "maxItems": 3,
             "prefixItems": [{"type": "integer", "minimum": 0},
                             {"type": "integer", "minimum": 0}, {"type": "string"}],
             "items": {"type": ["integer", "string"]}}
FILE = object_schema({"path": {"type": "string"}, "occurrences": {"type": "integer", "minimum": 0},
                      "exact_matches": {"type": "integer", "minimum": 0},
                      "rel_matches": {"type": "array", "items": REL_MATCH}, "bom": {"type": "boolean"}})
RESULT = object_schema({"old_path": {"type": "string"}, "new_path": {"type": "string"},
                        "is_directory": {"type": "boolean"}, "file_count": {"type": "integer", "minimum": 0},
                        "reference_count": {"type": "integer", "minimum": 0},
                        "files": {"type": "array", "items": FILE}, "source_text": {"type": ["string", "null"]}})
TOOLS = (ToolSpec(name="paths_preview", description="Ссылки на путь и проекция внутренних путей без записи.",
                  args=ARGS, result=RESULT, effects="read", idempotent=True, requires_preview=False,
                  errors=("invalid_input", "not_found", "conflict", "denied"), availability="*",
                  limits={"max_file_bytes": MAX_FILE_BYTES}),)
