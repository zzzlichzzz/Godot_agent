extends SceneTree

# ЗАДАЧА 5: живая проверка синхронизации открытой вкладки скрипта.
#
# Гоняется тем же харнессом, что и scene_reload_guard_live.gd: реальный
# headless-редактор, песочница. Что измеряется:
#   1) гипотеза «сопоставление по индексам»: соотношение
#      get_open_scripts() и get_open_script_editors();
#   2) что на самом деле делает штатная панельная функция
#      _sync_open_script_with_disk (вызывается напрямую у собранной панели);
#   3) порядок «буфер → reload(true)» (сырой эксперимент, идёт в diag);
#   4) защита несохранённых правок (6.3).
#
# Имена проверок фиксированные: их сверяет test_remaining_work_steps.py.
const SENTINEL := "TAB_SYNC_RESULTS "
const ENTRY_CANDIDATES := [
	"res://addons/Godot_agent/godot_agent/agent_entry.gd",
	"res://addons/godot_agent/agent_entry.gd",
]

const PATH_A := "res://sync_tab_a.gd"
const PATH_B := "res://sync_tab_b.gd"
const PATH_C := "res://sync_tab_c.gd"
const PATH_D := "res://sync_tab_d.gd"
const PATH_E := "res://sync_tab_e.gd"
const PATH_F1 := "res://sync_tab_f1.gd"
const PATH_F2 := "res://sync_tab_f2.gd"

var completed: Array[String] = []
var failures: Array[String] = []
var diag: Dictionary = {}


func check(name: String, cond: bool, detail: String = "") -> void:
	if cond:
		completed.append(name)
	else:
		failures.append(name + (" :: " + detail if detail != "" else ""))


func _norm(text: String) -> String:
	return str(text).replace("\r\n", "\n")


## Ключ идентичности содержимого: перевод строк и хвостовые пустые строки
## не должны решать, «та ли это вкладка».
func _key(text: String) -> String:
	return _norm(text).strip_edges(false, true)


func _report() -> void:
	print(SENTINEL + JSON.stringify({"completed": completed, "failures": failures, "diag": diag}))


func _load_first(paths: Array) -> Script:
	for p in paths:
		if ResourceLoader.exists(p):
			var s := load(p) as Script
			if s != null:
				return s
	return null


func _write(path: String, text: String) -> bool:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(text)
	f.close()
	return true


func _read(path: String) -> String:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""
	var t := f.get_as_text()
	f.close()
	return t


func _seed() -> bool:
	return (_write(PATH_A, "extends Node\n\nvar marker = \"OLD_A\"\n")
		and _write(PATH_B, "extends Node\n\nvar marker = \"OLD_B\"\n")
		and _write(PATH_C, "extends Node\n\nvar marker = \"OLD_C\"\n")
		and _write(PATH_D, "extends Node\n\nvar marker = \"OLD_D\"\n")
		and _write(PATH_E, "extends Node\n\nvar marker = \"OLD_E\"\n")
		and _write(PATH_F1, "extends Node\n\nvar marker = \"SAME_F\"\n")
		and _write(PATH_F2, "extends Node\n\nvar marker = \"SAME_F\"\n"))


func _script_for(script_editor, path: String) -> Script:
	for scr in script_editor.get_open_scripts():
		if scr != null and str(scr.resource_path) == path:
			return scr
	return null


## Истинная карта «путь -> CodeEdit»: у ЧИСТОЙ вкладки буфер равен
## source_code своего скрипта. Единственная связь, не зависящая от порядка.
func _map_clean_editors(script_editor) -> Dictionary:
	var mapping := {}
	for scr in script_editor.get_open_scripts():
		if scr == null:
			continue
		var reference := _key(scr.source_code)
		for editor in script_editor.get_open_script_editors():
			if editor == null:
				continue
			var ce := editor.get_base_editor() as CodeEdit
			if ce != null and _key(ce.text) == reference:
				mapping[str(scr.resource_path)] = ce
				break
	return mapping


func _editor_owner(map: Dictionary, editor) -> String:
	if editor == null:
		return "(null)"
	var ce := editor.get_base_editor() as CodeEdit
	for k in map.keys():
		if map[k] == ce:
			return k
	return "(dirty/unknown)"


