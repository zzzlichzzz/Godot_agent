@tool
extends RefCounted
## Read-only panel controls. The server owns the action; decisions send only its ticket.

const BADGE := "ReadConsentBadge"
const DockTheme = preload("agent_theme.gd")

static func revoke(view) -> void:
	if view._root_vbox != null:
		var badge = view._root_vbox.get_node_or_null(BADGE)
		if badge != null:
			view._root_vbox.remove_child(badge)
			badge.queue_free()
	view.set_meta("read_grant", "")
	view.set_meta("requested_grant", "")

static func finish(panel, success: bool) -> void:
	var view = panel._view
	var owner := str(view.get_meta("requested_grant", ""))
	view.set_meta("requested_grant", "")
	if not success or owner == "" or owner != panel._current_chat_id or view._root_vbox == null:
		return
	revoke(view)
	var badge := Button.new()
	badge.name = BADGE
	badge.text = "Чтение в этом чате разрешено · Отменить"
	badge.icon = DockTheme.first_icon(["Unlock", "FileAccess"])
	badge.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	badge.pressed.connect(func(): revoke(view))
	view._root_vbox.add_child(badge)
	view._root_vbox.move_child(badge, view._input_row_index())
	view.set_meta("read_grant", owner)

static func offer(panel, ticket: Dictionary) -> void:
	var view = panel._view
	var owner := str(ticket.get("chat_id", ""))
	if owner == "" or owner != panel._current_chat_id or view._chat_container == null:
		view.add_warning("Чат изменился: данные не отправлены.")
		return
	var paused := bool(ticket.get("pause", false))
	if view.get_meta("read_grant", "") == owner and not paused:
		decide(panel, ticket, true, false)
		return
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", DockTheme.panel_style("hint"))
	var stack := VBoxContainer.new()
	card.add_child(stack)
	var label := Label.new()
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.text = ("Продолжить серию чтений?" if paused else "Разрешить чтение и отправку в этот чат?")
	stack.add_child(label)
	var details := Label.new()
	details.name = "RequestedAction"
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.text = JSON.stringify(ticket.get("action", {}), "  ")
	var mono := DockTheme.mono_font()
	if mono:
		details.add_theme_font_override("font", mono)
	details.add_theme_color_override("font_color", DockTheme.color("dim"))
	stack.add_child(details)
	var buttons := HFlowContainer.new()
	buttons.name = "Choices"
	stack.add_child(buttons)
	# Вопрос уже называет разрешение; короткие ответы помещаются и в узком доке.
	for choice in [["Один раз", true, false], ["Всегда в этом чате", true, true], ["Отказать", false, false]]:
		var button := Button.new()
		button.text = choice[0]
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
	panel._view.set_meta("requested_grant", panel._current_chat_id if always else "")
	panel._set_ui_busy(true)
	var body := {"request_id": ticket.id, "chat_id": ticket.chat_id, "approved": approved}
	var error = panel.http_request.request(AgentServer.URL_CHAT + "/read/decision", panel._json_headers(),
		HTTPClient.METHOD_POST, panel._policy_json(body))
	if error != OK:
		panel._view.set_meta("requested_grant", "")
		panel._set_ui_busy(false)
		panel._log_error("Не удалось отправить решение о чтении.")
	return error == OK
