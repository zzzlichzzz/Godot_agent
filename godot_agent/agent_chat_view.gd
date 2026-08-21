@tool
extends Node
# ============================================================================
# AgentChatView — ВЕСЬ визуал чата в одном месте.
# Пузыри сообщений как переписка: ИИ-Агент слева, пользователь справа.
# Плавная «печать» по буквам, живой стрим ответа, закреплённая строка статуса.
# Логика агента (сеть, действия, подтверждения) остаётся в agent_panel.gd.
# ============================================================================

# Пользователь нажал «откатить» на карточке ответа агента.
# Подтверждение и запрос на сервер делает agent_panel — вид чата не знает
# ни про сеть, ни про историю изменений.
#
# Сигнал несёт АДРЕС записи журнала изменений. Раньше он был пустым, и панель
# могла попросить только «откатить последнее»: кнопка на любом облачке (в том
# числе на ответе без действий) отменяла самое свежее изменение проекта.
signal message_rollback_requested(entry_id: String)

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
# Плашка-напоминание закреплена НАД полем ввода, а не в ленте чата: иначе она
# уезжает вверх с историей, и человек забывает, что действия применяются молча.
var _auto_bar: PanelContainer = null
var _battle_scope_bar: PanelContainer = null
var _battle_scope_active: bool = false
var _root_vbox: VBoxContainer = null
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
	_root_vbox = vbox
	var old_log: RichTextLabel = null
	var stale_scroll: Node = null
	var stale_auto_bar: Node = null
	var stale_battle_scope_bar: Node = null
	for child in vbox.get_children():
		# Проверяем по имени, а не по типу: ChatScroll — ScrollContainer, и из-за
		# лишнего `child is RichTextLabel` старая область никогда не удалялась,
		# из-за чего при переоткрытии панели появлялся второй чат.
		if child.name == "ChatLog" and child is RichTextLabel:
			old_log = child
		elif child.name == "ChatScroll" and child != _scroll:
			stale_scroll = child
		elif child.name == "AutoApproveBar" and child != _auto_bar:
			stale_auto_bar = child
		elif child.name == "BattleScopeBar" and child != _battle_scope_bar:
			stale_battle_scope_bar = child
	if stale_scroll:
		vbox.remove_child(stale_scroll)
		stale_scroll.queue_free()
	# Плашка авто-подтверждения от прошлой сборки панели: иначе после
	# переоткрытия дока их стало бы две, и крестик гасил бы только новую.
	if stale_auto_bar:
		vbox.remove_child(stale_auto_bar)
		stale_auto_bar.queue_free()
	if stale_battle_scope_bar:
		vbox.remove_child(stale_battle_scope_bar)
		stale_battle_scope_bar.queue_free()

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

	# Панель могли собрать заново, пока режим «Разрешить всё» был включён —
	# возвращаем плашку на место над вводом.
	_update_battle_scope_bar()
	_update_auto_bar()


func clear() -> void:
	flush()
	_live_active = false
	_live_agent_card = null
	_live_sent = 0
	_live_streamed = false
	# Новый чат — режим «Разрешить всё» не переносится: иначе он молча
	# продолжил бы применять действия в другом контексте.
	_auto_approve_all = false
	# Плашка над вводом живёт вне списка карточек, поэтому её надо убрать
	# отдельно: очистка _chat_container её не затрагивает.
	_update_auto_bar()
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


func add_agent_message(bbcode_text: String, entry_id: String = "") -> void:
	# entry_id — адрес записи в журнале изменений, если это сообщение сообщает
	# о применённой правке. Пусто (по умолчанию) — обычный ответ без действий:
	# у такой карточки кнопки отката НЕ будет. Раньше её получали все карточки,
	# и нажатие откатывало последнее изменение проекта — не своё.
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
		# Стрим окончен — изменения зафиксированы, откат снова доступен.
		_wire_card_rollback(live, entry_id)
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
	_wire_card_rollback(card, entry_id)
	_scroll_to_bottom()


