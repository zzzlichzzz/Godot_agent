"""Native character slice after decoding; no filesystem or transport clipping."""


def render(path, text, max_chars):
    content = text[:max_chars]
    return {"path": path, "content": content, "truncated": len(text) > max_chars,
            "chars": len(content)}
