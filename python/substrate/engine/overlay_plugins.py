"""Keep project-owned editor plugins out of the temporary editor and in the final settings."""
import re
from dataclasses import dataclass
from python.kernel.errors import AppError


_SECTION = re.compile(rb'(?m)^[ \t]*\[([^]\r\n]+)\][ \t]*(?:;[^\r\n]*)?\r?$')
_ENABLED = re.compile(rb'enabled[ \t]*=[ \t]*PackedStringArray\((.*?)\)[ \t]*(?:;.*)?')
_PATH = rb'"res://addons/[^"\\:\x00-\x1f]+/plugin\.cfg"'
_PATHS = re.compile(rb'\s*(?:' + _PATH + rb'(?:\s*,\s*' + _PATH + rb')*)?\s*')


@dataclass(frozen=True)
class OverlaySettings:
    project: bytes
    plugins: bytes = b''
    next_section: bytes = b''

    @classmethod
    def capture(cls, raw):
        section = None
        for header in _SECTION.finditer(raw):
            if header[1] != b'editor_plugins': continue
            if section is not None: raise AppError('denied', 'Повторная секция editor_plugins в project.godot.')
            following = _SECTION.search(raw, header.end())
            end = following.start() if following else len(raw)
            block = raw[header.start():end]
            enabled = False
            for line in raw[header.end():end].splitlines():
                line = line.strip()
                if not line or line.startswith(b';'): continue
                value = _ENABLED.fullmatch(line)
                if (enabled or not value or not _PATHS.fullmatch(value[1]) or
                        any(p in (b'', b'.', b'..') for path in re.findall(_PATH, value[1])
                            for p in path[len(b'"res://addons/'):-len(b'/plugin.cfg"')].split(b'/'))):
                    raise AppError('denied', 'Неподдерживаемое объявление editor_plugins в project.godot.')
                enabled = True
            section = cls(raw[:header.start()] + raw[end:], block, following[1] if following else b'')
        return section or cls(raw)

    def restore(self, output):
        if not self.plugins: return output
        headers = list(_SECTION.finditer(output))
        if any(h[1] == b'editor_plugins' for h in headers):
            raise AppError('conflict', 'Непредвиденное изменение editor_plugins во временном проекте.')
        pos = next((h.start() for h in headers if h[1] == self.next_section), len(output))
        before, after = output[:pos], output[pos:]
        return (before + (b'\n' if before and not before.endswith(b'\n') else b'') + self.plugins +
                (b'\n' if after and not self.plugins.endswith(b'\n') else b'') + after)
