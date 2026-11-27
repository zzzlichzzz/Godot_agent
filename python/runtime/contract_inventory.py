"""Shipped public names survive a removed feature folder or a failed import."""
import json

from .module_loader import ROOT


def owners():
    inventory = {}
    for path in sorted((ROOT / 'contract' / 'capabilities').glob('*.json')):
        if path.name != '_template.json':
            item = json.loads(path.read_bytes())
            inventory[item['tool_name']] = item['module_id']
    return inventory
