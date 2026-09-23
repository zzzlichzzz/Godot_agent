@tool
extends RefCounted
# Экспорт РЕАЛЬНОГО API текущей версии Godot через ClassDB.
# Сервер использует это, чтобы проверять код модели против фактических
# методов/свойств/сигналов движка, а не по памяти обучения нейросети.
#
# no_inheritance = true у всех трёх ClassDB-запросов: берём у каждого класса
# только его СОБСТВЕННЫЕ члены — цепочку наследования достраивает Python
# (gd_api_cache.py) на основе поля "inherits". Так JSON выходит компактным.
#
# Помимо арности ("methods": имя -> [min, max]) экспортируем ПОЛНЫЕ сигнатуры
# ("signatures": имя -> "name(arg: Type = default) -> Ret") — одной готовой
# строкой на метод: так кэш не распухает структурой, а потребители (мост,
# справки) печатают её как есть. Внешней модели одной арности мало: без имён
# и дефолтов параметров она выдумывает их из памяти.

static func _type_name(d: Dictionary, nil_label: String) -> String:
	var t: int = int(d.get("type", TYPE_NIL))
	if t == TYPE_NIL:
		# PROPERTY_USAGE_NIL_IS_VARIANT отличает «настоящий Variant»
		# (аргументы, возвраты-значения) от void у возвращаемого типа.
		if (int(d.get("usage", 0)) & PROPERTY_USAGE_NIL_IS_VARIANT) != 0:
			return "Variant"
		return nil_label
	var cn := String(d.get("class_name", ""))
	if t == TYPE_OBJECT and cn != "":
		return cn
	return type_string(t)


static func _method_signature(m: Dictionary) -> String:
	var margs: Array = m.get("args", [])
	var defaults: Array = m.get("default_args", [])
	var first_default: int = margs.size() - defaults.size()
	var parts: Array = []
	for i in margs.size():
		var a: Dictionary = margs[i] if margs[i] is Dictionary else {}
		var piece := String(a.get("name", "arg%d" % i)) + ": " + _type_name(a, "Variant")
		if i >= first_default and i - first_default < defaults.size():
			piece += " = " + var_to_str(defaults[i - first_default])
		parts.append(piece)
	var ret = m.get("return", {})
	var rtype := _type_name(ret, "void") if ret is Dictionary else "void"
	return "%s(%s) -> %s" % [String(m.get("name", "")), ", ".join(PackedStringArray(parts)), rtype]


static func export_classes() -> Dictionary:
	var out := {}
	for cname in ClassDB.get_class_list():
		if not ClassDB.is_class_enabled(cname):
			continue
		var methods := {}
		var msigs := {}
		for m in ClassDB.class_get_method_list(cname, true):
			var margs = m.get("args", [])
			var defaults = m.get("default_args", [])
			var min_a: int = max(0, margs.size() - defaults.size())
			var max_a: int = margs.size()
			var mname := String(m.get("name", ""))
			if mname != "":
				methods[mname] = [min_a, max_a]
				msigs[mname] = _method_signature(m)
		var props := []
		for p in ClassDB.class_get_property_list(cname, true):
			var pname := String(p.get("name", ""))
			if pname != "":
				props.append(pname)
		var sigs := []
		for sdef in ClassDB.class_get_signal_list(cname, true):
			var sname := String(sdef.get("name", ""))
			if sname != "":
				sigs.append(sname)
		var parent := ClassDB.get_parent_class(cname)
		out[cname] = {
			"inherits": parent if parent != "" else null,
			"methods": methods,
			"signatures": msigs,
			"properties": props,
			"signals": sigs,
		}
	return out
