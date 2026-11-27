"""Literal has_method guards coupled to direct calls on the same local receiver."""
from .tokens import tokenize

NOTE = 'has_method(): проверка того же вызова; в probable меняется вместе с вызовом'


def pairs(tokens, name):
    """Only a simple positive guard and calls in its straight-line indented suite."""
    rows = []
    for tok in tokens:
        if tok['kind'] == 'newline': continue
        if not rows or rows[-1][0]['line'] != tok['line']: rows.append([])
        rows[-1].append(tok)
    for i, row in enumerate(rows):
        if len(row) != 8 or row[0]['value'] != 'if': continue
        receiver = row[1]['value']; literal = row[5]
        if (row[1]['kind'] != 'identifier' or literal['value'] not in ('"'+name+'"', "'"+name+"'")
                or [t['value'] for t in row[2:5]+row[6:]] != ['.', 'has_method', '(', ')', ':']): continue
        calls = []; indent = None
        for j in range(i+1, len(rows)):
            line = rows[j]; col = line[0]['column']
            if col <= row[0]['column']: break
            if indent is None: indent = col
            words = [t['value'] for t in line]
            if col != indent or ';' in words or words[-1] == ':':
                calls = []; break
            if receiver not in words: continue
            if words[:4] != [receiver, '.', name, '('] or words.count(receiver) != 1:
                calls = []; break
            calls.append(line[2]['start'])
        if calls: yield literal, calls


def selected(tokens, name, starts, excluded_lines):
    for literal, calls in pairs(tokens, name):
        hits = [start in starts for start in calls]
        if not any(hits): continue
        if not all(hits) or literal['line'] in excluded_lines:
            raise ValueError('Нельзя раздельно переименовать вызов и его проверку has_method на строке %d.' % literal['line'])
        yield literal


def plan_guards(edits, path, text, old, new, excluded):
    tokens = tokenize(text.replace('\r\n','\n').replace('\r','\n'))
    starts = {edit['start'] for edit in edits}
    for tok in selected(tokens, old, starts, {n for p,n in excluded if p == path}):
        edits.append(dict(start=tok['start']+1, end=tok['end']-1, replacement=new))
