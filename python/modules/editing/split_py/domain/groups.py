"""Native symbol grouping and target metadata; no filesystem calls."""
import re

from python.kernel.errors import AppError
from .inventory import SplitError

DEFAULT_TARGET_LINES = 900


def target_lines(value):
    if not isinstance(value, int) or isinstance(value, bool):
        raise AppError('invalid_input', 'target_lines must be an integer')
    if not 100 <= value <= 5000:
        raise AppError('invalid_input', 'target_lines must be between 100 and 5000')
    return value


def suggest_groups(inventory, stem, target_lines=DEFAULT_TARGET_LINES):
    """Черновые группы: символы по порядку, куски не длиннее target_lines."""
    if not inventory['symbols']:
        raise SplitError('в файле нет символов верхнего уровня для переноса')
    chunks, current, size = [], [], 0
    for item in inventory['symbols']:
        cost = item['lines'] + 2   # + разделительная пустая строка
        if current and size + cost > target_lines:
            chunks.append(current)
            current, size = [], 0
        current.append(item)
        size += cost
    if current:
        chunks.append(current)
    return [{'module': '%s_part%d' % (stem, index),
             'symbols': [item['name'] for item in chunk]}
            for index, chunk in enumerate(chunks, 1)]


def targets(donor, groups):
    folder = donor.rsplit('/', 1)[0] if '/' in donor else ''
    for raw in groups:
        module = str(raw.get('module') or '').strip()
        if re.match(r'^[A-Za-z_]\w*$', module):
            yield '%s/%s.py' % (folder, module) if folder else '%s.py' % module
