"""C.7 deletion is a read-only report; scripts are warnings, not patches."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec
from ..shared.refactor_schema import B, FILES, N, S, STRINGS, obj

WARNING = obj({'file': S, 'line': {'type': 'integer', 'minimum': 1}, 'code': S, 'message': S})
RESULT = obj({'action': {'type': 'string', 'enum': ['delete_node']}, 'scene': S,
              'target_node': S, 'target_node_path': S,
              'deleted_nodes': {'type': 'array', 'minItems': 1, 'items': S},
              'files': FILES, 'reference_count': N, 'affected_paths': STRINGS,
              'warnings': {'type': 'array', 'items': WARNING}})
TOOLS = (ToolSpec(name='node_delete_preview',
    description='Read-only native prepare_node_deletion plan; no apply/undo/history/WAL. '
                'cleanup_code defaults to true: collect warnings, never rewrite scripts. '
                'Lossless Base64 before_bytes/after_bytes; only scene_res and files.absolute omitted. '
                'Native structured diff context=3, max600 ordered rows. deleted_nodes target-first then '
                'scene order; warnings in attached-script/line order, one per noncomment matching line. '
                'Removed-node scripts excluded. reference_count counts scene removals, not warnings. '
                '.tscn and textual .scn supported.',
    args=obj({'path': S, 'node': S, 'cleanup_code': B}, ['path', 'node']),
    result=RESULT, effects='read', idempotent=True, cost='cheap',
    errors=('invalid_input', 'not_found', 'denied'),
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES}),)
