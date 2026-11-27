"""Literal gd_api_check masking: preserve character positions and LF."""


def mask(text, mask_strings, mask_comments):
    out = list(text)
    i, n = 0, len(text)
    in_str = None
    triple = None
    while i < n:
        c = text[i]
        if triple:
            if mask_strings and c != "\n":
                out[i] = " "
            if c == "\\" and i + 1 < n:
                if mask_strings and text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if text.startswith(triple * 3, i):
                if mask_strings:
                    out[i] = out[i + 1] = out[i + 2] = " "
                triple = None
                i += 3
                continue
            i += 1
            continue
        if in_str:
            if mask_strings and c != "\n":
                out[i] = " "
            if c == "\\" and i + 1 < n:
                if mask_strings and text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "#":
            j = text.find("\n", i)
            end = n if j < 0 else j
            if mask_comments:
                for k in range(i, end):
                    out[k] = " "
            i = end
            continue
        if c == '"' or c == "'":
            if text.startswith(c * 3, i):
                triple = c
                if mask_strings:
                    out[i] = out[i + 1] = out[i + 2] = " "
                i += 3
                continue
            in_str = c
            if mask_strings:
                out[i] = " "
            i += 1
            continue
        i += 1
    return "".join(out)
