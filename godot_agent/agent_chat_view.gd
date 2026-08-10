@tool
extends Node
# ============================================================================
# AgentChatView — ВЕСЬ визуал чата в одном месте.
# Пузыри сообщений как переписка: ИИ-Агент слева, пользователь справа.
# Плавная «печать» по буквам, живой стрим ответа, закреплённая строка статуса.
# Логика агента (сеть, действия, подтверждения) остаётся в agent_panel.gd.
# ============================================================================

# Цвета, иконки и стили — единый модуль agent_theme.gd (см. _T()).
var _theme_script = null

# Кэшированные сцены карточек (путь считается от расположения скрипта,
# чтобы аддон работал из любого места под res://addons/…).
var _card_scene_cache := {}


func _T():
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _color(key: String) -> Color:
	var T = _T()
	if T == null:
		return Color.WHITE
	return T.color(key)


func _icon(icon_name: String) -> Texture2D:
	var T = _T()
	if T == null:
		return null
	return T.icon(icon_name)


func _load_card_scene(file_name: String) -> PackedScene:
	if _card_scene_cache.has(file_name):
		return _card_scene_cache[file_name]
	var sc := get_script() as Script
	var packed: PackedScene = null
	if sc:
		var path := sc.resource_path.get_base_dir() + "/" + file_name
		if FileAccess.file_exists(path):
			packed = load(path) as PackedScene
	if packed == null:
		push_warning("AgentChatView: не удалось загрузить сцену карточки " + file_name)
	_card_scene_cache[file_name] = packed
	return packed


func _instantiate_card(file_name: String) -> Control:
	# Раньше при неудачной загрузке сцены код делал XxxCard.new(): у такого узла
	# нет дочерних нод из сцены, и первый же @onready падал с null.
	# Теперь честно возвращаем null, а вызывающий код показывает простой текст.
	var packed := _load_card_scene(file_name)
	if packed == null:
		return null
	return packed.instantiate() as Control


func _make_user_card() -> UserMessageCard:
	return _instantiate_card("UserMessageCard.tscn") as UserMessageCard


func _make_agent_card() -> AgentMessageCard:
	return _instantiate_card("AgentMessageCard.tscn") as AgentMessageCard


func _make_plan_card() -> PlanChecklistCard:
	return _instantiate_card("PlanChecklistCard.tscn") as PlanChecklistCard


func _make_diff_card() -> DiffPreviewCard:
	return _instantiate_card("DiffPreviewCard.tscn") as DiffPreviewCard


var _chat_container: VBoxContainer = null
var _scroll: ScrollContainer = null
var _status_bar: AgentStatusBar = null
var _status_label: Label = null
var _tw_timer: Timer = null
var _tw_buffer: String = ""
var _live_active: bool = false
var _live_agent_card: AgentMessageCard = null
var _live_sent: int = 0
var _live_streamed: bool = false
# «Разрешить всё»: подтверждения применяются без запроса до отключения.
var _auto_approve_all: bool = false
var _auto_banner: PanelContainer = null
var _loc = null

func _locale():
	if _loc == null:
		var sc := get_script() as Script
		if sc:
			var lp := sc.resource_path.get_base_dir() + "/agent_locale.gd"
			if FileAccess.file_exists(lp):
				_loc = load(lp)
	return _loc


func _t(key: String) -> String:
	var l = _locale()
	if l:
		return l.t(key)
	return key


