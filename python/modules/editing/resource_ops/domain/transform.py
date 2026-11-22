"""Six bounded native-derived operations on a pure byte-preserving document."""
import re

from .document import Document, calls, quote, refuse, unquote

SCHEMA = {"Animation": {"length": "float", "loop_mode": "int", "step": "float"},
          "Theme": {"default_font_size": "int"}, "SpriteFrames": {}, "TileSet": {"tile_size": "Vector2i"},
          "StyleBoxFlat": {"bg_color": "Color", "border_color": "Color"}, "StyleBoxEmpty": {},
          "GradientTexture2D": {"width": "int", "height": "int", "fill_from": "Vector2", "fill_to": "Vector2"}}
PARENTS = {"GradientTexture2D": "Texture2D", "StyleBoxFlat": "StyleBox", "StyleBoxEmpty": "StyleBox"}


def dependencies(raw):
    doc = Document(raw)
    return [node["attrs"]["path"] for node in doc.nodes.values() if node["kind"] == "ext_resource"]


def resource_type(raw):
    cls = Document(raw).nodes["gd_resource"]["attrs"].get("type")
    if cls not in SCHEMA:
        refuse("Класс ресурса вне подтверждённой текстовой границы: %s" % cls)
    return cls


def expression(doc, tagged, resources):
    kind, raw = tagged["type"], tagged.get("value")
    if kind in ("Nil", "bool", "int", "float", "String"):
        return quote(raw)
    if kind == "StringName":
        return "&" + quote(raw)
    if kind == "NodePath":
        return "NodePath(" + quote(raw) + ")"
    if kind in ("Vector2", "Vector2i", "Vector3", "Vector3i", "Color"):
        return kind + "(" + ", ".join(quote(v) for v in raw) + ")"
    if kind == "ResourcePath":
        cls = resource_type(resources[raw])
        identity = next((n["attrs"]["id"] for n in doc.nodes.values()
                         if n["kind"] == "ext_resource" and n["attrs"].get("path") == raw), None)
        identity = identity or doc.add("ext_resource", PARENTS.get(cls, cls), path=raw)
        return "ExtResource(" + quote(identity) + ")"
    if kind != "NewSubresource" or tagged["class"] not in SCHEMA:
        refuse("Класс NewSubresource недоступен")
    identity = doc.add("sub_resource", tagged["class"])
    for item in tagged["properties"]:
        set_property(doc, "sub_resource:" + identity, tagged["class"], item, resources)
    return "SubResource(" + quote(identity) + ")"


def set_property(doc, key, cls, op, resources):
    name, value = op["property"], op["value"]
    if name in ("resource_path", "resource_name", "resource_scene_unique_id", "script"):
        refuse("Служебное свойство ресурса изменять нельзя", "denied")
    expected = SCHEMA[cls].get(name)
    if not expected:
        refuse("Свойство не существует или не сохраняется: %s" % name)
    if value["type"] != expected:
        refuse("Тип значения не совпадает со свойством %s" % name)
    doc.set(key, name, expression(doc, value, resources))


def target(doc, path):
    key = "resource"
    for name in path:
        refs = calls(doc.get(key, name, ""))
        if len(refs) != 1 or refs[0][1] != "SubResource":
            refuse("target должен указывать на встроенный Resource")
        key = "sub_resource:" + refs[0][2]
        if key not in doc.nodes:
            refuse()
    return key


def replace(doc, op, resources):
    pending, seen, changes = [target(doc, op["target"])], set(), []
    old_ids = {n["attrs"]["id"] for n in doc.nodes.values() if n["kind"] == "ext_resource" and n["attrs"]["path"] == op["old"]}
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        for name in doc.nodes[key]["fields"]:
            value = doc.get(key, name)
            refs = calls(value)
            if refs and value.lstrip().startswith(("[", "{")):
                refuse("Container references вне подтверждённой текстовой границы")
            for match, kind, identity in refs:
                if kind == "SubResource":
                    pending.append("sub_resource:" + identity)
                elif identity in old_ids:
                    changes.append((key, name, match.span()))
    if len(changes) != op["expected_count"]:
        refuse("Найдено ссылок %d, ожидалось %d" % (len(changes), op["expected_count"]), "conflict")
    encoded = expression(doc, {"type": "ResourcePath", "value": op["new"]}, resources)
    for key, name, (start, end) in reversed(changes):
        value = doc.get(key, name)
        doc.set(key, name, value[:start] + encoded + value[end:])


