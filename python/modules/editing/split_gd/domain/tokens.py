"""Native lexical offsets: comments skipped, strings whole, not a parser."""
KEYWORDS = {
    'and', 'as', 'assert', 'await', 'break', 'breakpoint', 'class', 'class_name',
    'const', 'continue', 'elif', 'else', 'enum', 'extends', 'for', 'func', 'if',
    'in', 'is', 'match', 'namespace', 'not', 'null', 'or', 'pass', 'preload',
    'return', 'self', 'signal', 'static', 'super', 'trait', 'true', 'false',
    'var', 'void', 'while', 'yield', 'PI', 'TAU', 'INF', 'NAN',
}
TWO_CHAR = ('->', '==', '!=', '<=', '>=', ':=', '&&', '||', '+=', '-=',
            '*=', '/=', '%=', '**', '<<', '>>', '..')


def tokenize(text):
    tokens = []
    index, line, size = 0, 1, len(text)
    while index < size:
        char = text[index]
        if char in ' \t\r':
            index += 1
            continue
        if char == '\n':
            tokens.append({'kind': 'newline', 'value': '\n', 'start': index,
                           'end': index + 1, 'line': line})
            index += 1
            line += 1
            continue
        if char == '#':
            end = text.find('\n', index)
            index = size if end < 0 else end
            continue
        if char in '"\'':
            width = 3 if text.startswith(char * 3, index) else 1
            start, start_line = index, line
            index += width
            closed = False
            while index < size:
                if text[index] == '\\':
                    index += min(2, size - index)
                    continue
                if text.startswith(char * width, index):
                    index += width
                    closed = True
                    break
                if text[index] == '\n':
                    if width == 1:
                        break
                    line += 1
                index += 1
            tokens.append({'kind': 'string', 'value': text[start:index],
                           'start': start, 'end': index, 'line': start_line, 'closed': closed})
            continue
        if char.isdigit():
            start, start_line = index, line
            while index < size and (text[index].isalnum() or text[index] in '._'):
                index += 1
            tokens.append({'kind': 'number', 'value': text[start:index],
                           'start': start, 'end': index, 'line': start_line})
            continue
        if char == '_' or (char.isascii() and char.isalpha()):
            start, start_line = index, line
            index += 1
            while index < size and (text[index] == '_' or text[index].isalnum() and text[index].isascii()):
                index += 1
            tokens.append({'kind': 'identifier', 'value': text[start:index],
                           'start': start, 'end': index, 'line': start_line})
            continue
        start = index
        value = text[index:index + 2] if text[index:index + 2] in TWO_CHAR else char
        index += len(value)
        tokens.append({'kind': 'symbol', 'value': value, 'start': start, 'end': index, 'line': line})
    return tokens


def prev_token(tokens, index):
    index -= 1
    while index >= 0 and tokens[index]['kind'] == 'newline':
        index -= 1
    return tokens[index] if index >= 0 else None