func setup(vbox: VBoxContainer) -> void:
	# Старый чат-лог (RichTextLabel) прячем, но НЕ удаляем: логика agent_panel.gd
	# продолжает писать в него (chat_log.text += …) — всё бесшовно работает.
	var old_log: RichTextLabel = null
	var stale_scroll: Node = null
	for child in vbox.get_children():
		# Проверяем по имени, а не по типу: ChatScroll — ScrollContainer, и из-за
		# лишнего `child is RichTextLabel` старая область никогда не удалялась,
		# из-за чего при переоткрытии панели появлялся второй чат.
		if child.name == "ChatLog" and child is RichTextLabel:
			old_log = child
		elif child.name == "ChatScroll" and child != _scroll:
			stale_scroll = child
	if stale_scroll:
		vbox.remove_child(stale_scroll)
		stale_scroll.queue_free()

	var insert_index := 0
	if old_log:
		old_log.visible = false
		insert_index = old_log.get_index()

	# Создаём скролл-область карточек на месте старого лога.
	if _chat_container == null or not is_instance_valid(_chat_container):
		_scroll = ScrollContainer.new()
		_scroll.name = "ChatScroll"
		_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
		_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		var cards_vbox := VBoxContainer.new()
		cards_vbox.name = "Cards"
		cards_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		cards_vbox.add_theme_constant_override("separation", 8)
		_scroll.add_child(cards_vbox)
		vbox.add_child(_scroll)
		vbox.move_child(_scroll, insert_index)
		_chat_container = cards_vbox

	# Строка статуса закреплена под списком карточек и не уезжает при скролле.
	if _status_bar == null or not is_instance_valid(_status_bar):
		_status_bar = _instantiate_card("AgentStatusBar.tscn") as AgentStatusBar
		if _status_bar:
			vbox.add_child(_status_bar)
			vbox.move_child(_status_bar, insert_index + 1)
	if _status_bar == null and (_status_label == null or not is_instance_valid(_status_label)):
		_status_label = Label.new()
		_status_label.name = "ChatStatusLabel"
		_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_status_label.add_theme_color_override("font_color", _color("text"))
		_status_label.visible = false
		vbox.add_child(_status_label)
		vbox.move_child(_status_label, insert_index + 1)

	if _tw_timer == null or not is_instance_valid(_tw_timer):
		_tw_timer = Timer.new()
		_tw_timer.name = "TypewriterTimer"
		_tw_timer.wait_time = 0.02
		_tw_timer.one_shot = false
		add_child(_tw_timer)
		_tw_timer.timeout.connect(_on_tw_tick)


func clear() -> void:
	flush()
	_live_active = false
	_live_agent_card = null
	_live_sent = 0
	_live_streamed = false
	# Новый чат — режим «Разрешить всё» не переносится: иначе он молча
	# продолжил бы применять действия в другом контексте.
	_auto_approve_all = false
	_auto_banner = null
	# Карточки-вопросы удаляются вместе с содержимым чата — иначе в словаре
	# остались бы ссылки на освобождённые узлы.
	_question_cards.clear()
	if _chat_container:
		for child in _chat_container.get_children():
			_chat_container.remove_child(child)
			child.queue_free()


# --- общий каркас простых карточек ---

func _make_panel(variant: String) -> PanelContainer:
	var panel := PanelContainer.new()
	var T = _T()
	if T:
		panel.add_theme_stylebox_override("panel", T.panel_style(variant))
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return panel


func _make_note_label(text: String, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return label


# --- сообщения-«пузыри» (переписка: агент слева, пользователь справа) ---

func add_user_message(escaped_text: String) -> void:
	flush()
	if _chat_container == null:
		return
	var card := _make_user_card()
	if card == null:
		_chat_container.add_child(_make_note_label(escaped_text, _color("success")))
		_scroll_to_bottom()
		return
	_chat_container.add_child(card)
	card.setup(escaped_text)
	_scroll_to_bottom()


func add_agent_message(bbcode_text: String) -> void:
	if _chat_container == null:
		return
	flush()
	# Если ответ уже «печатался» в живой карточке — переиспользуем её,
	# иначе один и тот же текст показывался в чате дважды.
	if _live_streamed and _live_agent_card != null and is_instance_valid(_live_agent_card):
		var live := _live_agent_card
		_reset_live_state()
		live.set_status("")
		live.setup(bbcode_text)
		_scroll_to_bottom()
		return
	finalize_live_block()
	var card := _make_agent_card()
	if card == null:
		_chat_container.add_child(_make_note_label(bbcode_text, _color("text")))
		_scroll_to_bottom()
		return
	_chat_container.add_child(card)
	card.setup(bbcode_text)
	_scroll_to_bottom()


func add_system(text: String) -> void:
	flush()
	if _chat_container:
		_chat_container.add_child(_make_note_label(text, _color("dim")))
		_scroll_to_bottom()


func add_hint(text: String) -> void:
	flush()
	if _chat_container == null:
		return
	var panel := _make_panel("hint")
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)

	var title := Label.new()
	title.text = _t("hint_title")
	title.add_theme_color_override("font_color", _color("warning"))
	var T = _T()
	if T:
		title.add_theme_font_size_override("font_size", T.font_size("Label", 14))

	var content := Label.new()
	content.text = text
	content.add_theme_color_override("font_color", _color("text"))
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	vbox.add_child(title)
	vbox.add_child(content)
	panel.add_child(vbox)
	_chat_container.add_child(panel)
	_scroll_to_bottom()


