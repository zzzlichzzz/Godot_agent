"""Native scan eligibility and lexical import parsing, without filesystem I/O."""
import re

SKIP_DIRS = {'__pycache__','.git','.godot','.import','.agent_history','dist','build',
             'minilich_brain','parser_corpus','agent_api_cache','node_modules','.venv','_tmp'}
SCAN_EXTS = {'.py','.gd','.md','.json','.cmd','.bat','.txt','.cfg','.godot','.tscn','.tres','.gdshader'}
IMPORT_RE = re.compile(r'^\s*(?:import|from)\s+')


def extension(rel):
    base = rel.rsplit('/',1)[-1]
    return '.'+base.rsplit('.',1)[1].lower() if '.' in base.lstrip('.') else ''


def stem(base):
    return base.rsplit('.',1)[0] if '.' in base.lstrip('.') else base


def eligible(rel):
    parts = rel.split('/')
    return (not any(p in SKIP_DIRS or p.startswith('.') for p in parts[:-1])
            and extension(rel) in SCAN_EXTS)


def imports(line):
    if not IMPORT_RE.match(line):
        return [], []
    stripped = line.strip()
    if stripped.startswith('from '):
        target = stripped[5:].split(' import',1)[0].strip().strip('()').strip()
        return [target.lstrip('.')], []
    modules, aliases = [], []
    for part in stripped[len('import '):].split(','):
        pieces = part.strip().split(' as ')
        if pieces and pieces[0].strip():
            modules.append(pieces[0].strip().lstrip('.'))
        if len(pieces)==2 and pieces[1].strip():
            aliases.append(pieces[1].strip())
    return modules, aliases


def module_matches(candidate, name):
    return candidate == name or candidate.endswith('.'+name)
