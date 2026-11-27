"""Append-only legacy text grammar: neutral tokens/spans, never lint or IO.

Specification port from ba0535d4 tscn_lint.py regex vocabulary.
Regex objects do not cross the formats boundary; callbacks receive data only.
"""
import re
from dataclasses import dataclass

_MATH_CTORS = ('Vector2', 'Vector2i', 'Vector3', 'Vector3i', 'Vector4', 'Vector4i', 'Quaternion', 'Color', 'Rect2', 'Rect2i', 'AABB', 'Plane', 'Basis', 'Transform2D', 'Transform3D')
_ANY_SECTION_RE = re.compile('^\\[\\s*([A-Za-z_][A-Za-z0-9_]*)')
_ATTR_RE = re.compile('(\\w+)=(?:"([^"]*)"|(ExtResource|SubResource)\\(\\s*"?([^")\\s]+)"?\\s*\\)|(-?\\d+(?:\\.\\d+)?))')
_CLOSING_TAG_RE = re.compile('^\\[/[A-Za-z_][A-Za-z0-9_]*\\]$')
_CONNECTION_RE = re.compile('^\\[connection\\b([^\\]\\n]*)\\]', re.M)
_CTOR_ARGS_RE = re.compile('^\\s*[A-Za-z_][A-Za-z0-9_/]*\\s*=\\s*([A-Za-z_][A-Za-z0-9_]*)\\.new\\(\\s*[^)\\s]')
_CTOR_LINE_RE = re.compile('^(\\s*[A-Za-z_][A-Za-z0-9_/]*\\s*=\\s*)([A-Za-z_][A-Za-z0-9_]*)\\.new\\(\\s*\\)\\s*$')
_CTOR_VALUE_RE = re.compile('^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*\\s*\\(')
_DOTTED_PROP_RE = re.compile('^\\s*([A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+)\\s*=')
_EXTCALL_RE = re.compile('ExtResource\\(\\s*"?([^")\\s]+)"?\\s*\\)')
_EXT_RE = re.compile('\\[ext_resource\\b([^\\]]*)\\]')
_HEADER_RE = re.compile('\\[gd_scene\\b([^\\]]*)\\]')
_KEYWORD_VALUE_RE = re.compile('^(?:true|false|null|nan|inf|-inf)$')
_MATH_CTOR_ARGS_RE = re.compile('\\b(%s)\\(([^()]*)\\)' % '|'.join(_MATH_CTORS))
_METHOD_ATTR_RE_V83 = re.compile('\\bmethod="([^"]*)"')
_NAME_ATTR_RE_V83 = re.compile('\\bname="([^"]*)"')
_NEXT_SECTION_RE = re.compile('\\n\\s*\\[')
_NODEPATH_VAL_RE = re.compile('NodePath\\("([^"]*)"\\)')
_NODE_RE = re.compile('\\[node\\b([^\\]]*)\\]')
_NUM_ARG_RE = re.compile('^-?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][-+]?\\d+)?$|^-?inf$|^nan$')
_NUM_VALUE_RE = re.compile('^-?(?:\\d|\\.\\d)')
_POLYGON_PROP_RE = re.compile('^polygon\\s*=\\s*PackedVector2Array\\(([^)]*)\\)\\s*$')
_SECTION_START_RE = re.compile('^\\[(gd_scene|ext_resource|sub_resource|node|resource|connection)\\b')
_SUBCALL_RE = re.compile('SubResource\\(\\s*"?([^")\\s]+)"?\\s*\\)')
_SUB_RE = re.compile('\\[sub_resource\\b([^\\]]*)\\]')
_UID_IN_HEADER_RE = re.compile('(\\[(?:gd_scene|ext_resource)\\b[^\\]]*)\\s+uid="uid://([^"]*)"([^\\]]*\\])')
_VALID_METHOD_RE_V83 = re.compile('^[A-Za-z_]\\w*$')
_VALID_UID_RE = re.compile('^[0-9a-z]{10,}$')
_LOAD_STEPS_RE = re.compile('(\\[gd_scene\\b[^\\]]*\\bload_steps=)"?\\d+"?')
_INSTANCE_EXT_RE = re.compile('instance=ExtResource\\(\\s*"?([^")\\s]+)"?\\s*\\)')
_QUOTED_ID_RE = re.compile('\\bid="([^"]+)"')
_QUOTED_TYPE_RE = re.compile('\\btype="([^"]+)"')
_QUOTED_PATH_RE = re.compile('\\bpath="([^"]+)"')
_NUMERIC_PROPERTY_RE = re.compile('^([A-Za-z_][\\w/]*)\\s*=\\s*(-?\\d+\\.?\\d*)\\s*$')
_SUB_HEADER_START_RE = re.compile('\\[sub_resource\\b([^\\]]*)\\]')


@dataclass(frozen=True)
class Token:
    values: tuple
    spans: tuple
    def group(self, index=0):
        return self.values[index]
    def start(self, index=0):
        return self.spans[index][0]
    def end(self, index=0):
        return self.spans[index][1]


def _token(match):
    if match is None:
        return None
    indices = range(len(match.groups()) + 1)
    return Token(tuple(match.group(i) for i in indices), tuple(match.span(i) for i in indices))