func add_success(text: String) -> void:
	flush()
	if _chat_container:
		_chat_container.add_child(_make_note_label(text, _color("success")))
		_scroll_to_bottom()


func add_error(text: String) -> void:
	# Ошибки раньше уходили в скрытый ChatLog (agent_panel._log_error писал в
	# RichTextLabel, который setup() прячет) — пользователь не видел их вообще.
	# Теперь это заметная карточка с иконкой ошибки прямо в ленте чата.
	flush()
	if _chat_container == null:
		return
	var panel := _make_panel("error")
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var icon_rect := TextureRect.new()
	var err_icon := _icon("StatusError")
	if err_icon != null:
		icon_rect.texture = err_icon
		icon_rect.custom_minimum_size = Vector2(16, 16)
		icon_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_rect.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
		icon_rect.modulate = _color("error")
	else:
		icon_rect.visible = false

	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", _color("error"))
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	row.add_child(icon_rect)
	row.add_child(label)
	panel.add_child(row)
	_chat_container.add_child(panel)
	_scroll_to_bottom()


func add_warning(text: String) -> void:
	# Предупреждения (принудительный откат, остановленный план) — жёлтым,
	# чтобы отличались и от обычного статуса, и от ошибки.
	flush()
	if _chat_container:
		_chat_container.add_child(_make_note_label(text, _color("warning")))
		_scroll_to_bottom()


func add_code_preview(escaped_code: String) -> void:
	flush()
	if _chat_container == null:
		return
	var panel := _make_panel("code")
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)

	var title := Label.new()
	title.text = "▸ " + _t("code_preview_title")
	title.add_theme_color_override("font_color", _color("code_text"))

	var code := RichTextLabel.new()
	code.text = escaped_code
	# Моно-шрифт и цвет кода — из общего модуля темы. autowrap выключен
	# намеренно: код не должен переноситься по словам.
	var T2 = _T()
	if T2:
		T2.style_rich_text(code, true)
	code.autowrap_mode = TextServer.AUTOWRAP_OFF
	code.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	code.add_theme_color_override("default_color", _color("code_text"))

	vbox.add_child(title)
	vbox.add_child(code)
	panel.add_child(vbox)
	_chat_container.add_child(panel)
	_scroll_to_bottom()


# --- строка статуса («модель пишет код…») ---

func show_status(phase: String, elapsed: int, chars: int) -> void:
	if _status_bar and is_instance_valid(_status_bar):
		if _status_bar.visible:
			_status_bar.update_status(phase, elapsed, chars)
		else:
			_status_bar.show_status(phase, elapsed, chars)
		return
	if _status_label == null or not is_instance_valid(_status_label):
		return
	var line := phase
	if elapsed > 0:
		line += " · " + str(elapsed) + " " + _t("unit_sec")
	if chars > 0:
		line += " · " + str(chars) + " " + _t("unit_chars")
	_status_label.text = line
	_status_label.visible = true


func hide_status() -> void:
	if _status_bar and is_instance_valid(_status_bar):
		_status_bar.hide_status()
	if _status_label and is_instance_valid(_status_label):
		_status_label.visible = false


func reset_live() -> void:
	flush()
	_reset_live_state()


func _reset_live_state() -> void:
	_live_active = false
	_live_agent_card = null
	_live_sent = 0
	_live_streamed = false


# --- живой стрим ответа прямо в чат ---

func feed_live_stream(stream: String) -> void:
	if stream == "" or _chat_container == null:
		return
	if not _live_active:
		flush()
		_live_active = true
		_live_sent = 0
		_live_streamed = false
		_live_agent_card = _make_agent_card()
		if _live_agent_card == null:
			_live_active = false
			return
		_chat_container.add_child(_live_agent_card)
		_live_agent_card.setup("")
		_live_agent_card.set_status(_t("typing"))
		_scroll_to_bottom()
	if stream.length() > _live_sent:
		var delta := stream.substr(_live_sent)
		_live_sent = stream.length()
		_live_streamed = true
		# Через буфер печати: раньше текст вставлялся мгновенно, а таймер
		# «плавной печати» вообще никогда не запускался.
		_append_typed(_escape_bbcode(delta))


func finalize_live_block() -> void:
	# Стрим окончен: убираем статус "печатает"
	flush()
	if _live_active and _live_agent_card and is_instance_valid(_live_agent_card):
		_live_agent_card.set_status("")
	_reset_live_state()


