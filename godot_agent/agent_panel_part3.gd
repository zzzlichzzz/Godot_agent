@tool
extends RefCounted

# Модуль agent_panel_part3: методы вынесены «пилой» split_gd из agent_panel.gd.
# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,
# поэтому connect()/call() по исходным именам продолжают работать.
# Тело работает через параметр panel: к членам донора — panel.<член>,
# к другим методам донора — panel.<метод> (через его обёртку).

# --- константы, скопированные из донора (неизменяемы) ---
const CHECK_LOG_URL = AgentServer.URL_PROJECT_CHECK_LOG
const PROGRESS_URL = AgentServer.URL_CHAT_PROGRESS
# ---------------------------------------------------------------------------
# ЗАДАЧА 2: одна отправка finalize вместо трёх копий.
#
# Первопричина дублирования. Сцена, настройки проекта и ресурс отправляли отчёт
# об исходе тремя почти дословными копиями. Копии разошлись: правило «не
# повторяемся вечно после терминального ответа» появилось у одной и
# переехало в остальные две лишь частично, поэтому правка одного пути
# забывала другой.
#
# Теперь вид транзакции — данные, а не отдельная функция: FINALIZE_KINDS
# перечисляет адрес, тело и счётчик повторов. Правила повтора и терминальных
# кодов существуют в одном экземпляре на все три вида.
# ---------------------------------------------------------------------------
const FINALIZE_KINDS := ["scene", "project_settings", "resource"]

static func _open_pending_scene_paths(panel) -> PackedStringArray:
	var result := PackedStringArray()
	var open_scenes := EditorInterface.get_open_scenes()
	var targets = panel._last_pending_action_paths.duplicate()
	targets.append(panel._last_pending_action_path)
	targets.append(panel._last_pending_action_dest)
	for raw in targets:
		var sp := str(raw)
		if sp == "" or not (sp.to_lower().ends_with(".tscn") or sp.to_lower().ends_with(".scn")):
			continue
		for opened in open_scenes:
			if str(opened).to_lower() == sp.to_lower() and not result.has(sp):
				result.append(sp)
	return result

static func _close_scenes_before_write(panel) -> void:
	# v49: перед одобренной записью закрываем открытые целевые сцены,
	# предварительно сохранив их, чтобы не потерять пользовательские изменения.
	# После применения правок они открываются заново уже в новом виде.
	panel._scenes_to_reopen = PackedStringArray()
	var ei: Object = EditorInterface
	if not ei.has_method("close_scene"):
		return  # старый Godot без close_scene: остаётся авто-перечитывание (v46)
	if ei.has_method("save_all_scenes"):
		ei.call("save_all_scenes")
	elif ei.has_method("save_scene"):
		ei.call("save_scene")
	var open_targets = panel._open_pending_scene_paths()
	for raw in [panel._last_pending_action_path, panel._last_pending_action_dest]:
		var sp := str(raw)
		if sp == "" or not (sp.ends_with(".tscn") or sp.ends_with(".scn")):
			continue
		if not EditorInterface.get_open_scenes().has(sp) and not open_targets.has(sp):
			continue
		EditorInterface.open_scene_from_path(sp)  # делаем вкладку сцены активной
		if int(ei.call("close_scene")) == OK and not panel._scenes_to_reopen.has(sp):
			panel._scenes_to_reopen.append(sp)
	for sp in open_targets:
		if not panel._scenes_to_reopen.has(sp):
			EditorInterface.open_scene_from_path(sp)
			if int(ei.call("close_scene")) == OK:
				panel._scenes_to_reopen.append(sp)

static func _reopen_scenes_after_write(panel) -> void:
	# v49: открываем обратно сцены, закрытые перед записью. Если действие
	# не выполнилось или файл переехал/удалён — просто пропускаем.
	for sp in panel._scenes_to_reopen:
		if FileAccess.file_exists(str(sp)):
			EditorInterface.open_scene_from_path(str(sp))
	panel._scenes_to_reopen = PackedStringArray()

static func _close_target_scenes_before_write(panel, extra_targets: PackedStringArray) -> void:
	panel._scenes_to_reopen = PackedStringArray()
	var ei: Object = EditorInterface
	if not ei.has_method("close_scene"):
		return
	if ei.has_method("save_all_scenes"):
		ei.call("save_all_scenes")
	elif ei.has_method("save_scene"):
		ei.call("save_scene")
	var open_scenes := EditorInterface.get_open_scenes()
	for raw in extra_targets:
		var sp := str(raw)
		if sp == "" or not (sp.ends_with(".tscn") or sp.ends_with(".scn")):
			continue
		for opened in open_scenes:
			if str(opened).to_lower() == sp.to_lower() and not panel._scenes_to_reopen.has(str(opened)):
				EditorInterface.open_scene_from_path(str(opened))
				if int(ei.call("close_scene")) == OK:
					panel._scenes_to_reopen.append(str(opened))

static func _remap_scenes_to_reopen(panel, old_path: String, new_path: String) -> void:
	for i in range(panel._scenes_to_reopen.size()):
		if panel._scenes_to_reopen[i].to_lower() == old_path.to_lower():
			panel._scenes_to_reopen[i] = new_path

static func _sync_resource_uid(panel, _old_path: String, new_path: String) -> void:
	# v106 (audit 3.1): штатный ResourceLoader.get_resource_uid() вместо ручного
	# парсинга первой строки (UID текстур/звука лежит в .import-файле, бинарники
	# построчно разбирать бессмысленно). Для папок обходим файлы рекурсивно.
	#
	# ЗАДАЧА 3: здесь больше НЕТ полного scan(). Раньше он стоял после
	# update_file() и пересчитывал весь проект ради одного файла. Для каталога
	# update_file() не годится — он не заходит внутрь, — поэтому при обходе
	# папки обновляем каждый найденный файл поимённо.
	#
	# ЗАДАЧА 4: решение «обновлять этот файл или пересчитывать проект»
	# принимает шлюз мутаций, а не сама панель.
	if new_path.is_empty():
		return
	var global_new := ProjectSettings.globalize_path(new_path)
	if DirAccess.dir_exists_absolute(global_new):
		var dir := DirAccess.open(global_new)
		if dir:
			dir.list_dir_begin()
			var name := dir.get_next()
			while name != "":
				if not name.begins_with("."):
					panel._sync_resource_uid("", new_path.trim_suffix("/") + "/" + name)
				name = dir.get_next()
			dir.list_dir_end()
	else:
		var uid := ResourceLoader.get_resource_uid(new_path)
		if uid != ResourceUID.INVALID_ID:
			if ResourceUID.has_id(uid):
				ResourceUID.set_id(uid, new_path)
			else:
				ResourceUID.add_id(uid, new_path)
	panel._notify_path_changed(new_path)

