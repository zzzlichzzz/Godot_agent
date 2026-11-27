"""Literal top-level native inventory; no tokenizer, planning or engine tables."""
import re

from .text import balance, indent_width, leading_comment_start

FUNC_RE = re.compile(r'^(?:static\s+)?func\s+([A-Za-z_]\w*)\s*\(')


def parse_params(sig_text):
    start = sig_text.find('(')
    if start < 0:
        return []
    depth, close = 0, -1
    for i in range(start, len(sig_text)):
        ch = sig_text[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
            if depth == 0:
                close = i
                break
    if close < 0:
        close = len(sig_text)
    inner = sig_text[start + 1:close]
    pieces, chunk, depth = [], [], 0
    for ch in inner:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            pieces.append(''.join(chunk).strip())
            chunk = []
        else:
            chunk.append(ch)
    if chunk:
        pieces.append(''.join(chunk).strip())
    out = []
    for piece in pieces:
        if not piece:
            continue
        eq, depth = -1, 0
        for i, ch in enumerate(piece):
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
            elif ch == '=' and depth == 0:
                eq = i
                break
        head = piece if eq < 0 else piece[:eq]
        match = re.match(r'\s*([A-Za-z_]\w*)', head)
        if match:
            out.append({'name': match.group(1),
                        'default': None if eq < 0 else piece[eq + 1:].strip()})
    return out


def file_inventory(text):
    lines = str(text or '').splitlines()
    inv = {'extends': '', 'class_name': '', 'header_end': 0,
           'consts': [], 'vars': [], 'funcs': [], 'errors': [], 'lines': len(lines)}
    index, size = 0, len(lines)
    while index < size:
        line = lines[index]
        stripped = line.strip()
        if indent_width(line) or not stripped:
            index += 1
            continue
        if stripped.startswith('extends '):
            match = re.match(r'extends\s+([\w.]+)', stripped)
            if match:
                inv['extends'] = match.group(1)
            inv['header_end'] = index + 1
            index += 1
            continue
        if stripped.startswith('class_name '):
            inv['class_name'] = stripped.split()[1]
            inv['header_end'] = index + 1
            index += 1
            continue
        if stripped in ('@tool', '@static_unload') or stripped.startswith('@icon'):
            inv['header_end'] = max(inv['header_end'], index + 1)
            index += 1
            continue
        if stripped.startswith('const '):
            end, block = index + 1, [line]
            while balance('\n'.join(block)) > 0 and end < size:
                block.append(lines[end])
                end += 1
            match = re.match(r'const\s+([A-Za-z_]\w*)', stripped)
            block_start = leading_comment_start(lines, index)
            inv['consts'].append({'name': match.group(1) if match else '', 'start': index + 1, 'end': end,
                                  'block_start': block_start + 1,
                                  'text': '\n'.join(lines[block_start:end])})
            index = end
            continue
        plain = re.sub(r'^(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s*)+', '', stripped)
        if plain.startswith('var ') or plain.startswith('signal '):
            match = re.match(r'(?:var|signal)\s+([A-Za-z_]\w*)', plain)
            if match:
                inv['vars'].append({'name': match.group(1), 'line': index + 1})
            index += 1
            continue
        match = FUNC_RE.match(stripped)
        if not match:
            index += 1
            continue
        name = match.group(1)
        sig_end, sig_lines = index + 1, [line]
        while not (sig_lines[-1].rstrip().endswith(':') and balance('\n'.join(sig_lines)) == 0):
            if sig_end >= size:
                inv['errors'].append('line %d: сигнатура %s не закрыта' % (index + 1, name))
                break
            sig_lines.append(lines[sig_end])
            sig_end += 1
        body_start = sig_end
        while body_start < size and not lines[body_start].strip():
            body_start += 1
        cursor, end = body_start, body_start
        while cursor < size:
            if lines[cursor].strip() and indent_width(lines[cursor]) == 0:
                break
            if lines[cursor].strip():
                end = cursor + 1
            cursor += 1
        sig_text = ' '.join(value.strip() for value in sig_lines)
        ret_match = re.search(r'->\s*([^:]+):\s*$', sig_text)
        ret = ret_match.group(1).strip() if ret_match else ''
        block_start = leading_comment_start(lines, index)
        inv['funcs'].append({
            'name': name, 'sig_start': index + 1, 'start': index + 1,
            'block_start': block_start + 1, 'body_start': body_start + 1, 'end': end,
            'sig_lines': sig_lines, 'sig_text': sig_text, 'params': parse_params(sig_text),
            'ret': ret, 'has_await': bool(re.search(r'\bawait\b', '\n'.join(lines[body_start:end]))),
            'anns': [value.strip() for value in lines[block_start:index]
                     if value.strip().startswith('@')],
        })
        index = end
    return inv