# --- плавная «печать» по буквам ---

func flush() -> void:
	if _tw_buffer != "":
		if _live_agent_card and is_instance_valid(_live_agent_card):
			_live_agent_card.append_text(_tw_buffer)
		_tw_buffer = ""
	if _tw_timer and is_instance_valid(_tw_timer):
		_tw_timer.stop()


func _append_typed(text: String) -> void:
	if text == "":
		return
	_tw_buffer += text
	if _tw_timer and is_instance_valid(_tw_timer) and _tw_timer.is_stopped():
		_tw_timer.start()


func _on_tw_tick() -> void:
	if _tw_buffer == "":
		if _tw_timer:
			_tw_timer.stop()
		return
	if _live_agent_card == null or not is_instance_valid(_live_agent_card):
		_tw_buffer = ""
		if _tw_timer:
			_tw_timer.stop()
		return
	# Скорость адаптивная: чем длиннее остаток, тем крупнее порция.
	var step: int = clampi(int(_tw_buffer.length() / 100.0) + 2, 2, 40)
	var out := ""
	while step > 0 and _tw_buffer != "":
		var c := _tw_buffer[0]
		if c == "[":
			var close := _tw_buffer.find("]")
			if close == -1:
				out += _tw_buffer
				_tw_buffer = ""
				break
			out += _tw_buffer.substr(0, close + 1)
			_tw_buffer = _tw_buffer.substr(close + 1)
		else:
			out += c
			_tw_buffer = _tw_buffer.substr(1)
		step -= 1
	_live_agent_card.append_text(out)
	_scroll_to_bottom()
	if _tw_buffer == "" and _tw_timer:
		_tw_timer.stop()


func scroll_to_end() -> void:
	# Публичная обёртка для agent_panel: раньше панель прокручивала скрытый
	# ChatLog, теперь просит прокрутить реальный список карточек.
	_scroll_to_bottom()


func _scroll_to_bottom() -> void:
	if _scroll == null or not is_instance_valid(_scroll):
		return
	var bar := _scroll.get_v_scroll_bar()
	# Если пользователь сам отлистал вверх — не выдёргиваем у него скролл.
	var was_at_bottom := bar == null or _scroll.scroll_vertical >= int(bar.max_value - bar.page - 24)
	if not was_at_bottom:
		return
	# Двух кадров достаточно, чтобы контейнер пересчитал размеры карточек.
	await get_tree().process_frame
	await get_tree().process_frame
	if _scroll == null or not is_instance_valid(_scroll):
		return
	var vbar := _scroll.get_v_scroll_bar()
	if vbar:
		_scroll.scroll_vertical = int(vbar.max_value)


func _escape_bbcode(text: String) -> String:
	var T = _T()
	if T:
		return T.escape_bbcode(text)
	return text


func _color_to_hex(color: Color) -> String:
	return "#" + color.to_html(false)


# --- Специализированные визуальные блоки ---

func show_status_bar(phase: String, elapsed: int = 0, chars: int = 0) -> void:
	# Статус-бар один и закреплён в setup(): раньше на каждый вызов создавалась
	# новая копия, а queue_free старой ещё не успевал сработать — Godot давал
	# новому узлу имя AgentStatusBar2, и update/hide больше его не находили.
	show_status(phase, elapsed, chars)


func update_status_bar(phase: String = "", elapsed: int = -1, chars: int = -1) -> void:
	if _status_bar and is_instance_valid(_status_bar):
		_status_bar.update_status(phase, elapsed, chars)


func hide_status_bar() -> void:
	hide_status()


func add_plan_checklist(plan_title: String, steps: Array) -> PlanChecklistCard:
	if _chat_container == null:
		return null
	var card := _make_plan_card()
	if card == null:
		_chat_container.add_child(_make_note_label(plan_title, _color("accent")))
		_scroll_to_bottom()
		return null
	_chat_container.add_child(card)
	card.setup(plan_title, steps)
	_scroll_to_bottom()
	return card


func update_plan_step(card: PlanChecklistCard, step_index: int, status: String) -> void:
	if card and is_instance_valid(card):
		card.update_step(step_index, status)


