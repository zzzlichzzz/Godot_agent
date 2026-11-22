"""Local utf-8-sig replacement decoder, including native partial-BOM behavior."""
import codecs


def decode(raw):
    decoder = codecs.getincrementaldecoder('utf-8-sig')(errors='replace')
    return decoder.decode(raw, final=True)
