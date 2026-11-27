@tool
extends RefCounted
## Read-only panel controls. The server owns the action; decisions send only its ticket.

const DockTheme = preload("agent_theme.gd")
const Lang = preload("agent_locale.gd")

static func _words(ru: String, en: String) -> String:
	return en if Lang.get_lang() == "en" else ru

static func _operation(kind: String) -> String:
	match kind:
		"read_file": return _words("Содержимое файлов", "File contents")
		"read_function": return _words("Функции скрипта", "Script functions")
		"list_scene": return _words("Структура сцены", "Scene structure")
		"list_files": return _words("Дерево файлов", "File tree")
		"search_project", "ask_librarian": return _words("Поиск по проекту", "Project search")
		"gather_context": return _words("Контекст проекта", "Project context")
		_: return _words("Анализ символа", "Symbol analysis")

static func _summary(action: Dictionary) -> String:
	# Display only: the server keeps the exact ticket, including scopes and limits.
	for key in ["paths", "path", "scene", "subdir", "dir", "query", "sections", "old_name"]:
		if action.has(key):
			var value = action[key]
			var items: Array = value if value is Array else [value]
			var lines := PackedStringArray()
			for item in items:
				lines.append(JSON.stringify(item).trim_prefix('"').trim_suffix('"'))
			return "\n".join(lines)
	if action.get("action") == "list_files": return "res://"
	return str(action.get("action", ""))

static func finish(panel, success: bool) -> void:
	var view = panel._view
	var owner := str(view.get_meta("requested_grant", ""))
	view.set_meta("requested_grant", "")
	if not success or owner == "" or owner != panel._current_chat_id or view._root_vbox == null:
		return
	view.set_auto_approve(true)

static func offer(panel, ticket: Dictionary) -> void:
	var view = panel._view
	var owner := str(ticket.get("chat_id", ""))
	if owner == "" or owner != panel._current_chat_id or view._chat_container == null:
		view.add_warning("Чат изменился: данные не отправлены.")
		return
	var paused := bool(ticket.get("pause", false))
	if view.is_auto_approve() and not paused:
		decide(panel, ticket, true, false)
		return
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", DockTheme.panel_style("hint"))
	var stack := VBoxContainer.new()
	card.add_child(stack)
	stack.add_theme_constant_override("separation", DockTheme.px(5))
	var label := Label.new()
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.text = (_words("Продолжить серию чтений?", "Continue reading?") if paused else _words("Отправить данные в чат?", "Share data with this chat?"))
	stack.add_child(label)
	var action: Dictionary = ticket.get("action", {})
	var target := Label.new()
	target.name = "ReadTarget"
	target.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	target.text = _summary(action)
	var mono := DockTheme.mono_font()
	if mono: target.add_theme_font_override("font", mono)
	var well := PanelContainer.new()
	well.add_theme_stylebox_override("panel", DockTheme.panel_style("sunken"))
	var scope := VBoxContainer.new()
	var operation := Label.new()
	operation.text = _operation(str(action.get("action", "")))
	operation.add_theme_color_override("font_color", DockTheme.color("dim"))
	operation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	well.add_child(scope)
	scope.add_child(operation)
	scope.add_child(target)
	stack.add_child(well)
	var toggle := Button.new()
	toggle.name = "ReadParameters"
	toggle.toggle_mode = true
	toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	toggle.icon = DockTheme.first_icon(["GuiTreeArrowRight"])
	toggle.text = _words("Параметры запроса", "Request details")
	DockTheme.style_button(toggle, "dim")
	stack.add_child(toggle)
	var details := Label.new()
	details.name = "RequestedAction"
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.text = JSON.stringify(action, "  ")
	if mono:
		details.add_theme_font_override("font", mono)
	details.add_theme_color_override("font_color", DockTheme.color("dim"))
	stack.add_child(details)
	details.hide()
	toggle.toggled.connect(func(open: bool):
		details.visible = open
		toggle.icon = DockTheme.first_icon(["GuiTreeArrowDown" if open else "GuiTreeArrowRight"]))
	var buttons := HFlowContainer.new()
	buttons.name = "Choices"
	stack.add_child(buttons)
	# Вопрос уже называет разрешение; короткие ответы помещаются и в узком доке.
	for choice in [[_words("Разрешить", "Allow"), true, false], [Lang.t("allow_all"), true, true], [_words("Запретить", "Deny"), false, false]]:
		var button := Button.new()
		button.text = choice[0]
		if choice[2]: button.tooltip_text = Lang.t("allow_all_tip")
		buttons.add_child(button)
		button.pressed.connect(func():
			if decide(panel, ticket, choice[1], choice[2]):
				card.queue_free())
	view._chat_container.add_child(card)
	view.scroll_to_end(true)

static func decide(panel, ticket: Dictionary, approved: bool, always: bool) -> bool:
	if panel._is_network_busy or panel._current_chat_id != ticket.get("chat_id"):
		return false
	panel._pending_request_kind = "read_decision"
	panel._active_chat_turn = Crypto.new().generate_random_bytes(16).hex_encode()
	panel._view.set_meta("requested_grant", panel._current_chat_id if always else "")
	panel._set_ui_busy(true)
	var body := {"request_id": ticket.id, "chat_id": ticket.chat_id, "approved": approved, "turn_id": panel._active_chat_turn}
	var error = panel.http_request.request(AgentServer.URL_CHAT + "/read/decision", panel._json_headers(),
		HTTPClient.METHOD_POST, panel._policy_json(body))
	if error != OK:
		panel._active_chat_turn = ""
		panel._view.set_meta("requested_grant", "")
		panel._set_ui_busy(false)
		panel._log_error("Не удалось отправить решение о чтении.")
	return error == OK