func add_diff_preview(file_path: String, diff_text: String) -> DiffPreviewCard:
	if _chat_container == null:
		return null
	var card := _make_diff_card()
	if card == null:
		add_code_preview(_escape_bbcode(diff_text))
		return null
	_chat_container.add_child(card)
	card.setup(file_path, diff_text)
	card.set_allow_all_texts(_t("allow_all"), _t("allow_all_tip"))
	card.set_view_full_texts(_t("diff_show_full"), _t("diff_hide_full"))
	# Сигналы карточки agent_panel подключает уже после возврата, поэтому
	# и авто-применение, и «Разрешить всё» уходят в отложенный вызов.
	if not card.apply_all_requested.is_connected(_on_diff_allow_all):
		card.apply_all_requested.connect(_on_diff_allow_all.bind(card))
	if _auto_approve_all:
		card.mark_auto_approved(_t("auto_approved") % file_path)
		card.call_deferred("emit_signal", "diff_applied", file_path)
	_scroll_to_bottom()
	return card


func _on_diff_allow_all(card: DiffPreviewCard) -> void:
	set_auto_approve(true)
	if card and is_instance_valid(card):
		card.diff_applied.emit(card.get_file_path())


func add_tool_call(tool_name: String, params: Dictionary) -> void:
	# Добавляем tool call к последней карточке агента
	if _chat_container == null:
		return
	for i in range(_chat_container.get_child_count() - 1, -1, -1):
		var child := _chat_container.get_child(i) as AgentMessageCard
		if child:
			child.add_tool_call(tool_name, params)
			return


# --- авто-подтверждение («Разрешить всё») ---

func is_auto_approve() -> bool:
	return _auto_approve_all


func set_auto_approve(enabled: bool) -> void:
	if _auto_approve_all == enabled:
		return
	_auto_approve_all = enabled
	if enabled:
		_add_auto_approve_banner()
	else:
		if _auto_banner and is_instance_valid(_auto_banner):
			_auto_banner.queue_free()
		_auto_banner = null
		add_system(_t("auto_approve_stopped"))


func _add_auto_approve_banner() -> void:
	if _chat_container == null:
		return
	if _auto_banner and is_instance_valid(_auto_banner):
		_auto_banner.queue_free()
	var panel := _make_panel("hint")
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)

	var label := Label.new()
	label.text = _t("auto_approve_on")
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_color_override("font_color", _color("warning"))

	var off_btn := Button.new()
	off_btn.text = _t("auto_approve_off")
	off_btn.flat = true
	off_btn.custom_minimum_size = Vector2(0, 26)
	off_btn.add_theme_color_override("font_color", _color("error"))
	off_btn.add_theme_color_override("font_hover_color", Color.WHITE)
	off_btn.pressed.connect(func() -> void: set_auto_approve(false))

	row.add_child(label)
	row.add_child(off_btn)
	panel.add_child(row)
	_chat_container.add_child(panel)
	_auto_banner = panel
	_scroll_to_bottom()


func add_confirmation_card(description: String, confirm_callback: Callable, reject_callback: Callable) -> PanelContainer:
	if _chat_container == null:
		return null
	# Режим «Разрешить всё»: не спрашиваем, только показываем что применили.
	if _auto_approve_all:
		_chat_container.add_child(_make_note_label(_t("auto_approved") % description, _color("dim")))
		_scroll_to_bottom()
		confirm_callback.call_deferred()
		return null
	var panel := _make_panel("agent")
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 8)

	var label := Label.new()
	label.text = description
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", _color("text"))
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var hbox := HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 10)

	var confirm_btn := Button.new()
	confirm_btn.text = _t("allow")
	confirm_btn.custom_minimum_size = Vector2(100, 28)
	confirm_btn.flat = true
	confirm_btn.icon = _icon(&"StatusSuccess")
	confirm_btn.add_theme_color_override("font_color", _color("success"))
	confirm_btn.add_theme_color_override("font_hover_color", Color.WHITE)

	var reject_btn := Button.new()
	reject_btn.text = _t("reject")
	reject_btn.custom_minimum_size = Vector2(100, 28)
	reject_btn.flat = true
	reject_btn.icon = _icon(&"StatusError")
	reject_btn.add_theme_color_override("font_color", _color("error"))
	reject_btn.add_theme_color_override("font_hover_color", Color.WHITE)

	var all_btn := Button.new()
	all_btn.text = _t("allow_all")
	all_btn.tooltip_text = _t("allow_all_tip")
	all_btn.custom_minimum_size = Vector2(0, 28)
	all_btn.flat = true
	all_btn.add_theme_color_override("font_color", _color("warning"))
	all_btn.add_theme_color_override("font_hover_color", Color.WHITE)

	var lock := func() -> void:
		confirm_btn.disabled = true
		reject_btn.disabled = true
		all_btn.disabled = true

	# Кнопки блокируются сразу, чтобы двойной клик не отправил ответ дважды.
	confirm_btn.pressed.connect(func() -> void:
		lock.call()
		confirm_callback.call()
		panel.queue_free()
	)
	reject_btn.pressed.connect(func() -> void:
		lock.call()
		reject_callback.call()
		panel.queue_free()
	)
	all_btn.pressed.connect(func() -> void:
		lock.call()
		set_auto_approve(true)
		confirm_callback.call()
		panel.queue_free()
	)

	hbox.add_child(confirm_btn)
	hbox.add_child(reject_btn)
	hbox.add_child(all_btn)
	vbox.add_child(label)
	vbox.add_child(hbox)
	panel.add_child(vbox)

	_chat_container.add_child(panel)
	_scroll_to_bottom()
	return panel


