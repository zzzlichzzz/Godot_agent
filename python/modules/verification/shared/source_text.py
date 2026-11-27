"""ADR-0008 main-file decode; candidate/instance readers retain their contracts."""
import codecs


def decode_source(raw):
    """Match legacy streamed UTF-8-sig decoding, preserving CRLF and raw bytes.

    One initial BOM only. Incremental decoder also preserves the legacy empty
    result for a terminal incomplete BOM prefix; ordinary bad UTF-8 is replaced.
    """
    decoder = codecs.getincrementaldecoder('utf-8-sig')(errors='replace')
    return decoder.decode(raw, final=True)