func _wire_card_rollback(card: AgentMessageCard, entry_id: String) -> void:
	# Кнопка отката на карточке ответа. Сама карточка про откат ничего не
	# знает — она только шлёт сигнал со своим адресом, а вопрос и запрос
	# делает agent_panel.
	#
	# Пустой адрес означает «откатывать нечего»: set_rollback_target скроет
	# кнопку. Это и есть исправление второй жалобы — сообщение без действий
	# больше не предлагает откат.
	if card == null or not is_instance_valid(card):
		return
	card.set_rollback_target(entry_id)
	if entry_id == "":
		return
	if not card.rollback_requested.is_connected(_on_card_rollback_requested):
		card.rollback_requested.connect(_on_card_rollback_requested)


func _on_card_rollback_requested(entry_id: String) -> void:
	message_rollback_requested.emit(entry_id)


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
			# СЕКУНДЫ СЧИТАЕТ САМА СТРОКА СТАТУСА, поэтому здесь -1 («не менять»).
			#
			# Раньше сюда уходило elapsed с сервера, и счётчик скакал 1, 0, 2, 0,
			# 3, 0…: на один и тот же ярлык писали два независимых источника —
			# собственный таймер строки (каждые 0.5 с, растёт) и ответ
			# /chat/progress (раз в секунду). А сервер присылает elapsed НЕ
			# всегда: на фазах «отправляю запрос» и «повтор через N с» поля в
			# снимке нет вовсе, и панель превращала его отсутствие в честный ноль
			# (json.get("elapsed", 0)). Плюс на сервере elapsed отсчитывается от
			# начала ФАЗЫ, а не запроса, поэтому он ещё и прыгал назад при
			# повторах и смене ключа.
			#
			# Часы синхронизируются один раз — при показе строки (show_status
			# ниже ставит _start_time по серверному elapsed). Дальше время идёт
			# ровно, как ему и положено: 1, 2, 3, 4, 5.
			_status_bar.update_status(phase, -1, chars)
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
		# Пока ответ печатается, изменения ещё не зафиксированы на сервере —
		# откат прячем до конца стрима (его вернёт add_agent_message).
		_live_agent_card.set_rollback_available(false)
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


func scroll_to_end(force: bool = false) -> void:
	# Публичная обёртка для agent_panel: раньше панель прокручивала скрытый
	# ChatLog, теперь просит прокрутить реальный список карточек.
	# force=true — когда ответ на действие пользователя обязан попасться на глаза.
	_scroll_to_bottom(force)


func _scroll_to_bottom(force: bool = false) -> void:
	if _scroll == null or not is_instance_valid(_scroll):
		return
	var bar := _scroll.get_v_scroll_bar()
	# Если пользователь сам отлистал вверх — не выдёргиваем у него скролл.
	# force=true только для карточек, которые ЖДУТ ответа (вопросы вроде отката):
	# иначе пользователь нажимает «Откатить» у старого сообщения выше, карточка
	# подтверждения появляется внизу — и он её просто не видит.
	var was_at_bottom := bar == null or _scroll.scroll_vertical >= int(bar.max_value - bar.page - 24)
	if not force and not was_at_bottom:
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


func add_diff_preview(file_path: String, diff_text: String, diff_data: Dictionary = {}) -> DiffPreviewCard:
	if _chat_container == null:
		return null
	# diff_data — разобранный дифф с сервера (что добавилось и что удалилось).
	# Его может не быть: старая сборка сервера или патч, который не сошёлся с
	# диском. Тогда показываем предлагаемый код как раньше.
	var has_diff := diff_data.has("lines") and diff_data["lines"] is Array and not (diff_data["lines"] as Array).is_empty()
	var card := _make_diff_card()
	if card == null:
		add_code_preview(_escape_bbcode(_plain_diff_text(diff_text, diff_data) if has_diff else diff_text))
		return null
	_chat_container.add_child(card)
	if has_diff:
		card.setup_diff(file_path, diff_data)
	else:
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


func add_applied_diff(file_path: String, diff_data: Dictionary) -> DiffPreviewCard:
	# Отчёт об уже применённом изменении (шаг плана). От предпросмотра
	# отличается только отсутствием кнопок: спрашивать нечего, файл уже записан.
	if _chat_container == null:
		return null
	if not (diff_data.has("lines") and diff_data["lines"] is Array and not (diff_data["lines"] as Array).is_empty()):
		return null
	var card := _make_diff_card()
	if card == null:
		return null
	_chat_container.add_child(card)
	card.setup_diff(file_path, diff_data)
	card.set_view_full_texts(_t("diff_show_full"), _t("diff_hide_full"))
	card.mark_applied()
	_scroll_to_bottom()
	return card


