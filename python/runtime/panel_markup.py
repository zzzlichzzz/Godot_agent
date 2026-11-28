"""Presentation only: these browser extractors return Markdown, not DOM-generated BBCode."""
from python.substrate.llm.api.md_to_bbcode import to_bbcode


def answer_renderer(record):
    if record and record.get('kind') != 'api' and record.get('site_id') in ('arena', 'arena_battle', 'kimi', 'qwen'):
        return to_bbcode
    return None
