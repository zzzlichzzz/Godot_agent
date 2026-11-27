"""Ordered, bounded native reference scan over supplied bytes, without IO."""
import re

from .text import decode

SCAN_SKIP_DIRS = {'__pycache__', '.git', '.godot', '.import', '.agent_history',
                  'dist', 'build', 'minilich_brain', 'parser_corpus', 'agent_api_cache',
                  'node_modules', '.venv', '_tmp'}
SCAN_EXTS = {'.gd', '.tscn', '.tres', '.godot', '.md', '.json', '.py', '.cfg', '.txt', '.bat', '.cmd'}
MAX_SCAN_FILE_BYTES = 1024 * 1024
MAX_OCCURRENCES = 1000
READ_MARKERS = ('open(', 'read_text', 'read_bytes', 'read_string',
                'check-only', '--script', 'source_code', 'get_script')


def eligible(rel):
    parts = rel.split('/')
    if any(part in SCAN_SKIP_DIRS or part.startswith('.') for part in parts[:-1]):
        return False
    return '.' in parts[-1] and '.' + parts[-1].rsplit('.', 1)[1].lower() in SCAN_EXTS


def scan(donor, public_names, files):
    file_name = donor.rsplit('/', 1)[-1]
    stem = file_name.rsplit('.', 1)[0]
    names = '|'.join(re.escape(name) for name in public_names)
    call_re = re.compile(r'(?:\.\s*(?:%s)\s*\(|"(?:%s)")' % (names, names)) if names else None
    occurrences = []
    counts = {'path': 0, 'source_read': 0, 'call': 0, 'doc': 0, 'mention': 0}
    files_by_kind = {'source_read': set(), 'call': set(), 'doc': set(), 'path': set()}
    truncated = False
    for rel, raw in files:
        if rel == donor:
            continue
        if not eligible(rel) or len(raw) > MAX_SCAN_FILE_BYTES:
            continue
        ext = '.' + rel.rsplit('.', 1)[1].lower()
        text = decode(raw)
        if file_name not in text and stem not in text and call_re is None:
            continue
        if file_name not in text and stem not in text and call_re is not None and not call_re.search(text):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            has_name = file_name in line or stem in line
            relevant = has_name or (call_re is not None and bool(call_re.search(line)))
            if not relevant:
                continue
            if ext == '.md':
                kind = 'doc'
            elif file_name in line and any(marker in line for marker in READ_MARKERS):
                kind = 'source_read'
            elif call_re is not None and call_re.search(line):
                kind = 'call'
            elif has_name:
                kind = 'path'
            else:
                kind = 'mention'
            counts[kind] += 1
            files_by_kind.setdefault(kind, set()).add(rel)
            if len(occurrences) < MAX_OCCURRENCES:
                occurrences.append({'file': rel, 'line': number, 'kind': kind, 'text': line.strip()[:160]})
            else:
                truncated = True
    all_files = set().union(*files_by_kind.values()) if files_by_kind else set()
    hard_files = sorted(files_by_kind.get('source_read') or ())
    return {'counts': counts, 'occurrences': occurrences, 'truncated': truncated,
            'hard_files': hard_files, 'soft_files': sorted(all_files - set(hard_files))}
