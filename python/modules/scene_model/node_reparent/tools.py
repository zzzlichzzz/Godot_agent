"""C.7 read-only native prepare projection; never an apply endpoint."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec
from ..shared.refactor_schema import B, FILES, N, S, STRINGS, obj

RESULT = obj({'action': {'type': 'string', 'enum': ['reparent_node']}, 'scene': S,
              'old_path': S, 'new_path': S, 'new_parent': S, 'target_node': S,
              'target_node_path': S, 'files': FILES, 'reference_count': N,
              'affected_paths': STRINGS})
TOOLS = (ToolSpec(name='node_reparent_preview',
    description='Read-only native prepare_node_reparent plan; no apply/undo/history/WAL. '
                'update_scripts defaults to true. Lossless Base64 before_bytes/after_bytes; '
                'only scene_res duplicate and files.absolute omitted. Native structured diff context=3, '
                'max600 ordered [kind,old_line|null,new_line|null,text] rows. '
                'target_node is name; target_node_path is old path; new_parent is resolved path, root=".". '
                'Scene-first files order; quoted $ paths for .. or nonidentifier components. '
                '.tscn and textual .scn supported.',
    args=obj({'path': S, 'node': S, 'new_parent': S, 'update_scripts': B},
             ['path', 'node', 'new_parent']),
    result=RESULT, effects='read', idempotent=True, cost='cheap',
    errors=('invalid_input', 'not_found', 'denied'),
    limits={'max_file_bytes': READ_TEXT_MAX_BYTES}),)
