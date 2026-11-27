"""Native character slice after decoding; no filesystem or transport clipping."""


def _line_offset(text, index):
    pos = 0
    for _ in range(index):
        newline = text.find("\n", pos)
        if newline < 0:
            return len(text)
        pos = newline + 1
    return pos


def render(path, text, max_chars, *, start_line=None, end_line=None, offset=None):
    low = max(_line_offset(text, (start_line or 1) - 1), offset or 0)
    high = _line_offset(text, end_line) if end_line is not None else len(text)
    end = min(low + max_chars, high)
    content = text[low:end]
    result = {"path": path, "content": content, "truncated": end < high, "chars": len(content)}
    if start_line is not None or end_line is not None or offset is not None:
        result["next_offset"] = end if end < high else None
    return result
