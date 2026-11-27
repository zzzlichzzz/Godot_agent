"""Own byte decoder and literal native inventory helpers, without IO."""
import codecs


def decode(raw):
    decoder = codecs.getincrementaldecoder('utf-8-sig')(errors='replace')
    text = decoder.decode(raw, final=True)
    return text.replace('\r\n', '\n').replace('\r', '\n')


def file_newline(raw):
    """File newline from original bytes, before universal-newline decoding."""
    if b'\r\n' in raw:
        return '\r\n'
    if b'\r' in raw:
        return '\r'
    return '\n'


def newline_of(text):
    return '\r\n' if '\r\n' in text else '\n'


def indent_width(line):
    return len(line) - len(line.lstrip(' \t'))


def code_skeleton(text):
    out = []
    i, size = 0, len(text)
    while i < size:
        ch = text[i]
        if ch == '#':
            while i < size and text[i] != '\n':
                i += 1
            out.append('\n')
            continue
        if ch in ('"', "'"):
            quote = ch
            triple = text[i:i + 3] == ch * 3
            marker = ch * (3 if triple else 1)
            i += len(marker)
            while i < size:
                if text[i] == '\\':
                    i += min(2, size - i)
                    continue
                if text.startswith(marker, i):
                    i += len(marker)
                    break
                if not triple and text[i] == '\n':
                    break
                i += 1
            out.append(' ')
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def balance(text):
    value = 0
    for ch in code_skeleton(text):
        if ch in '([{':
            value += 1
        elif ch in ')]}':
            value -= 1
    return value


def leading_comment_start(lines, index):
    start = index
    while start > 0:
        value = lines[start - 1].strip()
        if value.startswith('#') or value.startswith('@'):
            start -= 1
            continue
        break
    return start