func _plain_diff_text(diff_text: String, diff_data: Dictionary) -> String:
	# Запасной вид, когда сцена карточки не загрузилась: обычный текстовый
	# дифф вместо цветного — лучше, чем ничего не показать перед применением.
	var raw = diff_data.get("lines")
	if not (raw is Array):
		return diff_text
	var out := PackedStringArray()
	for entry in raw:
		if entry is Array and (entry as Array).size() >= 4:
			out.append(str(entry[0]) + " " + str(entry[3]))
	return "\n".join(out)


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
	_update_auto_bar()
	if enabled:
		# Разово пишем в ленту — чтобы в истории осталось, с какого момента
		# действия начали применяться без вопросов.
		add_system(_t("auto_approve_on"))
	else:
		add_system(_t("auto_approve_stopped"))


func set_battle_scope(enabled: bool) -> void:
	_battle_scope_active = enabled
	_update_battle_scope_bar()


func _update_battle_scope_bar() -> void:
	if not _battle_scope_active:
		if _battle_scope_bar and is_instance_valid(_battle_scope_bar):
			_battle_scope_bar.queue_free()
		_battle_scope_bar = null
		return
	if _root_vbox == null or not is_instance_valid(_root_vbox):
		return
	if _battle_scope_bar and is_instance_valid(_battle_scope_bar):
		if _battle_scope_bar.get_parent() == _root_vbox:
			return
		_battle_scope_bar.queue_free()
		_battle_scope_bar = null

	var panel := _make_panel("hint")
	panel.name = "BattleScopeBar"
	var T = _T()
	if T:
		panel.add_theme_stylebox_override(
			"panel", T.make_panel_style(T.color("bg_1"), T.alpha("warning", 0.45), 6, 8, 3)
		)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var icon_rect := TextureRect.new()
	var head_icon: Texture2D = null
	if T:
		head_icon = T.first_icon(["StatusWarning", "Info"])
	if head_icon != null:
		icon_rect.texture = head_icon
		icon_rect.custom_minimum_size = Vector2(16, 16)
		icon_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_rect.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		icon_rect.modulate = _color("warning")
	else:
		icon_rect.visible = false

	var label := Label.new()
	label.text = _t("arena_battle_scope_hint")
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	label.add_theme_color_override("font_color", _color("warning"))
	if T:
		label.add_theme_font_size_override("font_size", maxi(T.font_size("Label", 14) - 2, 9))

	row.add_child(icon_rect)
	row.add_child(label)
	panel.add_child(row)
	_root_vbox.add_child(panel)
	_root_vbox.move_child(panel, _input_row_index())
	_battle_scope_bar = panel


func _update_auto_bar() -> void:
	# Плашка живёт ровно столько, сколько включён режим.
	if not _auto_approve_all:
		if _auto_bar and is_instance_valid(_auto_bar):
			_auto_bar.queue_free()
		_auto_bar = null
		return
	if _root_vbox == null or not is_instance_valid(_root_vbox):
		return
	if _auto_bar and is_instance_valid(_auto_bar):
		# Плашка от прошлой сборки панели: узел ещё жив, но висит в старом
		# дереве и пользователю не виден — пересоздаём в актуальном.
		if _auto_bar.get_parent() == _root_vbox:
			return
		_auto_bar.queue_free()
		_auto_bar = null

	var panel := _make_panel("hint")
	panel.name = "AutoApproveBar"
	var T = _T()
	if T:
		# Отступы меньше, чем у карточек в ленте: это узкая полоска-напоминание
		# над вводом, а не сообщение — она не должна отбирать место у чата.
		panel.add_theme_stylebox_override(
			"panel", T.make_panel_style(T.color("bg_1"), T.alpha("warning", 0.45), 6, 8, 3)
		)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var icon_rect := TextureRect.new()
	var head_icon: Texture2D = null
	if T:
		head_icon = T.first_icon(["StatusWarning", "AutoKey", "Play"])
	if head_icon != null:
		icon_rect.texture = head_icon
		icon_rect.custom_minimum_size = Vector2(16, 16)
		icon_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_rect.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		icon_rect.modulate = _color("warning")
	else:
		icon_rect.visible = false

	var label := Label.new()
	label.text = _t("auto_approve_bar")
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	label.add_theme_color_override("font_color", _color("warning"))
	if T:
		label.add_theme_font_size_override("font_size", maxi(T.font_size("Label", 14) - 2, 9))

	# Крестик: выключить режим в любой момент, не дожидаясь конца задачи.
	var off_btn := Button.new()
	off_btn.name = "AutoApproveOffButton"
	off_btn.tooltip_text = _t("auto_approve_off")
	off_btn.custom_minimum_size = Vector2(20, 20)
	off_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	off_btn.focus_mode = Control.FOCUS_NONE
	if T:
		T.style_icon_button(off_btn, ["Close", "Remove"], "✕", "error")
	else:
		off_btn.flat = true
		off_btn.text = "✕"
	off_btn.pressed.connect(func() -> void: set_auto_approve(false))

	row.add_child(icon_rect)
	row.add_child(label)
	row.add_child(off_btn)
	panel.add_child(row)
	_root_vbox.add_child(panel)
	# Место плашки — прямо над строкой ввода (HBoxContainer с InputField).
	_root_vbox.move_child(panel, _input_row_index())
	_auto_bar = panel