## Сообщить редактору об изменении файла — через шлюз мутаций (ЗАДАЧА 4).
##
## Шлюз владеет решением «обновить один файл или пересчитать проект» и ведёт
## журнал. Без шлюза (изолированный тест, до подключения плагина) делаем то же
## самое напрямую, чтобы поведение не зависело от порядка инициализации.
static func _notify_path_changed(panel, path: String) -> void:
	if path == "":
		return
	if panel._mutation_gate and panel._mutation_gate.has_method("notify_changed"):
		panel._mutation_gate.call("notify_changed", path)
		return
	var efs := EditorInterface.get_resource_filesystem()
	if efs and efs.has_method("update_file"):
		efs.call("update_file", path)

## Сообщить редактору об изменениях по списку ИЗВЕСТНЫХ путей (ЗАДАЧА 3).
##
## Заменяет полный scan() там, где сервер уже перечислил, что именно он
## поменял. update_file() пересчитывает один файл, scan() — весь проект;
## на проекте в тысячи файлов разница видна глазами.
##
## Принимает и один путь, и список, и список списков: вызывающие места
## передают то, что вернул сервер, и это либо строка, либо Array путей,
## который сам лежит в общем списке вместе с переименованным файлом.
static func _refresh_changed_paths(panel, paths) -> void:
	var efs := EditorInterface.get_resource_filesystem()
	if efs == null or paths == null:
		return
	var pending: Array = [paths]
	var seen := {}
	while not pending.is_empty():
		var item = pending.pop_back()
		if item is Array or item is PackedStringArray:
			pending.append_array(Array(item))
			continue
		var path := str(item)
		if path == "" or seen.has(path):
			continue
		seen[path] = true
		# Каталог целиком update_file() не перечитывает; его содержимое уже
		# обошёл _sync_resource_uid, поэтому пропускаем молча, а не сканируем
		# ради него весь проект.
		if DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(path)):
			continue
		if not efs.has_method("update_file"):
			return
		efs.call("update_file", path)

static func _ensure_script_autoreload_setting(panel) -> void:
	# Editor preferences belong to the user, not to the plugin.
	var es = EditorInterface.get_editor_settings()
	if es == null:
		return
	var key := "text_editor/behavior/files/auto_reload_scripts_on_external_change"
	if es.has_setting(key) and not bool(es.get_setting(key)):
		push_warning("Автоперезагрузка скриптов выключена. При необходимости включите её в Editor Settings; агент не меняет эту настройку.")

static func _force_reload_open_script(panel) -> void:
	var target_path = panel._last_pending_action_path
	if panel._last_pending_action_type == "move_file" and not panel._last_pending_action_dest.is_empty():
		target_path = panel._last_pending_action_dest
	panel._sync_open_script_with_disk(target_path)

static func _dirty_open_scripts(panel, target_paths: PackedStringArray) -> PackedStringArray:
	var affected := PackedStringArray()
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor:
		return affected
	var wanted := {}
	for path in target_paths:
		if path != "":
			wanted[path.to_lower()] = true
	for scr in script_editor.get_open_scripts():
		if scr == null:
			continue
		var path_str := str(scr.resource_path)
		if not wanted.is_empty() and not wanted.has(path_str.to_lower()):
			continue
		# Вкладку ищем без арифметики по индексам (см. _find_open_code_edit_for).
		var code_edit = panel._find_open_code_edit_for(script_editor, scr, path_str)
		if code_edit == null:
			# Чистая вкладка всегда опознаётся по содержимому; если вкладку
			# найти не удалось, значит в ней есть несохранённые правки.
			if not affected.has(path_str):
				affected.append(path_str)
			continue
		if code_edit.get_version() != code_edit.get_saved_version():
			if not affected.has(path_str):
				affected.append(path_str)
	return affected

static func _sync_open_script_with_disk(panel, target_path: String) -> void:
	if target_path.is_empty() or not target_path.begins_with("res://"):
		return
	if not FileAccess.file_exists(target_path):
		return
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor:
		return

	var file := FileAccess.open(target_path, FileAccess.READ)
	if not file:
		push_warning("Не удалось открыть файл для чтения: " + target_path)
		return
	var real_text := file.get_as_text()
	file.close()

	var open_scripts := script_editor.get_open_scripts()
	var target_script: Script = null
	for scr in open_scripts:
		if scr and scr.resource_path == target_path:
			target_script = scr
			break

	# Вкладку опознаём ДО перезагрузки ресурса: буфер чистой вкладки равен
	# СТАРОМУ source_code, по нему и находится нужный редактор.
	var target_code_edit = panel._find_open_code_edit_for(script_editor, target_script, target_path)

	var buffer_synced := false
	if target_code_edit:
		var has_unsaved_edits = target_code_edit.get_version() != target_code_edit.get_saved_version()
		if has_unsaved_edits:
			push_warning("Вкладка '%s' содержит несохранённые правки — авто-обновление пропущено, чтобы не потерять их." % target_path)
		else:
			buffer_synced = true
			if target_code_edit.text != real_text:
				var caret_line = target_code_edit.get_caret_line()
				var caret_col = target_code_edit.get_caret_column()
				target_code_edit.text = real_text
				target_code_edit.set_caret_line(min(caret_line, max(0, target_code_edit.get_line_count() - 1)))
				target_code_edit.set_caret_column(caret_col)
				target_code_edit.tag_saved_version()
				print("Вкладка скрипта синхронизирована с диском: ", target_path)
	elif target_script:
		# Скрипт открыт, но чистой вкладки, показывающей его, не нашлось:
		# либо несохранённые правки, либо несколько вкладок с одинаковым
		# содержимым (сопоставление неоднозначно). Буфер не трогаем — это и
		# есть защита 6.3.
		push_warning("Вкладка '%s' не синхронизирована: вкладку не удалось надёжно опознать (несохранённые правки или несколько вкладок с одинаковым содержимым)." % target_path)

	# Обновление РЕСУРСА. Измерено живой фикстурой (script_tab_sync_live.gd) и
	# сверено с исходниками Godot 4.6: GDScript::reload() файл с диска НЕ
	# читает — он лишь пере-парсит уже загруженный текст (err=OK, source_code
	# не меняется ни при keep_state=true, ни при false). Ресурс освежает пара
	# «set_source_code(текст с диска) + reload(true)» — ровно тот порядок,
	# которым внутри движка пользуется load_source_code() + reload() при
	# авто-перезагрузке скриптов. При несохранённых правках ресурс не трогаем:
	# буфер человека — источник правды, ресурс догонит его при сохранении.
	if target_script and buffer_synced:
		if target_script.source_code != real_text:
			target_script.set_source_code(real_text)
		target_script.reload(true)
	elif ResourceLoader.has_cached(target_path):
		var res = ResourceLoader.load(target_path, "", ResourceLoader.CACHE_MODE_REPLACE)
		if res is Script and res.source_code != real_text:
			# CACHE_MODE_REPLACE возвращает тот же инстанс (измерено живой
			# фикстурой), поэтому «перечитать с диска» работает только так же,
			# как для открытой вкладки: set_source_code(диск) + reload. Ветка
			# срабатывает для закэшированного, но НЕ открытого скрипта.
			res.set_source_code(real_text)
			res.reload(true)

