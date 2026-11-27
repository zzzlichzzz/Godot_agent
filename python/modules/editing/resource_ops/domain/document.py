"""A pure UTF-8 resource document; token-aware value spans, never evaluation."""
import re

from python.kernel.errors import AppError
from python.kernel.write_plan import canonical_json as quote

EOL = re.compile(r"\r\n|\r|\n")
HEADER = re.compile(r'\[(gd_resource|ext_resource|sub_resource|resource)\b(.*?)\][ \t]*$')
ATTR = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\d+)')
FIELD = re.compile(r'([A-Za-z0-9_./:-]+)[ \t]*=[ \t]*')
CALL = re.compile(r'(?P<kind>ExtResource|SubResource)\(\s*(?P<id>"(?:[^"\\]|\\.)*")\s*\)|"(?:[^"\\]|\\.)*"|;[^\r\n]*')
TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|;[^\r\n]*|\r\n|[\r\n]|[()\[\]{}]|[^";()\[\]{}\r\n]+|.', re.DOTALL)


def refuse(message="Неоднозначная или неподдерживаемая структура .tres", kind="invalid_input"):
    raise AppError(kind, message)


def calls(value):
    return [(m, m["kind"], unquote(m["id"])) for m in CALL.finditer(value) if m["kind"]]


def unquote(value):
    if not re.fullmatch(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"', value):
        refuse("Неподдерживаемый строковый литерал ресурса")
    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    return re.sub(r'\\(u[0-9a-fA-F]{4}|.)', lambda m: chr(int(m[1][1:], 16)) if m[1].startswith("u") else escapes[m[1]], value[1:-1])


def value_end(text, start):
    stack, last = [], start
    for token in TOKEN.finditer(text, start):
        value = token.group()
        if value == '"':
            refuse()
        if value.startswith(";"):
            if not stack:
                end = EOL.search(text, token.end())
                return last, end.end() if end else len(text)
            continue
        if value in ("(", "[", "{"):
            stack.append(value)
        elif value in (")", "]", "}"):
            if not stack or stack.pop() != dict(zip(")]}", "([{"))[value]:
                refuse()
        elif EOL.fullmatch(value) and not stack:
            return last, token.end()
        if value.strip():
            last = token.start() + len(value.rstrip())
    if stack or last == start:
        refuse()
    return last, len(text)


class Document:
    def __init__(self, raw):
        if raw.startswith(b"\xef\xbb\xbf"):
            raise AppError("invalid_input", "ResourceLoader не смог загрузить ресурс",
                           details={"native_code": "load_failed", "native_diagnostic": "Parse Error: Expected '['."})
        try:
            self.text = raw.decode("utf-8")
        except UnicodeError:
            refuse("Ресурс должен быть корректным UTF-8")
        if any(m[0].startswith(";") and self.text[m.end():m.end()+1] == "\r" and self.text[m.end():m.end()+2] != "\r\n" for m in TOKEN.finditer(self.text)):
            refuse()
        endings = EOL.findall(self.text)
        self.eol = max(dict.fromkeys(endings), key=endings.count) if endings else "\n"
        self.scan()

    def scan(self):
        self.nodes, pos, current = {}, 0, None
        while pos < len(self.text):
            end = EOL.search(self.text, pos)
            stop = end.end() if end else len(self.text)
            line = self.text[pos:end.start() if end else stop]
            header = HEADER.fullmatch(line)
            if header:
                if current:
                    current["end"] = pos
                kind, rest = header.groups()
                pairs = ATTR.findall(rest)
                if ATTR.sub("", rest).strip() or len({k for k, _ in pairs}) != len(pairs):
                    refuse()
                attrs = {key: unquote(value) if value.startswith('"') else int(value) for key, value in pairs}
                key = kind if kind in ("gd_resource", "resource") else kind + ":" + str(attrs.get("id", ""))
                if key in self.nodes or kind != "gd_resource" and not self.nodes:
                    refuse()
                current = {"kind": kind, "attrs": attrs, "start": pos, "head_end": stop, "fields": {}}
                self.nodes[key] = current
            elif line.strip() and not line.lstrip().startswith(";"):
                field = FIELD.match(line)
                if not current or not field or current["kind"] not in ("resource", "sub_resource"):
                    refuse()
                name, start = field[1], pos + field.end()
                finish, stop = value_end(self.text, start)
                if name in current["fields"] or finish == start:
                    refuse()
                current["fields"][name] = (start, finish, stop)
            pos = stop
        if current:
            current["end"] = len(self.text)
        if "gd_resource" not in self.nodes or "resource" not in self.nodes or current["kind"] != "resource":
            refuse()
        if self.nodes["gd_resource"]["attrs"].get("format") != 3:
            refuse("Поддерживается только текстовый resource format=3")

    def get(self, key, name, default=None):
        field = self.nodes[key]["fields"].get(name)
        return self.text[field[0]:field[1]] if field else default

    def set(self, key, name, value):
        node = self.nodes[key]
        field = node["fields"].get(name)
        if field:
            start, end, stop = field
            local = EOL.search(self.text, start, stop)
            old = self.text[start:end]
            common = next((i for i, (a, b) in enumerate(zip(old, value)) if a != b), min(len(old), len(value)))
            tail = next((i for i, (a, b) in enumerate(zip(old[common:][::-1], value[common:][::-1])) if a != b), min(len(old) - common, len(value) - common))
            value = value[:common] + EOL.sub(lambda _: local.group() if local else self.eol, value[common:len(value) - tail]) + (value[-tail:] if tail else "")
        else:
            start = end = node["end"]
            prefix = "" if self.text[:start].endswith(("\n", "\r")) else self.eol
            suffix = self.eol if start < len(self.text) or self.text.endswith(("\n", "\r")) else ""
            value = prefix + name + " = " + value + suffix
        self.text = self.text[:start] + value + self.text[end:]
        self.scan()

    def add(self, kind, cls, **attrs):
        used = {n["attrs"].get("id") for n in self.nodes.values()}
        index = 1
        while "agent_%d" % index in used:
            index += 1
        identity = "agent_%d" % index
        fields = dict(type=cls, **attrs, id=identity)
        header = "[" + kind + " " + " ".join(k + "=" + quote(v) for k, v in fields.items()) + "]"
        start = self.nodes["resource"]["start"]
        self.text = self.text[:start] + header + self.eol * 2 + self.text[start:]
        self.scan()
        if "load_steps" in self.nodes["gd_resource"]["attrs"]:
            header_end = self.nodes["gd_resource"]["head_end"]
            self.text = re.sub(r"\bload_steps=\d+", "load_steps=%d" % (len(self.nodes) - 1), self.text[:header_end]) + self.text[header_end:]
            self.scan()
        return identity
