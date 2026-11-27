extends SceneTree
## Private, framed stdio primitives. The inspected project is never run or imported.

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or not args[0].is_absolute_path():
		quit(2)
		return
	var root := args[0].replace("\\", "/").simplify_path()
	while true:
		var header := OS.read_buffer_from_stdin(4)
		if header.size() != 4: break
		var size := header.decode_u32(0)
		if size == 0 or size > 100000000: break
		var raw := OS.read_buffer_from_stdin(size)
		if raw.size() != size: break
		var request: Variant = JSON.parse_string(raw.get_string_from_utf8())
		if not request is Dictionary: break
		print("GDIO:", JSON.stringify(_perform(root, request)))
	quit()

func _path(root: String, rel: String) -> String:
	if rel.is_empty(): return root
	if rel.is_absolute_path() or rel.contains(":") or rel.contains("\\"): return ""
	var current := root
	for part in rel.split("/"):
		if part in ["", ".", ".."]: return ""
		var parent := DirAccess.open(current)
		if parent != null and parent.is_link(part): return ""
		current = current.path_join(part)
	return current

func _perform(root: String, r: Dictionary) -> Dictionary:
	var path := _path(root, r.rel)
	if path.is_empty(): return {"errno": 13}
	match r.op:
		"stat":
			return {"value": "dir" if DirAccess.dir_exists_absolute(path) else ("file" if FileAccess.file_exists(path) else "")}
		"list":
			var dir := DirAccess.open(path)
			if not dir: return {"errno": 2}
			dir.include_hidden = true
			var rows := []
			var seen := 0
			if dir.list_dir_begin() != OK: return {"errno": 13}
			var name := dir.get_next()
			while not name.is_empty():
				seen += 1
				if r.limit >= 0 and seen > r.limit: return {"value": [[], seen, true]}
				if not dir.is_link(name): rows.append([name, dir.current_is_dir()])
				name = dir.get_next()
			return {"value": [rows, seen, false]}
		"read":
			var f := FileAccess.open(path, FileAccess.READ)
			if not f: return {"errno": 13 if FileAccess.file_exists(path) else 2}
			var n := f.get_length()
			if n > r.limit: return {"errno": 27}
			var data := f.get_buffer(n)
			if data.size() != n: return {"errno": 5}
			return {"value": Marshalls.raw_to_base64(data) if n else ""}
		"stage":
			if not path.get_file().begins_with(".agent-stage-") or not FileAccess.file_exists(path): return {"errno": 13}
			var data := Marshalls.base64_to_raw(r.data) if not r.data.is_empty() else PackedByteArray()
			var f := FileAccess.open(path, FileAccess.WRITE)
			if not f or (not data.is_empty() and not f.store_buffer(data)): return {"errno": 5}
			f.flush()
			return {"value": f.get_length() == data.size()}
		"mkdir":
			if DirAccess.dir_exists_absolute(path) or FileAccess.file_exists(path): return {"errno": 17}
			return {"value": true} if DirAccess.make_dir_absolute(path) == OK else {"errno": 5}
		"remove":
			if not FileAccess.file_exists(path) and not DirAccess.dir_exists_absolute(path): return {"errno": 2}
			return {"value": true} if DirAccess.remove_absolute(path) == OK else {"errno": 5}
		"rename":
			var dest := _path(root, r.dest)
			if dest.is_empty(): return {"errno": 13}
			return {"value": true} if DirAccess.rename_absolute(path, dest) == OK else {"errno": 5}
	return {"errno": 22}