## Найти CodeEdit, показывающий ИМЕННО target_script.
##
## Сопоставление get_open_scripts()[i] и get_open_script_editors()[i] по
## индексу движком не гарантировано (список скриптов сортируется по имени,
## вкладки идут в порядке открытия), а метода «какой скрипт показываешь» у
## ScriptEditorBase нет. Поэтому:
##   1) активная вкладка — ground truth через get_current_script();
##   2) неактивные — по содержимому: у чистой вкладки буфер равен source_code.
static func _find_open_code_edit_for(panel, script_editor, target_script: Script, target_path: String) -> CodeEdit:
	var current_script: Script = script_editor.get_current_script()
	if current_script != null and str(current_script.resource_path) == target_path:
		var current = script_editor.get_current_editor()
		if current:
			var current_edit := current.get_base_editor() as CodeEdit
			if current_edit:
				return current_edit
	if target_script == null:
		return null
	var reference = panel._normalized_script_text(target_script.source_code)
	# Собираем ВСЕ совпадения: одинаковое содержимое у двух вкладок (шаблон,
	# копия) делает сопоставление неоднозначным — тогда чужой буфер трогать
	# нельзя, и это НЕ ошибка, а честный отказ (внешний warning объяснит).
	var matches: Array[CodeEdit] = []
	for editor in script_editor.get_open_script_editors():
		if editor == null:
			continue
		var code_edit := editor.get_base_editor() as CodeEdit
		if code_edit != null and panel._normalized_script_text(code_edit.text) == reference:
			matches.append(code_edit)
	if matches.size() == 1:
		return matches[0]
	return null

## Сравнимый вид текста скрипта: хвостовые пустые строки и CRLF не должны
## решать, «та ли это вкладка».
static func _normalized_script_text(panel, text: String) -> String:
	return str(text).replace("\r\n", "\n").rstrip("\n")

static func _on_play_watch_tick(panel) -> void:
	# Страховка от забытого отчёта: раз в такт возвращаем неотправленные
	# конверты в сеть. Перебор видов вместо трёх одинаковых блоков — ЗАДАЧА 2.
	for finalize_kind in FINALIZE_KINDS:
			if panel._finalize_body(finalize_kind).is_empty() \
					or bool(panel._finalize_retrying.get(finalize_kind, false)) \
					or panel._is_network_busy \
					or panel._pending_request_kind == finalize_kind + "_finalize":
				continue
			panel._send_pending_finalize(finalize_kind)
	if panel._hl: panel._hl.watchdog()
	panel._reconcile_confirm_buttons()
	if not panel._pending_runtime_check_result_body.is_empty() and not panel._is_network_busy:
		panel._send_pending_runtime_check_result()
	var playing := EditorInterface.is_playing_scene()
	if panel._was_playing and not playing:
		panel._was_playing = false
		# Игра только что закрылась: даём Godot дописать лог и проверяем.
		await panel.get_tree().create_timer(1.2).timeout
		panel._auto_check_log()
		return
	panel._was_playing = playing