def add_track(doc, op, resources):
    fields = doc.nodes["resource"]["fields"]
    if any(name.startswith("tracks/") and doc.get("resource", name) == "NodePath(" + quote(op["path"]) + ")" for name in fields):
        refuse("Animation уже содержит такой value track", "conflict")
    indices = [int(m[1]) for name in fields if (m := re.match(r"tracks/(\d+)/", name))]
    if any("tracks/%d/type" % index not in fields or "tracks/%d/path" % index not in fields for index in indices):
        refuse("Неполная структура Animation track")
    index = max(indices, default=-1) + 1
    if any(key["time"] > float(doc.get("resource", "length", "1.0")) for key in op["keys"]):
        refuse("Ключ Animation находится после конца анимации")
    packed = lambda field: "PackedFloat32Array(" + ", ".join(quote(k[field]) for k in op["keys"]) + ")"
    keys = '{"times": ' + packed("time") + ', "transitions": ' + packed("transition") + ', "update": ' + str(["continuous", "discrete", "capture"].index(op["update_mode"])) + ', "values": [' + ", ".join(expression(doc, k["value"], resources) for k in op["keys"]) + "]}"
    values = {"type": '"value"', "imported": "false", "enabled": "true", "path": "NodePath(" + quote(op["path"]) + ")",
              "interp": str(["nearest", "linear", "cubic"].index(op["interpolation"])), "loop_wrap": "true", "keys": keys}
    for name, value in values.items():
        doc.set("resource", "tracks/%d/%s" % (index, name), value)


def add_animation(doc, op, resources):
    existing = doc.get("resource", "animations", '[{"frames": [], "loop": true, "name": &"default", "speed": 5.0}]')
    if not existing.startswith("[") or not existing.endswith("]"):
        refuse()
    names = [unquote(m[1]) for m in re.finditer(r'"name"\s*:\s*&?("(?:[^"\\]|\\.)*")', existing)]
    if op["name"] in names:
        refuse("SpriteFrames уже содержит эту анимацию", "conflict")
    if any(PARENTS.get(resource_type(resources[f["texture"]["value"]])) != "Texture2D" for f in op["frames"]):
        refuse("Кадр SpriteFrames требует Texture2D")
    frames = ", ".join('{"duration": ' + quote(f["duration"]) + ', "texture": ' + expression(doc, f["texture"], resources) + "}" for f in op["frames"])
    new = '{"frames": [' + frames + '], "loop": ' + quote(op["loop"]) + ', "name": &' + quote(op["name"]) + ', "speed": ' + quote(op["fps"]) + "}"
    doc.set("resource", "animations", existing[:-1] + (", " if existing[1:-1].strip() else "") + new + "]")


def theme(doc, op, resources):
    suffix = {"color": "colors", "constant": "constants", "font_size": "font_sizes", "font": "fonts", "icon": "icons", "stylebox": "styles"}
    name = "/".join([op["theme_type"], suffix[op["data_type"]], op["name"]])
    if not re.fullmatch(r"[A-Za-z0-9_./:-]+", name):
        refuse("Theme key вне подтверждённой текстовой границы")
    if doc.get("resource", name) is not None and not op["overwrite"]:
        refuse("Theme item уже существует", "conflict")
    value = op["value"]
    expected = {"font": "Font", "icon": "Texture2D", "stylebox": "StyleBox"}.get(op["data_type"])
    cls = value.get("class") if value["type"] == "NewSubresource" else resource_type(resources[value["value"]]) if expected else None
    if expected and PARENTS.get(cls, cls) != expected:
        refuse("Theme %s требует %s" % (op["data_type"], expected))
    doc.set("resource", name, expression(doc, value, resources))


def atlas(doc, op, resources):
    name = "sources/%d" % op["source_id"]
    if doc.get("resource", name) is not None:
        refuse("TileSet source_id уже существует", "conflict")
    raw = resources[op["texture"]["value"]]
    if PARENTS.get(resource_type(raw)) != "Texture2D":
        refuse("TileSet atlas требует Texture2D")
    texture = Document(raw)
    width, height = [int(texture.get("resource", field, "64")) for field in ("width", "height")]
    sx, sy = op["texture_region_size"]
    if any((x + 1) * sx > width or (y + 1) * sy > height for x, y in op["tiles"]):
        refuse("В atlas нет места для tile")
    encoded = expression(doc, op["texture"], resources)
    identity = doc.add("sub_resource", "TileSetAtlasSource")
    key = "sub_resource:" + identity
    doc.set(key, "texture", encoded)
    doc.set(key, "texture_region_size", "Vector2i(%d, %d)" % (sx, sy))
    for x, y in op["tiles"]:
        doc.set(key, "%d:%d/0" % (x, y), "0")
    doc.set("resource", name, "SubResource(" + quote(identity) + ")")


def transform(raw, action, resources):
    doc, cls = Document(raw), resource_type(raw)
    for op in action["operations"]:
        if op["op"] == "set_property":
            key = target(doc, op["target"])
            set_property(doc, key, cls if key == "resource" else doc.nodes[key]["attrs"]["type"], op, resources)
        elif op["op"] == "replace_reference":
            replace(doc, op, resources)
        else:
            required, function = {"animation_add_value_track": ("Animation", add_track), "sprite_frames_add_animation": ("SpriteFrames", add_animation),
                                  "theme_set_item": ("Theme", theme), "tileset_add_atlas_source": ("TileSet", atlas)}[op["op"]]
            if cls != required:
                refuse("Операция требует корневой %s" % required)
            function(doc, op, resources)
    result = doc.text.encode("utf-8")
    if result == raw:
        refuse("Операции не меняют ресурс")
    return result
