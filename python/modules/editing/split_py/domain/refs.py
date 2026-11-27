"""Read-only native branch priority, all-hit counts and bounded report retention."""
import re

from .text import decode
from .walk import extension, imports, module_matches

MAX_SCAN_FILE_BYTES = 1024*1024
MAX_OCCURRENCES = 1000


def scan(donor, stem, base, files):
    name_re = re.compile(r'(?<![\w-])'+re.escape(base)+r'(?![\w])')
    patch_re = re.compile(r'(?<![\w.])'+re.escape(stem)+r'\s*(?:\.\s*\w+\s*(?:[+\-*/%@|&^]?=)(?!=)'
                          r'|\.\s*__setattr__\s*\()')
    setattr_re = re.compile(r'(?<![\w.])setattr\(\s*'+re.escape(stem)+r'\s*,')
    counts = {'import':0,'source_read':0,'patch':0,'mention':0,'doc':0}
    occurrences = []
    truncated = False
    for rel, raw in files:
        if rel == donor or len(raw) > MAX_SCAN_FILE_BYTES:
            continue
        ext = extension(rel)
        for number, line in enumerate(decode(raw).splitlines(),1):
            modules, _aliases = imports(line)
            if any(module_matches(m,stem) for m in modules):
                kind = 'import'
            elif patch_re.search(line) or setattr_re.search(line):
                kind = 'patch'
            elif name_re.search(line) or donor in line:
                if ext == '.py' and ('open(' in line or '__file__' in line or 'read_text(' in line):
                    kind = 'source_read'
                elif ext == '.md':
                    kind = 'doc'
                else:
                    kind = 'mention'
            else:
                continue
            counts[kind] += 1
            if len(occurrences) < MAX_OCCURRENCES:
                occurrences.append({'rel':rel,'line':number,'kind':kind,'text':line.strip()[:200]})
            else:
                truncated = True
    return {'counts':counts,'occurrences':occurrences,'truncated':truncated}