func _input_row_index() -> int:
	# Индекс строки ввода в корневом VBox. Дерево панели собирается кодом
	# (plugin_universal.gd) и из .tscn, поэтому ищем по имени узла, а не по
	# фиксированному номеру: порядок детей между сборками может отличаться.
	if _root_vbox == null or not is_instance_valid(_root_vbox):
		return 0
	var input_row := _root_vbox.get_node_or_null("HBoxContainer")
	if input_row:
		return input_row.get_index()
	# Запасной вариант: перед строкой статуса, если ввод почему-то не найден.
	if _status_bar and is_instance_valid(_status_bar) and _status_bar.get_parent() == _root_vbox:
		return _status_bar.get_index() + 1
	return maxi(_root_vbox.get_child_count() - 1, 0)


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
		tone: String = "warning", icon_names: Array = []) -> PanelContainer:
	if _chat_container == null:
		return null

	# Тот же вопрос ещё висит без ответа — убираем старую карточку.
	if _question_cards.has(key):
		var old = _question_cards[key]
		if old != null and is_instance_valid(old):
			old.queue_free()
		_question_cards.erase(key)

	# Тон "ask" — обычный вопрос без тревоги: карточка выглядит как сообщение
	# агента, без жёлтой рамки и знака «внимание». Раньше даже рутинный откат
	# показывался как предупреждение и выглядел пугающе.
	var is_ask := tone == "ask"
	var panel: PanelContainer
	if is_ask:
		panel = _make_panel("agent")
	else:
		panel = _make_panel("hint" if tone == "warning" else "error")
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)

	# Цвет заголовка: у обычного вопроса — как у текста, а не сигнальный.
	var title_color := _color("text") if is_ask else _color(tone)

	# Шапка: иконка + заголовок вопроса.
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 6)
	var icon_rect := TextureRect.new()
	var head_icon: Texture2D = null
	if not icon_names.is_empty():
		var T = _T()
		if T:
			head_icon = T.first_icon(icon_names)
	elif not is_ask:
		# Знак «внимание»/«ошибка» — только для настоящих предупреждений.
		head_icon = _icon(&"StatusWarning" if tone == "warning" else &"StatusError")
	if head_icon != null:
		icon_rect.texture = head_icon
		icon_rect.custom_minimum_size = Vector2(16, 16)
		icon_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_rect.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		icon_rect.modulate = title_color
	else:
		icon_rect.visible = false
	var title_label := Label.new()
	title_label.text = title
	title_label.add_theme_color_override("font_color", title_color)
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(icon_rect)
	head.add_child(title_label)

	var label := Label.new()
	label.text = description
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", _color("dim") if is_ask else _color("text"))
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# Пустое описание не должно оставлять пустую строку в карточке.
	label.visible = description != ""

	var hbox := HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 10)

	var yes_btn := Button.new()
	yes_btn.text = yes_label
	yes_btn.custom_minimum_size = Vector2(100, 28)
	yes_btn.flat = true
	yes_btn.icon = _icon(&"StatusSuccess")
	yes_btn.add_theme_color_override("font_color", _color("accent") if is_ask else _color(tone))
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
	# Вопрос без ответа блокирует работу, поэтому скролл принудительный:
	# карточку видно сразу, даже если пользователь читал историю выше.
	_scroll_to_bottom(true)
	return panel
