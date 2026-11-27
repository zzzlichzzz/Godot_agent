"""Closed public envelope; parsed native action remains explicitly inert JSON."""
from python.kernel.tool_spec import ToolSpec
from .domain.request import MAX_TEXT

FINDING = {'type': 'object', 'properties': {
    'severity': {'type': 'string', 'enum': ['blocking', 'warning']},
    'category': {'type': 'string'}, 'message': {'type': 'string'},
    'path': {'type': 'string'}, 'step': {'type': 'integer'}},
    'required': ['severity', 'category', 'message'], 'additionalProperties': False}
RESULT = {'type': 'object', 'properties': {
    'score': {'type': 'integer', 'minimum': 0, 'maximum': 100},
    'acceptable': {'type': 'boolean'}, 'vote_eligible': {'type': 'boolean'},
    'blocking': {'type': 'array', 'items': FINDING},
    'warnings': {'type': 'array', 'items': FINDING},
    'evidence': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 12},
    'action': {'type': ['object', 'null'], 'additionalProperties': True,
               'description': 'Opaque parsed answer JSON, including invalid/unknown fields; never executed.'},
    'structural_score': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 7, 'maxItems': 7}},
    'required': ['score', 'acceptable', 'vote_eligible', 'blocking', 'warnings', 'evidence', 'action', 'structural_score'],
    'additionalProperties': False}
JUDGE = ToolSpec(name='judge', description='Детерминированная оценка ответа по проекту; только чтение, без применения действий.',
    args={'type': 'object', 'properties': {'full_text': {'type': 'string', 'minLength': 1, 'maxLength': MAX_TEXT}},
          'required': ['full_text'], 'additionalProperties': False}, result=RESULT,
    effects='read', idempotent=True, errors=('invalid_input', 'not_found', 'denied'),
    cost='bounded', limits={'max_text_chars': MAX_TEXT, 'max_evidence': 12})
TOOLS = (JUDGE,)