func _init() -> void:
	if not _seed():
		check("полигон записан", false, "не удалось создать sync-скрипты")
		_report()
		quit(1)
		return

	# Детерминизм: выключаем редакторскую авто-перезагрузку скриптов на
	# внешнее изменение — иначе непонятно, обновила вкладку панель или сам
	# редактор. Настройка восстанавливается перед выходом.
	var settings = EditorInterface.get_editor_settings()
	var auto_key := "text_editor/behavior/files/auto_reload_scripts_on_external_change"
	var auto_old = null
	var auto_had := false
	if settings != null:
		auto_had = settings.has_setting(auto_key)
		auto_old = settings.get_setting(auto_key) if auto_had else null
	# Настройку НЕ трогаем здесь: сценарий реальной цепочки (update_file)
	# должен сначала отработать при исходном состоянии редактора.
	# Выключаем её перед изолированными экспериментами ниже.
	diag["auto_reload_old"] = str(auto_old)

	# Панель собирается тем же путём, что в context_menu_e2e_live.gd.
	var entry_script := _load_first(ENTRY_CANDIDATES)
	var panel = null
	if entry_script != null:
		var entry = entry_script.new()
		entry.call("_load_locale")
		var panel_path: String = entry.call("_find_file",
			entry.call("_addon_path"), "agent_panel.gd")
		panel = entry.call("_build_panel", panel_path)
		if panel != null:
			entry.set("_dock", panel)
			get_root().add_child(panel)
			await process_frame
	check("панель собрана", panel != null)

	var script_editor = EditorInterface.get_script_editor()
	check("редактор скриптов доступен", script_editor != null)
	if panel == null or script_editor == null:
		if settings != null and auto_had:
			settings.set_setting(auto_key, auto_old)
		_report()
		quit(1)
		return

	# Открываем скрипты в порядке b, a, c — он не совпадает с алфавитным.
	# Если движок сортирует список скриптов, пары «индекс списка = индекс
	# вкладки» ломаются именно здесь.
	EditorInterface.edit_script(load(PATH_B), -1, 0, false)
	await process_frame
	EditorInterface.edit_script(load(PATH_A), -1, 0, false)
	await process_frame
	EditorInterface.edit_script(load(PATH_C), -1, 0, false)
	await process_frame

	var open_scripts: Array = script_editor.get_open_scripts()
	var open_editors: Array = script_editor.get_open_script_editors()
	var names: Array = []
	for scr in open_scripts:
		names.append(str(scr.resource_path) if scr != null else "null")
	diag["open_scripts"] = names
	diag["open_editor_count"] = open_editors.size()
	check("скрипты открыты в редакторе",
		open_scripts.size() >= 3 and open_editors.size() >= 3,
		"scripts=%d editors=%d" % [open_scripts.size(), open_editors.size()])

	var map := _map_clean_editors(script_editor)
	diag["mapped"] = map.keys()
	check("карта редактор<-содержимое собрана",
		map.has(PATH_A) and map.has(PATH_B) and map.has(PATH_C), str(map.keys()))

	# Диагностика гипотезы №1: чем на самом деле является open_editors[i]
	# для open_scripts[i] при нашем порядке открытия.
	var index_pairs: Array = []
	for i in range(open_scripts.size()):
		var sp := str(open_scripts[i].resource_path) if open_scripts[i] != null else "null"
		var owner := "(нет пары)"
		if i < open_editors.size():
			owner = _editor_owner(map, open_editors[i])
		index_pairs.append("%d: script=%s -> editor_of=%s" % [i, sp, owner])
	diag["index_pairs"] = index_pairs

	var ce_a = map.get(PATH_A, null)
	var ce_b = map.get(PATH_B, null)
	var ce_c = map.get(PATH_C, null)
	if ce_a == null or ce_b == null or ce_c == null:
		if settings != null and auto_had:
			settings.set_setting(auto_key, auto_old)
		_report()
		quit(1)
		return

	# --- реальная цепочка перехвата: update_file + sync, настройка
	#     авто-перезагрузки редактора — в исходном состоянии -----------------
	EditorInterface.edit_script(load(PATH_D), -1, 0, false)
	await process_frame
	var map_d := _map_clean_editors(script_editor)
	var ce_d = map_d.get(PATH_D, null)
	check("вкладка d открыта", ce_d != null)
	if ce_d != null:
		diag["guard_d_before"] = "version=%d saved=%d" % [
			ce_d.get_version(), ce_d.get_saved_version()]
		_write(PATH_D, "extends Node\n\nvar marker = \"NEW_D\"\n")
		panel.call("_refresh_changed_paths", [[PATH_D]])
		panel.call("_sync_open_script_with_disk", PATH_D)
		await process_frame
		await process_frame
		var d_text := _norm(ce_d.text)
		diag["d_tab_after"] = d_text.substr(0, 48)
		check("цепочка update_file+sync обновляет вкладку",
			d_text.contains("NEW_D"), d_text.substr(0, 60))

	# Дальше — изолированные эксперименты: редакторская авто-перезагрузка
	# выключена, чтобы её эффект не подменял поведение панели.
	if settings != null:
		settings.set_setting(auto_key, false)

	# --- 6.4 + основной сценарий: цель — НЕактивная вкладка b ---------------
	_write(PATH_B, "extends Node\n\nvar marker = \"NEW_B\"\n")
	ce_b.set_caret_line(2)
	ce_b.set_caret_column(4)
	panel.call("_sync_open_script_with_disk", PATH_B)
	await process_frame
	await process_frame

	var b_text := _norm(ce_b.text)
	var a_text := _norm(ce_a.text)
	var a_source := _norm((load(PATH_A) as Script).source_code)
	var b_script := _script_for(script_editor, PATH_B)
	diag["b_tab_after"] = b_text.substr(0, 48)
	diag["a_tab_after"] = a_text.substr(0, 48)
	diag["b_source_after"] = _norm(b_script.source_code).substr(0, 48) if b_script != null else "no-script"
	diag["b_load_source_after"] = _norm((load(PATH_B) as Script).source_code).substr(0, 48)
	check("вкладка цели обновлена", b_text.contains("NEW_B"), b_text.substr(0, 60))
	check("чужая вкладка не тронута", a_text == a_source, a_text.substr(0, 60))
	check("каретка сохранена",
		ce_b.get_caret_line() == 2 and ce_b.get_caret_column() == 4,
		"line=%d col=%d" % [ce_b.get_caret_line(), ce_b.get_caret_column()])
	# Ctrl+S-безопасность: редактор считает буфер сохранённым, а сам буфер
	# совпадает с файлом на диске — сохранение не может откатить правку.
	check("буфер помечен сохранённым",
		ce_b.get_version() == ce_b.get_saved_version(),
		"v=%d saved=%d" % [ce_b.get_version(), ce_b.get_saved_version()])
	check("ресурс перечитан с диска",
		b_script != null and _norm(b_script.source_code).contains("NEW_B"), "")
	check("файлы на диске не изменены синхронизацией",
		_norm(_read(PATH_B)).contains("NEW_B")
		and _norm(_read(PATH_A)).contains("OLD_A"))

	# --- сырая диагностика ресурса: почему source_code не обновился ---------
	if b_script != null:
		diag["b_valid"] = str(is_instance_valid(b_script))
		diag["b_path"] = str(b_script.resource_path)
		var err_true: int = b_script.reload(true)
		diag["reload_true_err"] = err_true
		diag["res_after_reload_true"] = _norm(b_script.source_code).substr(0, 48)
		var err_false: int = b_script.reload(false)
		diag["reload_false_err"] = err_false
		diag["res_after_reload_false"] = _norm(b_script.source_code).substr(0, 48)

	# --- E: каким API движка ресурс РЕАЛЬНО перечитывается с диска ----------
	# GDScript::reload() файл не читает (это видно в исходниках движка);
	# проверяем кандидатов: update_file, CACHE_MODE_REPLACE, load_source_code.
	EditorInterface.edit_script(load(PATH_E), -1, 0, false)
	await process_frame
	var map_e := _map_clean_editors(script_editor)
	var ce_e = map_e.get(PATH_E, null)
	var sc_e := _script_for(script_editor, PATH_E)
	check("вкладка e открыта", ce_e != null and sc_e != null)
	if ce_e != null and sc_e != null:
		_write(PATH_E, "extends Node\n\nvar marker = \"NEW_E\"\n")
		var efs = EditorInterface.get_resource_filesystem()
		if efs != null and efs.has_method("update_file"):
			efs.update_file(PATH_E)
		await process_frame
		await process_frame
		diag["e_after_update_file_src"] = _norm(sc_e.source_code).substr(0, 48)
		diag["e_after_update_file_tab"] = _norm(ce_e.text).substr(0, 48)
		var fresh = ResourceLoader.load(PATH_E, "", ResourceLoader.CACHE_MODE_REPLACE)
		diag["e_replace_same_instance"] = str(fresh == sc_e)
		if fresh is Script:
			diag["e_after_replace_src"] = _norm((fresh as Script).source_code).substr(0, 48)
		var has_lsc: bool = sc_e.has_method("load_source_code")
		diag["e_has_load_source_code"] = str(has_lsc)
		if has_lsc:
			var err_lsc: int = sc_e.call("load_source_code", PATH_E)
			diag["e_load_source_code_err"] = err_lsc
			diag["e_after_load_source_code"] = _norm(sc_e.source_code).substr(0, 48)

	# --- сырой эксперимент по гипотезе №2: что делает reload(true) с буфером.
	_write(PATH_C, "extends Node\n\nvar marker = \"NEW_C\"\n")
	ce_c.text = "extends Node\n\nvar marker = \"NEW_C\"\n"
	ce_c.tag_saved_version()
	var script_c := _script_for(script_editor, PATH_C)
	if script_c != null:
		script_c.reload(true)
	await process_frame
	diag["reload_after_manual_update"] = _norm(ce_c.text).substr(0, 48)

	# --- 6.3: вкладка с несохранёнными правками не перезаписывается --------
	ce_c.set_caret_line(0)
	ce_c.begin_complex_operation()
	ce_c.insert_text_at_caret("# unsaved\n")
	ce_c.end_complex_operation()
	await process_frame
	var dirty: bool = ce_c.get_version() != ce_c.get_saved_version()
	diag["dirty_guard_state"] = "version=%d saved=%d dirty=%s" % [
		ce_c.get_version(), ce_c.get_saved_version(), str(dirty)]
	_write(PATH_C, "extends Node\n\nvar marker = \"NEW_C2\"\n")
	panel.call("_sync_open_script_with_disk", PATH_C)
	await process_frame
	await process_frame
	var c_dirty_text := _norm(ce_c.text)
	diag["dirty_tab_after"] = c_dirty_text.substr(0, 48)
	check("несохранённые правки не затёрты",
		dirty and c_dirty_text.contains("# unsaved"),
		"dirty=%s text=%s" % [str(dirty), c_dirty_text.substr(0, 60)])

	# --- F: две вкладки с ОДИНАКОВЫМ содержимым — сопоставление неоднозначно,
	#     чужие буферы не трогаются -----------------------------------------
	EditorInterface.edit_script(load(PATH_F1), -1, 0, false)
	await process_frame
	EditorInterface.edit_script(load(PATH_F2), -1, 0, false)
	await process_frame
	var map_f := _map_clean_editors(script_editor)
	var ce_f1 = map_f.get(PATH_F1, null)
	var ce_f2 = map_f.get(PATH_F2, null)
	check("вкладки f открыты", ce_f1 != null and ce_f2 != null)
	if ce_f1 != null and ce_f2 != null:
		_write(PATH_F1, "extends Node\n\nvar marker = \"NEW_F\"\n")
		panel.call("_sync_open_script_with_disk", PATH_F1)
		await process_frame
		await process_frame
		var f1_text := _norm(ce_f1.text)
		var f2_text := _norm(ce_f2.text)
		diag["ambiguous_f1"] = f1_text.substr(0, 32)
		diag["ambiguous_f2"] = f2_text.substr(0, 32)
		check("неоднозначная вкладка не тронута",
			f1_text.contains("SAME_F") and f2_text.contains("SAME_F"),
			"f1=%s f2=%s" % [f1_text.substr(0, 32), f2_text.substr(0, 32)])

	if settings != null and auto_had:
		settings.set_setting(auto_key, auto_old)
	_report()
	quit(1 if failures.size() > 0 else 0)
