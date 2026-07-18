@tool
extends RefCounted
# Экспорт РЕАЛЬНОГО API текущей версии Godot через ClassDB.
# Сервер использует это, чтобы проверять код модели против фактических
# методов/свойств/сигналов движка, а не по памяти обучения нейросети.
#
# no_inheritance = true у всех трёх ClassDB-запросов: берём у каждого класса
# только его СОБСТВЕННЫЕ члены — цепочку наследования достраивает Python
# (gd_api_cache.py) на основе поля "inherits". Так JSON выходит компактным.

static func export_classes() -> Dictionary:
	var out := {}
	for cname in ClassDB.get_class_list():
		if not ClassDB.is_class_enabled(cname):
			continue
		var methods := {}
		for m in ClassDB.class_get_method_list(cname, true):
			var margs = m.get("args", [])
			var defaults = m.get("default_args", [])
			var min_a: int = max(0, margs.size() - defaults.size())
			var max_a: int = margs.size()
			var mname := String(m.get("name", ""))
			if mname != "":
				methods[mname] = [min_a, max_a]
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
			"properties": props,
			"signals": sigs,
		}
	return out
