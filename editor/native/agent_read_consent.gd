@tool
extends RefCounted
## Read-only panel controls. The server owns the action; decisions send only its ticket.

const BADGE := "ReadConsentBadge"

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
	var card := VBoxContainer.new()
	var label := Label.new()
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.text = ("Продолжить серию чтений?" if paused else "Разрешить чтение и отправку в этот чат?")
	label.text += "\n" + JSON.stringify(ticket.get("action", {}), "  ")
	card.add_child(label)
	var buttons := HFlowContainer.new()
	card.add_child(buttons)
	for choice in ["Разрешить один раз", "Разрешить всегда в этом чате", "Отказать"]:
		var button := Button.new()
		button.text = choice
		buttons.add_child(button)
		button.pressed.connect(func():
			if decide(panel, ticket, choice != "Отказать", choice == "Разрешить всегда в этом чате"):
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
