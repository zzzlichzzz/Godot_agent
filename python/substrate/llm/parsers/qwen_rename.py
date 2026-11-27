"""Qwen sometimes labels its terminal rename proposal `json` instead of `agent_action`."""
import json
import re


_BLOCK = re.compile(r'^```json[ \t]*\r?\n(.*?)^```[ \t]*(?:\r?\n\s*===DONE===)?\s*\Z', re.M | re.S)


def rename_block(text):
    if text.count('```') != 2:
        return None
    match = _BLOCK.search(text)
    if not match:
        return None
    try:
        action = json.loads(match[1])
    except (ValueError, RecursionError):
        return None
    if not isinstance(action, dict) or action.get('action') != 'rename_symbol':
        return None
    return text[:match.start()].rstrip(), action, text[:match.start()] + text[match.start():].replace('```json','```agent_action',1)