static func _auto_check_log(panel) -> void:
	# Не мешаем текущей работе: если идёт запрос или ждём подтверждения —
	# тихо пропускаем (ручная кнопка всегда доступна).
	if panel._is_network_busy: return
	if panel._has_pending_action(): return
	panel._auto_check = true
	panel._pending_log_send = false
	var headers = panel._json_headers()
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir()),
	}
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "check_log"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(CHECK_LOG_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._auto_check = false

static func _on_progress_tick(panel) -> void:
	if not panel._is_network_busy:
		if panel._progress_timer:
			panel._progress_timer.stop()
		if panel._view:
			panel._view.hide_status()
		return
	if panel._progress_inflight or panel._link == null:
		return
	# Токен обязателен и здесь: /chat/progress — обычный GET, но сервер после
	# привязки проверяет ВСЕ запросы. Без заголовка он отвечал бы 403, а
	# _on_progress_response молча игнорирует не-200 — живая трансляция ответа
	# просто перестала бы появляться в чате, без единого сообщения об ошибке.
	if panel._link.get_now("progress", PROGRESS_URL):
		panel._progress_inflight = true

## Раздача коротких ответов по id. Один канал на все короткие запросы,
## поэтому кто именно пришёл — определяет метка, а не порядок.
static func _on_short_response(panel, id: String, result: int, code: int,
		headers: PackedStringArray, body: PackedByteArray) -> void:
	match id:
		"progress":
			panel._on_progress_response(result, code, headers, body)
		"live_input":
			panel._on_live_input_response(result, code, headers, body)
		"chat_stop":
			panel._on_short_stop_response(result, code)
		"post_move_sync":
			panel._on_post_move_sync_response(result, code, body)
		"node_rename_sync":
			panel._on_node_rename_sync_response(result, code, body)
		"node_rename_apply":
			panel._on_node_rename_apply_response(result, code, body)
		_:
			push_warning("[Godot Agent] Неизвестный короткий запрос: " + id)

static func _on_short_stop_response(panel, _result: int, _code: int) -> void:
	if panel._stop_button:
		panel._stop_button.disabled = false
		panel._stop_button.text = panel._t("stop_btn")

static func _on_progress_response(panel, _result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	panel._progress_inflight = false
	if not panel._is_network_busy or panel._view == null:
		return
	if response_code != 200:
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null or typeof(json) != TYPE_DICTIONARY:
		return
	if not bool(json.get("active", false)):
		return
	# Статус — только состояние бота; сам текст стримится прямо в чат (в _view).
	panel._view.show_status(str(json.get("phase", panel._t("working"))), int(json.get("elapsed", 0)), int(json.get("chars", 0)))
	panel._view.feed_live_stream(str(json.get("stream", "")))

static func _request_chats(panel, kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if panel._link == null:
		return
	if panel._is_network_busy and kind != "list" and kind != "sites" and kind != "status" and kind != "minilich_status" and kind != "minilich_set" and kind != "minilich_github" and not kind.begins_with("api_"):
		panel._log_error(panel._t("wait_current"))
		return
	panel._link.request(kind, panel._policy_body(extra), allow_autostart)

static func _on_chats_payload(panel, kind: String, json: Dictionary, extra: Dictionary) -> void:
	if kind == "minilich_github":
		if panel._minilich_github_label:
			if json.has("error"):
				panel._minilich_github_label.text = str(json.get("error", ""))
			else:
				panel._minilich_github_label.text = panel._t("github_fetch_running")
		return
	if kind == "minilich_status" or kind == "minilich_set":
		panel._on_minilich_payload(kind, json)
		return
	if kind == "status":
		panel._on_browser_status(json)
		return
	if kind == "chat_model":
		# Смена модели у ОТКРЫТОГО чата. Обрабатывается до общего хвоста: чат
		# перерисовывать нельзя — переписка сохранена, и это главное свойство
		# действия. Меняется только подпись модели и появляется системная строка.
		if json.has("error"):
			panel._notify(str(json.get("error", "")), "error")
			panel._log_error(str(json.get("error", "")))
			return
		panel._api_chat_model = str(json.get("model", ""))
		panel._api_chat_site = str(json.get("site", ""))
		panel._push_api_switch_target()
		if panel._view:
			panel._view.add_system(panel._t("chat_model_changed") % str(json.get("site", "")))
		panel._notify(panel._t("chat_model_changed_short"), "success")
		panel._fill_chat_list(json.get("chats", []))
		if panel._start_screen:
			panel._start_screen.set_chats(json.get("chats", []))
		return
	if kind.begins_with("api_"):
		panel._on_api_payload(kind, json)
		return
	if kind == "sites":
		if panel._start_screen:
			panel._start_screen.set_sites(json.get("sites", []))
			if panel._pending_view == "sites":
				panel._pending_view = ""
				panel._start_screen.show_sites()
		return
	if json.has("error"):
		if kind == "list":
			# Фоновое обновление списка чатов во время выполнения задачи не должно спамить ошибкой
			return
		var message = str(json.get("error", panel._t("srv_no_response")))
		panel._log_error(message)
		panel._notify(message, "error")
		if kind == "open" or kind == "new":
			panel._site_resend_envelope = {}
			panel._restore_chat_draft()
		return
	var cur = json.get("current_id")
	if cur != null and (kind == "open" or kind == "new"):
		panel._switch_chat_draft(str(cur))
	if cur != null:
		panel._current_chat_id = str(cur)
	if kind == "open" or kind == "new":
		panel._chat_navigation_generation += 1
		# Не стираем новый draft, набранный пока запрос навигации был в пути.
		# Очищаем только действительно пустое/старое визуальное состояние.
		if panel.input_field == null or panel.input_field.text.is_empty():
			panel._clear_chat_input(true)
		var keeps_resend = (kind == "open"
			and not panel._site_resend_envelope.is_empty()
			and bool(panel._site_resend_envelope.get("waiting_open", false))
			and str(panel._site_resend_envelope.get("chat_id", "")) == panel._current_chat_id
			and int(panel._site_resend_envelope.get("expected_generation", -1)) == panel._chat_navigation_generation)
		if not keeps_resend:
			if not panel._site_resend_envelope.is_empty():
				var source_chat = str(panel._site_resend_envelope.get("chat_id", ""))
				var source_prompt = str(panel._site_resend_envelope.get("prompt", ""))
				if source_chat != "" and source_prompt != "":
					panel._chat_drafts[source_chat] = source_prompt
			panel._site_resend_envelope = {}
			# Это завершение навигации, а не успешная отправка сообщения.
			# Не удаляем восстановленный draft нового чата.
			panel._pending_chat_prompt = ""
			panel._pending_editor_context = {}
	panel._fill_chat_list(json.get("chats", []))
	if panel._start_screen:
		panel._start_screen.set_chats(json.get("chats", []))
		if panel._pending_view == "chats":
			panel._pending_view = ""
			panel._start_screen.show_chats()
	if kind == "open" and panel._view:
		panel._clear_pending_action_state()
		panel._view.clear()
		# Модель запоминаем ТОЛЬКО для чата по ключу: у браузерного её нет, и
		# оставленная от прошлого чата строка предложила бы сменить то, чего не
		# существует.
		panel._api_chat_model = (str(json.get("model", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		panel._api_chat_site = (str(json.get("site", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		panel._push_api_switch_target()
		panel._view.set_battle_scope(str(json.get("site_id", "")) == "arena_battle")
		panel._render_transcript(json.get("transcript", []))
		panel._view.add_system(panel._t("chat_opened") % str(json.get("title", "")))
		var warn: String = str(json.get("warning", ""))
		if warn != "":
			panel._view.add_system(warn)
			panel._notify(warn, "error")
		var trimmed := int(json.get("transcript_trimmed", 0))
		if trimmed > 0:
			panel._view.add_system("Более старые сообщения этого чата не показаны: %d." % trimmed)
		panel._enter_chat_ui()
		# У чата по ключу API нет страницы в браузере: ждать её загрузки нечего,
		# а ожидание ещё и 40 раз опросило бы /browser/status и закончилось
		# ложным предупреждением «страница долго грузится».
		if str(json.get("kind", "browser")) != "api":
			panel._begin_page_wait()
		if warn != "" and not panel._site_resend_envelope.is_empty():
			panel._site_resend_envelope = {}
			panel._restore_chat_draft()
			return
		if (not panel._site_resend_envelope.is_empty()
				and bool(panel._site_resend_envelope.get("waiting_open", false))
				and str(panel._site_resend_envelope.get("chat_id", "")) == panel._current_chat_id
				and int(panel._site_resend_envelope.get("expected_generation", -1)) == panel._chat_navigation_generation):
			var resend = panel._site_resend_envelope.duplicate(true)
			panel._site_resend_envelope = {}
			panel._pending_editor_context = resend.get("editor_context", {})
			panel._send_chat_raw(str(resend.get("prompt", "")), true)
		elif not panel._site_resend_envelope.is_empty():
			panel._site_resend_envelope = {}
	elif kind == "new" and panel._view:
		panel._clear_pending_action_state()
		panel._view.clear()
		panel._api_chat_model = (str(json.get("model", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		panel._api_chat_site = (str(json.get("site", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		panel._push_api_switch_target()
		panel._view.set_battle_scope(str(json.get("site_id", "")) == "arena_battle")
		panel._view.add_system(panel._t("chat_created"))
		if str(json.get("kind", "browser")) == "api":
			# Модель выбрана заранее в настройках и закреплена за чатом —
			# напоминание «выберите модель на странице» здесь было бы неверным.
			panel._view.add_hint(panel._t("api_chat_hint") % [str(json.get("site", "")),
				str(json.get("model", ""))])
			panel._enter_chat_ui()
		else:
			panel._view.add_hint(panel._t("pick_model_hint"))  # v48/v49: напоминание выбрать модель — заметным окошком
			panel._enter_chat_ui()
			panel._begin_page_wait()
	elif kind == "delete":
		var deleted_current = str(extra.get("id", "")) == panel._current_chat_id
		if deleted_current:
			panel._current_chat_id = ""
			panel._api_chat_model = ""
			panel._api_chat_site = ""
			panel._push_api_switch_target()
			panel._clear_pending_action_state()
		panel._on_link_hide_loading()
		panel._show_start_ui()
		if bool(extra.get("return_to_list", false)) and panel._start_screen:
			panel._start_screen.show_chats()

static func _fill_chat_list(panel, chats) -> void:
	if panel._chat_select == null or typeof(chats) != TYPE_ARRAY:
		return
	panel._suppress_chat_select = true
	panel._chat_select.clear()
	var sel := -1
	for i in chats.size():
		var c = chats[i]
		if typeof(c) != TYPE_DICTIONARY:
			continue
		var label = str(c.get("title", panel._t("untitled")))
		var sname := str(c.get("site_name", ""))
		if sname != "":
			label += " — " + sname
		if bool(c.get("prompt_stale", false)):
			label += "  " + panel._t("prompt_stale_short")
		panel._chat_select.add_item(label, i)
		panel._chat_select.set_item_metadata(i, str(c.get("id", "")))
		if str(c.get("id", "")) == panel._current_chat_id:
			sel = i
	if sel >= 0:
		panel._chat_select.select(sel)
	panel._suppress_chat_select = false

static func _on_chat_selected(panel, index: int) -> void:
	if panel._suppress_chat_select or panel._chat_select == null:
		return
	var id = str(panel._chat_select.get_item_metadata(index))
	if id == "" or id == panel._current_chat_id:
		return
	if panel._start_screen:
		panel._show_start_ui()
		panel._start_screen.show_loading(panel._t("opening_chat"))
	panel._request_chats("open", {"id": id})

static func _on_chat_new_pressed(panel) -> void:
	# «＋» в чате открывает выбор сайта (нейросети). Важно сначала
	# показать стартовый экран — иначе экран загрузки останется невидимым.
	panel._show_start_ui()
	panel._on_sites_tab_requested()

static func _on_chat_rename_pressed(panel) -> void:
	if panel._current_chat_id == "":
		panel._log_error(panel._t("select_chat_hint"))
		return
	# Вместо модального окна — правка прямо в строке чатов: OptionButton
	# на время подменяется полем ввода. Enter — сохранить, Esc — отмена.
	if panel._chat_select == null or not is_instance_valid(panel._chat_select):
		return
	if panel._rename_edit != null and is_instance_valid(panel._rename_edit):
		# Правка уже открыта — просто возвращаем фокус.
		panel._rename_edit.grab_focus()
		return
	var bar = panel._chat_select.get_parent()
	if bar == null:
		return

	panel._rename_edit = LineEdit.new()
	panel._rename_edit.name = "ChatRenameEdit"
	panel._rename_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._rename_edit.custom_minimum_size.x = 40.0
	if panel._chat_select.selected >= 0:
		panel._rename_edit.text = panel._chat_select.get_item_text(panel._chat_select.selected)
	panel._rename_edit.select_all()
	var T = panel._T()
	if T:
		T.style_input(panel._rename_edit)

	bar.add_child(panel._rename_edit)
	bar.move_child(panel._rename_edit, panel._chat_select.get_index())
	panel._chat_select.visible = false

	panel._rename_edit.text_submitted.connect(func(new_title: String) -> void:
		panel._finish_chat_rename(new_title)
	)
	# focus_exited = клик мимо: считаем это отменой, чтобы поле не зависало.
	panel._rename_edit.focus_exited.connect(func() -> void:
		panel._cancel_chat_rename()
	)
	panel._rename_edit.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
			panel._cancel_chat_rename()
	)
	panel._rename_edit.grab_focus()

static func _finish_chat_rename(panel, new_title: String) -> void:
	var t := new_title.strip_edges()
	panel._close_rename_edit()
	if t == "":
		return
	panel._request_chats("rename", {"id": panel._current_chat_id, "title": t})

static func _cancel_chat_rename(panel) -> void:
	panel._close_rename_edit()

static func _close_rename_edit(panel) -> void:
	# Возвращаем выпадающий список на место и убираем поле ввода.
	if panel._chat_select and is_instance_valid(panel._chat_select):
		panel._chat_select.visible = true
	if panel._rename_edit and is_instance_valid(panel._rename_edit):
		var edit = panel._rename_edit
		panel._rename_edit = null
		edit.queue_free()
	else:
		panel._rename_edit = null

static func _on_chat_delete_pressed(panel) -> void:
	if panel._current_chat_id == "":
		panel._log_error(panel._t("select_chat_first"))
		return
	# Защита от случайных нажатий: подтверждение карточкой в чате.
	# Удаление необратимо, поэтому тон «error», а не «warning».
	var chat_title := ""
	if panel._chat_select and panel._chat_select.selected >= 0:
		chat_title = panel._chat_select.get_item_text(panel._chat_select.selected)
	if panel._view:
		panel._view.add_question_card(
			"delete_chat",
			panel._t("del_title"),
			panel._t("del_text") % chat_title,
			panel._t("del_yes"),
			panel._t("del_no"),
			func(): panel._on_delete_confirmed(),
			func(): pass,
			"error"
		)

static func _on_delete_confirmed(panel) -> void:
	if panel._current_chat_id == "":
		return
	panel._request_chats("delete", {"id": panel._current_chat_id})

static func _on_start_delete_chat(panel, chat_id: String) -> void:
	if chat_id == "":
		return
	panel._request_chats("delete", {"id": chat_id, "return_to_list": true})

static func _render_transcript(panel, entries) -> void:
	if typeof(entries) != TYPE_ARRAY or panel._view == null:
		return
	for e in entries:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		var role := str(e.get("role", ""))
		var text := str(e.get("text", ""))
		if role == "user":
			panel._view.add_user_message(panel._escape_bbcode(text))
		elif role == "agent":
			panel._view.add_agent_message(text)
		else:
			panel._view.add_system(text)

static func _on_editor_script_changed(panel, scr: Script) -> void:
	if panel._hl:
		panel._hl.on_editor_script_changed(scr)

static func _show_start_ui(panel) -> void:
	if panel._view:
		panel._view.set_battle_scope(false)
	if panel._start_screen:
		panel._start_screen.visible = true
		panel._start_screen.show_home()
	if panel.has_node("VBoxContainer"):
		panel.get_node("VBoxContainer").visible = false

static func _enter_chat_ui(panel) -> void:
	if panel._start_screen:
		panel._start_screen.visible = false
	if panel.has_node("VBoxContainer"):
		panel.get_node("VBoxContainer").visible = true
	if panel.input_field:
		panel.input_field.call_deferred("grab_focus")
		panel.input_field.queue_redraw()

static func _apply_chatbar_texts(panel) -> void:
	if panel._bar_btn_new:
		panel._bar_btn_new.tooltip_text = panel._t("tip_new")
	if panel._bar_btn_ren:
		panel._bar_btn_ren.tooltip_text = panel._t("tip_rename")
	if panel._bar_btn_del:
		panel._bar_btn_del.tooltip_text = panel._t("tip_delete")
	if panel._bar_btn_home:
		panel._bar_btn_home.text = panel._t("menu")
		panel._bar_btn_home.tooltip_text = panel._t("tip_menu")
	if panel._bar_btn_settings:
		panel._bar_btn_settings.tooltip_text = panel._t("tip_settings")
	if panel._update_badge and not panel._pending_update_info.is_empty():
		panel._update_badge.tooltip_text = panel._t("update_badge_text") % panel._pending_update_info.get("version", "")

static func _on_language_changed(panel) -> void:
	# Обновляем подписи панели сразу, без перезагрузки плагина.
	panel.name = panel._t("dock_title")
	if panel.send_button and not panel._is_network_busy:
		panel.send_button.text = panel._t("send")
	if panel.input_field:
		panel.input_field.placeholder_text = panel._t("input_placeholder")
	panel._refresh_chat_model_btn()
	if panel.confirm_button:
		panel.confirm_button.text = panel._t("allow")
	if panel.reject_button:
		panel.reject_button.text = panel._t("reject")
	if panel.reinit_button:
		panel.reinit_button.text = panel._t("reinit")
	if panel.action_label and not panel.action_label.visible:
		# Скрытая строка подтверждения тоже переводится: см. пояснение там, где
		# её прячут. Видимую не трогаем — в ней описание конкретного действия.
		panel.action_label.text = panel._t("pending_default")
	if panel._log_errors_button:
		panel._log_errors_button.text = panel._t("log_errors")
	if panel._api_export_button:
		panel._api_export_button.text = panel._t("api_export_btn")
	if panel._safe_rename_check:
		panel._safe_rename_check.text = panel._t("safe_rename_toggle")
		panel._safe_rename_check.tooltip_text = panel._t("safe_rename_tip")
	if panel._safe_rename_button:
		panel._safe_rename_button.text = panel._t("safe_rename_btn")
	if panel._safe_node_rename_button:
		panel._safe_node_rename_button.text = panel._t("safe_node_rename_btn")
	panel._apply_chatbar_texts()
	# Обновляем заголовок вкладки дока.
	var tabs = panel.get_parent() as TabContainer
	if tabs:
		var ti: int = tabs.get_tab_idx_from_control(panel)
		if ti >= 0:
			tabs.set_tab_title(ti, panel._t("dock_title"))

static func _on_sites_tab_requested(panel) -> void:
	# Пользователь нажал «Новый чат» на главном экране — сразу показываем загрузку, список
	# сайтов покажем только после ответа сервера (см. _on_chats_payload).
	panel._pending_view = "sites"
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("sites", {})

static func _on_chats_tab_requested(panel) -> void:
	# Аналогично для кнопки «Загрузиться».
	panel._pending_view = "chats"
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("list", {})

static func _on_start_new_chat(panel, site_id: String) -> void:
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("new", {"site_id": site_id})

static func _on_start_load_chat(panel, chat_id: String) -> void:
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("open", {"id": chat_id})

static func _handle_site_mismatch(panel, site_name: String, prompt: String) -> void:
	panel._pending_chat_prompt = prompt
	panel._site_resend_envelope = {
		"prompt": prompt,
		"editor_context": panel._pending_editor_context.duplicate(true),
		"chat_id": panel._current_chat_id,
		"generation": panel._chat_navigation_generation,
		"waiting_open": false,
	}
	# Карточкой в чате вместо модального окна. ВАЖНО: «Нет» здесь не отмена —
	# запрос всё равно уходит, только без переключения страницы
	# (см. _on_site_switch_no), поэтому колбэк обязателен.
	if panel._view:
		panel._view.add_question_card(
			"site_mismatch",
			panel._t("site_mismatch_title"),
			panel._t("site_mismatch_prefix") + ((" (" + site_name + ")") if site_name != "" else "") + "?",
			panel._t("site_yes"),
			panel._t("site_no"),
			func(): panel._on_site_switch_yes(),
			func(): panel._on_site_switch_no()
		)

static func _on_site_switch_yes(panel) -> void:
	if (panel._site_resend_envelope.is_empty()
			or str(panel._site_resend_envelope.get("chat_id", "")) != panel._current_chat_id
			or int(panel._site_resend_envelope.get("generation", -1)) != panel._chat_navigation_generation):
		panel._log_error("Чат изменился; исходный запрос не был повторно отправлен.")
		panel._site_resend_envelope = {}
		panel._restore_chat_draft()
		return
	if panel._current_chat_id == "":
		var direct = panel._site_resend_envelope.duplicate(true)
		panel._site_resend_envelope = {}
		panel._pending_editor_context = direct.get("editor_context", {})
		panel._send_chat_raw(str(direct.get("prompt", "")), true)
		return
	panel._site_resend_envelope["waiting_open"] = true
	panel._site_resend_envelope["expected_generation"] = panel._chat_navigation_generation + 1
	panel._request_chats("open", {"id": panel._current_chat_id})

static func _on_site_switch_no(panel) -> void:
	if panel._view:
		panel._view.add_system(panel._t("stay_on_page"))
	if (panel._site_resend_envelope.is_empty()
			or str(panel._site_resend_envelope.get("chat_id", "")) != panel._current_chat_id
			or int(panel._site_resend_envelope.get("generation", -1)) != panel._chat_navigation_generation):
		panel._log_error("Чат изменился; исходный запрос не был повторно отправлен.")
		panel._site_resend_envelope = {}
		panel._restore_chat_draft()
		return
	var resend = panel._site_resend_envelope.duplicate(true)
	panel._site_resend_envelope = {}
	panel._pending_editor_context = resend.get("editor_context", {})
	panel._send_chat_raw(str(resend.get("prompt", "")), true)

static func _begin_page_wait(panel) -> void:
	if panel._view:
		panel._view.add_system(panel._t("page_wait"))
	panel._pagewait_left = 40
	if panel._pagewait_timer == null:
		panel._pagewait_timer = Timer.new()
		panel._pagewait_timer.wait_time = 1.0
		panel._pagewait_timer.one_shot = false
		panel.add_child(panel._pagewait_timer)
		panel._pagewait_timer.timeout.connect(panel._on_pagewait_tick)
	panel._pagewait_timer.start()

static func _on_pagewait_tick(panel) -> void:
	if panel._pagewait_left <= 0:
		if panel._pagewait_timer: panel._pagewait_timer.stop()
		if panel._view:
			panel._view.add_system(panel._t("page_slow"))
		return
	panel._pagewait_left -= 1
	if panel._link and panel._link.is_inflight():
		return
	panel._request_chats("status", {})

static func _on_browser_status(panel, json: Dictionary) -> void:
	if panel._pagewait_timer == null or panel._pagewait_timer.is_stopped():
		return
	if bool(json.get("ready", false)):
		panel._pagewait_timer.stop()
		if panel._view:
			panel._view.add_success(panel._t("page_ready"))

static func _on_api_tab_requested(panel) -> void:
	panel._pending_view = "api"
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("api_providers", {})

static func _on_api_settings_save(panel, data: Dictionary) -> void:
	panel._request_chats("api_set", data)

static func _on_api_models_refresh(panel, provider: String, free_only: bool) -> void:
	panel._request_chats("api_models", {"provider": provider, "free_only": free_only})

static func _on_api_models_scan(panel, force: bool) -> void:
	# Обход провайдеров за списками моделей. Ходит только к тем, кого можно
	# спросить без ключа или с уже сохранённым ключом, и только если их числа
	# устарели — решает это сервер (providers.autoscan_targets), потому что
	# только он знает, где лежат ключи и когда список обновлялся.
	panel._request_chats("api_scan", {"force": force})

static func _on_api_test_requested(panel, provider: String, model: String) -> void:
	panel._request_chats("api_test", {"provider": provider, "model": model})

static func _on_start_new_api_chat(panel, provider: String, model: String) -> void:
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(panel._t("connecting"))
	panel._request_chats("new", {"kind": "api", "provider": provider, "model": model})

static func _on_api_payload(panel, kind: String, json: Dictionary) -> void:
	if panel._start_screen == null:
		return
	# Проверка подключения разбирается ПЕРВОЙ, до общей обработки ошибок.
	# Неудачная проверка — это обычный, ожидаемый ответ (ok=false + причина), и
	# уходить по ветке ошибок нельзя: строка «проверяю подключение…» так и
	# осталась бы на экране, а результат проверки не дошёл бы до неё никогда.
	if kind == "api_test":
		if panel._start_screen.has_method("set_api_test_result"):
			panel._start_screen.set_api_test_result(json)
		if json.has("error"):
			panel._log_error(str(json["error"]))
		return
	var failed := json.has("error")
	if failed and kind != "api_scan":
		# Ошибку показываем в статусной строке экрана настроек, а не в чате:
		# пользователь сейчас смотрит именно на форму.
		#
		# ОБХОД ЗА СПИСКАМИ МОДЕЛЕЙ — ИСКЛЮЧЕНИЕ. Его никто не просил: он идёт
		# сам при открытии раздела. Красная строка на весь экран из-за того, что
		# автоматическое действие не удалось (например, сервер старее панели и
		# отвечает 404 на новый маршрут), выглядит как поломка плагина в ответ на
		# простое открытие настроек. Про эту неудачу расскажет сам экран — и
		# только если пользователь просил обход кнопкой (set_api_scan_result).
		panel._notify(str(json["error"]), "error")
	# Настройки применяем ДАЖЕ при ошибке, если сервер их прислал. Отказ
	# провайдера приходит вместе с полным ответом, где уже записано, что список
	# моделей получить не удалось и почему; без этого причина не доехала бы до
	# карточки провайдера, и там осталось бы «список ещё не загружался» — то
	# есть плагин выглядел бы просто ничего не делающим.
	if json.has("providers") and panel._start_screen.has_method("set_api_settings"):
		panel._start_screen.set_api_settings(json)
	if not failed and kind == "api_models" and panel._start_screen.has_method("set_api_models"):
		# models_info — записи {id, free}; models — прежний список строк. Отдаём
		# оба: экран возьмёт записи, если сервер их присылает, и не сломается со
		# старым сервером, где их нет.
		panel._start_screen.set_api_models(str(json.get("provider", "")),
			json.get("models", []), json.get("models_info", []))
	if kind == "api_scan" and panel._start_screen.has_method("set_api_scan_result"):
		# Вызывается и при ошибке: экран обязан узнать, что обход закончился,
		# иначе строка «обновляю списки моделей» останется висеть навсегда.
		panel._start_screen.set_api_scan_result(json)
	if panel._pending_view == "api":
		panel._pending_view = ""
		if panel._start_screen.has_method("show_api"):
			panel._start_screen.show_api()
	if panel._chat_model_pick_wanted and kind == "api_providers":
		# Ответ на нажатие кнопки выбора нейросети в чате. Окно открываем только
		# когда настройки действительно пришли: пустое окно с одной кнопкой
		# «закрыть» — не ответ на нажатие, а причина неудачи уже показана строкой
		# выше. Подпись кнопки («спрашиваю список…») возвращает на место
		# _push_api_switch_target ниже — она вызывается в любом случае.
		panel._chat_model_pick_wanted = false
		if not failed and panel._start_screen.has_method("open_chat_provider_pick"):
			panel._start_screen.open_chat_provider_pick()
	# Экран сам про открытый чат не знает — сообщаем ему модель, чтобы он решил,
	# показывать ли кнопку «продолжить открытый чат на этой модели». Делается
	# здесь, потому что настройки API открываются именно этим ответом.
	panel._push_api_switch_target()

static func _push_api_switch_target(panel) -> void:
	# Модель ОТКРЫТОГО чата по ключу или "" — тогда продолжать нечего и кнопки
	# смены модели не будет. Пустую строку отправляем так же обязательно, как
	# непустую: иначе кнопка осталась бы от прошлого чата и предложила бы
	# сменить модель у браузерного чата, где её вообще нет.
	#
	# Здесь же обновляется подпись кнопки выбора нейросети в самом чате: обе
	# зависят от одного и того же — от модели открытого чата, и разводить их по
	# разным местам значит однажды обновить только одну.
	panel._refresh_chat_model_btn()
	if panel._start_screen == null or not panel._start_screen.has_method("set_api_switch_target"):
		return
	panel._start_screen.set_api_switch_target(panel._api_chat_model)

static func _on_api_chat_model(panel, provider: String, model: String) -> void:
	# Продолжить ОТКРЫТЫЙ чат на другой модели. Отдельный обработчик от
	# _on_start_new_api_chat: тот создаёт новый чат с пустой историей, этот
	# сохраняет переписку.
	panel._request_chats("chat_model", {"provider": provider, "model": model})

static func _notify(panel, text: String, kind: String = "info") -> void:
	# Показываем статус и на стартовом экране, и в чате — пользователь всегда
	# видит, что агент работает, а не завис.
	if panel._start_screen and panel._start_screen.has_method("set_status"):
		panel._start_screen.set_status(text, kind)
	if kind == "status":
		return
	if kind == "error":
		panel._log_error(text)
	elif kind == "success":
		if panel._view: panel._view.add_success(text)
	else:
		if panel._view: panel._view.add_system(text)

static func _on_link_show_loading(panel, text: String) -> void:
	if panel._start_screen and panel._start_screen.has_method("show_loading"):
		panel._start_screen.show_loading(text)

static func _on_link_hide_loading(panel) -> void:
	if panel._start_screen and panel._start_screen.has_method("is_loading") and panel._start_screen.is_loading():
		panel._start_screen.hide_loading()

static func _close_ghost_script_tabs_for_move(panel, old_path: String, is_folder: bool) -> void:
	# v106 (audit 3.2): после перемещения закрываем вкладки старых путей даже
	# если внешних ссылок не нашлось (иначе Ctrl+S в «зомби»-вкладке воскресит
	# старый файл). Для папок сравниваем по префиксу — внутри могли лежать
	# открытые скрипты.
	if old_path.is_empty():
		return
	var se := EditorInterface.get_script_editor()
	if not se:
		return
	var prefix := old_path.trim_suffix("/") + "/"
	for scr in se.get_open_scripts():
		if scr == null:
			continue
		var path_str := str(scr.resource_path)
		var matches := path_str.begins_with(prefix) if is_folder else path_str == old_path
		if matches and not FileAccess.file_exists(path_str):
			panel._close_ghost_script_tab(path_str)

static func _close_ghost_script_tab(panel, target_path: String) -> void:
	# Откат удалил файл с диска, но вкладка в редакторе скриптов осталась —
	# сам Godot её не закрывает, а Ctrl+S в ней «воскресит» файл. Штатного API
	# закрыть вкладку нет, поэтому активируем её и шлём редактору штатный
	# шорткат «Close File» (Ctrl/Cmd+W). Если шорткат переназначен — подскажем
	# закрыть вручную (см. _after_ghost_close).
	if target_path.is_empty() or FileAccess.file_exists(target_path):
		return
	var se := EditorInterface.get_script_editor()
	if not se:
		return
	var dead: Script = null
	for scr in se.get_open_scripts():
		if scr and scr.resource_path == target_path:
			dead = scr
			break
	if dead == null:
		return
	panel._ghost_prev_script = se.get_current_script()
	if panel._ghost_prev_script == dead:
		panel._ghost_prev_script = null
	panel._ghost_close_path = target_path
	EditorInterface.edit_script(dead, -1, 0, false)
	var ev := InputEventKey.new()
	ev.keycode = KEY_W
	ev.command_or_control_autoremap = true
	ev.pressed = true
	panel.Input.parse_input_event(ev)
	var up := InputEventKey.new()
	up.keycode = KEY_W
	up.command_or_control_autoremap = true
	up.pressed = false
	panel.Input.parse_input_event(up)
	panel.get_tree().create_timer(0.4).timeout.connect(panel._after_ghost_close)

static func _after_ghost_close(panel) -> void:
	var se := EditorInterface.get_script_editor()
	if se and panel._ghost_close_path != "":
		for scr in se.get_open_scripts():
			if scr and scr.resource_path == panel._ghost_close_path:
				# Шорткат не сработал — честно просим закрыть вкладку вручную.
				panel._notify(panel._t("ghost_tab_manual") % panel._ghost_close_path, "info")
				break
	if panel._ghost_prev_script:
		EditorInterface.edit_script(panel._ghost_prev_script, -1, 0, false)
	panel._ghost_prev_script = null
	panel._ghost_close_path = ""