def any_section_match(*args, **kwargs):
    return _token(_ANY_SECTION_RE.match(*args, **kwargs))


def attr_finditer(*args, **kwargs):
    return (_token(m) for m in _ATTR_RE.finditer(*args, **kwargs))


def closing_tag_match(*args, **kwargs):
    return _token(_CLOSING_TAG_RE.match(*args, **kwargs))


def connection_finditer(*args, **kwargs):
    return (_token(m) for m in _CONNECTION_RE.finditer(*args, **kwargs))


def ctor_args_match(*args, **kwargs):
    return _token(_CTOR_ARGS_RE.match(*args, **kwargs))


def ctor_line_match(*args, **kwargs):
    return _token(_CTOR_LINE_RE.match(*args, **kwargs))


def ctor_value_match(*args, **kwargs):
    return _token(_CTOR_VALUE_RE.match(*args, **kwargs))


def dotted_prop_match(*args, **kwargs):
    return _token(_DOTTED_PROP_RE.match(*args, **kwargs))


def ext_finditer(*args, **kwargs):
    return (_token(m) for m in _EXT_RE.finditer(*args, **kwargs))


def extcall_finditer(*args, **kwargs):
    return (_token(m) for m in _EXTCALL_RE.finditer(*args, **kwargs))


def extcall_sub(replacement, text, *args, **kwargs):
    return _EXTCALL_RE.sub(lambda m: replacement(_token(m)) if callable(replacement) else m.expand(replacement), text, *args, **kwargs)


def header_search(*args, **kwargs):
    return _token(_HEADER_RE.search(*args, **kwargs))


def instance_ext_search(*args, **kwargs):
    return _token(_INSTANCE_EXT_RE.search(*args, **kwargs))


def keyword_value_match(*args, **kwargs):
    return _token(_KEYWORD_VALUE_RE.match(*args, **kwargs))


def load_steps_sub(replacement, text, *args, **kwargs):
    return _LOAD_STEPS_RE.sub(lambda m: replacement(_token(m)) if callable(replacement) else m.expand(replacement), text, *args, **kwargs)


def math_ctor_args_finditer(*args, **kwargs):
    return (_token(m) for m in _MATH_CTOR_ARGS_RE.finditer(*args, **kwargs))


def method_attr_v83_search(*args, **kwargs):
    return _token(_METHOD_ATTR_RE_V83.search(*args, **kwargs))


def name_attr_v83_search(*args, **kwargs):
    return _token(_NAME_ATTR_RE_V83.search(*args, **kwargs))


def next_section_search(*args, **kwargs):
    return _token(_NEXT_SECTION_RE.search(*args, **kwargs))


def node_finditer(*args, **kwargs):
    return (_token(m) for m in _NODE_RE.finditer(*args, **kwargs))


def node_search(*args, **kwargs):
    return _token(_NODE_RE.search(*args, **kwargs))


def nodepath_val_finditer(*args, **kwargs):
    return (_token(m) for m in _NODEPATH_VAL_RE.finditer(*args, **kwargs))


def num_arg_match(*args, **kwargs):
    return _token(_NUM_ARG_RE.match(*args, **kwargs))


def num_value_match(*args, **kwargs):
    return _token(_NUM_VALUE_RE.match(*args, **kwargs))


def numeric_property_match(*args, **kwargs):
    return _token(_NUMERIC_PROPERTY_RE.match(*args, **kwargs))


def polygon_prop_match(*args, **kwargs):
    return _token(_POLYGON_PROP_RE.match(*args, **kwargs))


def quoted_id_search(*args, **kwargs):
    return _token(_QUOTED_ID_RE.search(*args, **kwargs))


def quoted_path_search(*args, **kwargs):
    return _token(_QUOTED_PATH_RE.search(*args, **kwargs))


def quoted_type_search(*args, **kwargs):
    return _token(_QUOTED_TYPE_RE.search(*args, **kwargs))


def section_start_match(*args, **kwargs):
    return _token(_SECTION_START_RE.match(*args, **kwargs))


def sub_finditer(*args, **kwargs):
    return (_token(m) for m in _SUB_RE.finditer(*args, **kwargs))


def sub_header_start_match(*args, **kwargs):
    return _token(_SUB_HEADER_START_RE.match(*args, **kwargs))


def sub_search(*args, **kwargs):
    return _token(_SUB_RE.search(*args, **kwargs))


def subcall_finditer(*args, **kwargs):
    return (_token(m) for m in _SUBCALL_RE.finditer(*args, **kwargs))


def subcall_sub(replacement, text, *args, **kwargs):
    return _SUBCALL_RE.sub(lambda m: replacement(_token(m)) if callable(replacement) else m.expand(replacement), text, *args, **kwargs)


def uid_in_header_sub(replacement, text, *args, **kwargs):
    return _UID_IN_HEADER_RE.sub(lambda m: replacement(_token(m)) if callable(replacement) else m.expand(replacement), text, *args, **kwargs)


def valid_method_v83_match(*args, **kwargs):
    return _token(_VALID_METHOD_RE_V83.match(*args, **kwargs))


def valid_uid_match(*args, **kwargs):
    return _token(_VALID_UID_RE.match(*args, **kwargs))
