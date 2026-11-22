"""Native all-block local-name superset, including lambda parameters."""
ENGINE_VIRTUALS = {
    '_init', '_ready', '_enter_tree', '_exit_tree', '_process', '_physics_process',
    '_input', '_unhandled_input', '_unhandled_key_input', '_shortcut_input',
    '_gui_input', '_notification', '_to_string', '_get_property_list',
    '_get_configuration_warnings',
}


def collect_locals(tokens):
    found = set()
    index, size = 0, len(tokens)
    while index < size:
        token = tokens[index]
        if token['kind'] == 'identifier':
            value = token['value']
            if value in ('var', 'const') and index + 1 < size and tokens[index + 1]['kind'] == 'identifier':
                found.add(tokens[index + 1]['value'])
                index += 2
                continue
            if value == 'for':
                cursor = index + 1
                while cursor < size and tokens[cursor]['kind'] != 'identifier':
                    cursor += 1
                if cursor < size:
                    found.add(tokens[cursor]['value'])
                index = cursor + 1
                continue
            if value == 'func':
                cursor = index + 1
                if cursor < size and tokens[cursor]['kind'] == 'identifier':
                    found.add(tokens[cursor]['value'])
                    cursor += 1
                if cursor < size and tokens[cursor]['value'] == '(':
                    depth = 0
                    while cursor < size:
                        item = tokens[cursor]
                        if item['value'] == '(':
                            depth += 1
                        elif item['value'] == ')':
                            depth -= 1
                            if depth == 0:
                                break
                        elif depth == 1 and item['kind'] == 'identifier':
                            prev = tokens[cursor - 1] if cursor else None
                            if prev and prev['value'] in ('(', ','):
                                found.add(item['value'])
                        cursor += 1
                index = cursor + 1
                continue
        index += 1
    return found
