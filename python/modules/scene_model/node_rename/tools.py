"""Read-only native-prepare projection; no executor, plan store or write port."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


S = {'type': 'string'}
N = {'type': 'integer', 'minimum': 0}
B = {'type': 'boolean'}
BYTES = {'type': 'string', 'pattern': r'^[A-Za-z0-9+/]*={0,2}$'}
DIFF = obj({'lines': {'type': 'array', 'items': {'type': 'array', 'minItems': 4, 'maxItems': 4,
                'items': {'type': ['string', 'integer', 'null']}}}, 'added': N, 'removed': N,
            'truncated': B, 'path': S, 'action': {'type': 'string', 'enum': ['patch_file']}})
FILE = obj({'action': {'type': 'string', 'enum': ['patch_file']}, 'path': S, 'before_hash': S,
            'before_bytes': BYTES, 'after_bytes': BYTES, 'diff': DIFF, 'occurrences': N})
RESULT = obj({'action': {'type': 'string', 'enum': ['rename_node']}, 'scene': S,
              'old_name': S, 'new_name': S, 'old_path': S, 'new_path': S, 'target_node_path': S,
              'files': {'type': 'array', 'items': FILE}, 'reference_count': N,
              'affected_paths': {'type': 'array', 'items': S}, 'scripts_only': B, 'previous_name': S})
TOOLS = (ToolSpec(name='node_rename_preview',
    description='Read-only prepare_node_rename projection: scene and attached-script diffs, no apply/undo. '
                'before_bytes/after_bytes are lossless base64 ASCII; scene_res duplicate and host absolute paths omitted. '
                'Optional update_scripts=true, scripts_only=false, previous_name="". Structured diff context=3, max600 rows. '
                'Diff rows retain native [kind,old_line|null,new_line|null,text] order; .tscn and textual .scn supported.',
    args=obj({'path': S, 'node': S, 'new_name': S, 'update_scripts': B, 'scripts_only': B, 'previous_name': S},
             ['path', 'node', 'new_name']), result=RESULT, effects='read', idempotent=True,
    errors=('invalid_input', 'not_found', 'denied'), cost='cheap', limits={'max_file_bytes': READ_TEXT_MAX_BYTES}),)
