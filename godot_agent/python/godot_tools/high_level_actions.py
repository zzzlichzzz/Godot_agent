# -*- coding: utf-8 -*-
"""Compile typed high-level commands into existing validated primitives."""
import copy

import project_settings_actions
import scene_actions


class HighLevelActionError(ValueError):
    pass


def _exact_fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise HighLevelActionError("project_command должен быть JSON-объектом")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise HighLevelActionError("Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise HighLevelActionError("Неизвестные поля: %s" % ", ".join(sorted(unknown)))


def _text(value, field, limit=500):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise HighLevelActionError(
            "%s должен быть непустой строкой до %d символов" % (field, limit))
    return value


def _summary(action):
    value = action.get("summary")
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 500:
        raise HighLevelActionError("summary должен быть строкой до 500 символов")
    return value.strip() or None


def _component_path(parent, name):
    return name if parent == "." else parent + "/" + name


def _compile_scene_component(command, summary):
    _exact_fields(command, ("type", "scene", "parent", "name", "node_type"),
                  ("script", "properties", "signals"))
    parent = scene_actions.normalize_node_path(command["parent"], "parent")
    name = _text(command["name"], "name", 120)
    node_type = _text(command["node_type"], "node_type", 120)
    component = _component_path(parent, name)
    operations = [{"op": "add_node", "parent": parent, "name": name, "type": node_type}]
    script = command.get("script")
    if script is not None:
        operations.append({"op": "attach_script", "node": component,
                           "script": _text(script, "script", 500),
                           "replace_existing": False})
    properties = command.get("properties", [])
    if not isinstance(properties, list) or len(properties) > 12:
        raise HighLevelActionError("properties должен содержать не более 12 элементов")
    for item in properties:
        _exact_fields(item, ("name", "value"))
        operations.append({"op": "set_node_property", "node": component,
                           "property": _text(item["name"], "property.name", 160),
                           "value": scene_actions.normalize_variant(item["value"])})
    signals = command.get("signals", [])
    if not isinstance(signals, list) or len(signals) > 8:
        raise HighLevelActionError("signals должен содержать не более 8 элементов")
    for item in signals:
        _exact_fields(item, ("signal", "target", "method"))
        operations.append({"op": "connect_signal", "source": component,
                           "signal": _text(item["signal"], "signal", 160),
                           "target": scene_actions.normalize_node_path(item["target"], "target"),
                           "method": _text(item["method"], "method", 160)})
    result = {"action": "edit_scene", "scene": _text(command["scene"], "scene", 500),
              "operations": operations}
    if summary:
        result["summary"] = summary
    return result


def _compile_input_action(command, summary):
    _exact_fields(command, ("type", "name"), ("deadzone", "events"))
    name = _text(command["name"], "name", 120)
    operation = {"op": "add_input_action", "name": name}
    if "deadzone" in command:
        operation["deadzone"] = command["deadzone"]
    operations = [operation]
    events = command.get("events", [])
    if not isinstance(events, list) or len(events) > 8:
        raise HighLevelActionError("events должен содержать не более 8 элементов")
    for event in events:
        operations.append({"op": "add_input_event", "action": name,
                           "event": copy.deepcopy(event)})
    result = {"action": "edit_project_settings", "operations": operations}
    if summary:
        result["summary"] = summary
    return result


def _compile_autoload(command, summary):
    _exact_fields(command, ("type", "name", "path"))
    result = {"action": "edit_project_settings", "operations": [{
        "op": "add_autoload", "name": _text(command["name"], "name", 120),
        "path": _text(command["path"], "path", 500)}]}
    if summary:
        result["summary"] = summary
    return result


def _compile_rename(command, _summary):
    _exact_fields(command, ("type", "kind", "declaration", "old_name", "new_name"))
    return {"action": "rename_symbol", "kind": _text(command["kind"], "kind", 40),
            "declaration": _text(command["declaration"], "declaration", 600),
            "old_name": _text(command["old_name"], "old_name", 160),
            "new_name": _text(command["new_name"], "new_name", 160)}


def _compile_atomic_files(command, summary):
    _exact_fields(command, ("type", "operations"), ("checks",))
    operations = command["operations"]
    checks = command.get("checks", [])
    if not isinstance(operations, list) or not 1 <= len(operations) <= 30:
        raise HighLevelActionError("operations должен содержать от 1 до 30 элементов")
    if not isinstance(checks, list) or len(checks) > 32:
        raise HighLevelActionError("checks должен содержать не более 32 элементов")
    result = {"action": "transaction", "operations": copy.deepcopy(operations)}
    if checks:
        result["checks"] = copy.deepcopy(checks)
    if summary:
        result["summary"] = summary
    return result


_COMPILERS = {
    "create_scene_component": _compile_scene_component,
    "create_input_action": _compile_input_action,
    "register_autoload": _compile_autoload,
    "rename_symbol": _compile_rename,
    "atomic_files": _compile_atomic_files,
}


def compile_action(project_root, action, allow_addons=False,
                    allow_self_edit=False, addon_dir=None):
    """Return one normalized primitive action without modifying the project."""
    _exact_fields(action, ("action", "command"), ("summary",))
    if action.get("action") != "project_command":
        raise HighLevelActionError("Ожидалось action=project_command")
    command = action["command"]
    if not isinstance(command, dict):
        raise HighLevelActionError("command должен быть JSON-объектом")
    kind = command.get("type")
    compiler = _COMPILERS.get(kind)
    if compiler is None:
        raise HighLevelActionError("Неизвестная высокоуровневая команда: %s" % kind)
    try:
        compiled = compiler(command, _summary(action))
        if compiled["action"] == "edit_scene":
            compiled, _absolute = scene_actions.normalize_action(
                project_root, compiled, allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
        elif compiled["action"] == "edit_project_settings":
            compiled, _absolute = project_settings_actions.normalize_action(
                project_root, compiled, allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    except HighLevelActionError:
        raise
    except Exception as exc:
        raise HighLevelActionError(str(exc)) from exc
    return compiled
