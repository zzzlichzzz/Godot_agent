"""Shared strict wire data for the two C.7 prepare-only reports."""


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


S = {'type': 'string'}
N = {'type': 'integer', 'minimum': 0}
B = {'type': 'boolean'}
BYTES = {'type': 'string', 'pattern': r'^[A-Za-z0-9+/]*={0,2}$'}
STRINGS = {'type': 'array', 'items': S}
DIFF = obj({'lines': {'type': 'array', 'maxItems': 600,
                    'items': {'type': 'array', 'minItems': 4, 'maxItems': 4,
                              'items': {'type': ['string', 'integer', 'null']}}},
            'added': N, 'removed': N, 'truncated': B, 'path': S,
            'action': {'type': 'string', 'enum': ['patch_file']}})
FILE = obj({'action': {'type': 'string', 'enum': ['patch_file']}, 'path': S,
            'before_hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
            'before_bytes': BYTES, 'after_bytes': BYTES, 'diff': DIFF, 'occurrences': N})
FILES = {'type': 'array', 'minItems': 1, 'items': FILE}