# --- карточки-вопросы вместо модальных окон ---
#
# Раньше откат, удаление чата, смена сайта и перезапуск проекта показывались
# нативными ConfirmationDialog поверх редактора. Теперь это карточки в ленте
# чата — тот же вид, что у подтверждений действий агента, и вопрос остаётся
# в истории рядом с тем, к чему относится.
#
# ВАЖНО: режим «Разрешить всё» сюда НЕ распространяется. Он про действия
# агента с файлами; молча откатывать изменения или удалять чат нельзя.

# Активные карточки-вопросы по ключу: повторный показ того же вопроса
# заменяет предыдущую карточку, а не копит их стопкой.
var _question_cards := {}


func add_question_card(key: String, title: String, description: String,
		yes_label: String, no_label: String,
		yes_callback: Callable, no_callback: Callable,
		tone: String = "warning") -> PanelContainer:
	if _chat_container == null:
		return null

	# Тот же вопрос ещё висит без ответа — убираем старую карточку.
	if _question_cards.has(key):
		var old = _question_cards[key]
		if old != null and is_instance_valid(old):
			old.queue_free()
		_question_cards.erase(key)

	var panel := _make_panel("hint" if tone == "warning" else "error")
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)

	# Шапка: иконка + заголовок вопроса.
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	var icon_rect := TextureRect.new()
	var head_icon := _icon(&"StatusWarning" if tone == "warning" else &"StatusError")
	if head_icon != null:
		icon_rect.texture = head_icon
		icon_rect.custom_minimum_size = Vector2(16, 16)
		icon_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_rect.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		icon_rect.modulate = _color(tone)
	else:
		icon_rect.visible = false
	var title_label := Label.new()
	title_label.text = title
	title_label.add_theme_color_override("font_color", _color(tone))
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(icon_rect)
	head.add_child(title_label)

	var label := Label.new()
	label.text = description
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", _color("text"))
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var hbox := HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 10)

	var yes_btn := Button.new()
	yes_btn.text = yes_label
	yes_btn.custom_minimum_size = Vector2(100, 28)
	yes_btn.flat = true
	yes_btn.icon = _icon(&"StatusSuccess")
	yes_btn.add_theme_color_override("font_color", _color(tone))
	yes_btn.add_theme_color_override("font_hover_color", Color.WHITE)

	var no_btn := Button.new()
	no_btn.text = no_label
	no_btn.custom_minimum_size = Vector2(100, 28)
	no_btn.flat = true
	no_btn.icon = _icon(&"StatusError")
	no_btn.add_theme_color_override("font_color", _color("dim"))
	no_btn.add_theme_color_override("font_hover_color", Color.WHITE)

	# Блокируем сразу: двойной клик не должен отправить ответ дважды.
	var finish := func(cb: Callable) -> void:
		yes_btn.disabled = true
		no_btn.disabled = true
		_question_cards.erase(key)
		if cb.is_valid():
			cb.call()
		panel.queue_free()

	yes_btn.pressed.connect(func() -> void: finish.call(yes_callback))
	no_btn.pressed.connect(func() -> void: finish.call(no_callback))

	hbox.add_child(yes_btn)
	hbox.add_child(no_btn)
	vbox.add_child(head)
	vbox.add_child(label)
	vbox.add_child(hbox)
	panel.add_child(vbox)

	_chat_container.add_child(panel)
	_question_cards[key] = panel
	_scroll_to_bottom()
	return panel
