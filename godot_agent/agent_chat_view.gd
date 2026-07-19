@tool
extends Node
# ============================================================================
# AgentChatView — ВЕСЬ визуал чата в одном месте (подготовка к красивому UI).
# Пузыри сообщений как переписка: ИИ-Агент слева, пользователь справа.
# Плавная «печать» по буквам, живой стрим ответа, строка статуса.
# Логика агента (сеть, действия, подтверждения) остаётся в agent_panel.gd.
# ============================================================================

const AGENT_BG := "#26303d"
const AGENT_BORDER := "#3a4a63"
const AGENT_HEADER := "#ffd54f"
const USER_BG := "#1f3320"
const USER_BORDER := "#3a5a3c"
const USER_HEADER := "#a5d6a7"

var chat_log: RichTextLabel = null
var _status_label: Label = null
var _tw_timer: Timer = null
var _tw_buffer: String = ""
var _live_active: bool = false
var _live_start_len: int = 0
var _live_sent: int = 0
var _live_shown: String = ""
var _loc = null                      # скрипт локализации agent_locale.gd


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


func setup(chat_log_in: RichTextLabel, vbox: VBoxContainer) -> void:
	chat_log = chat_log_in
	if _status_label == null:
		_status_label = Label.new()
		_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_status_label.add_theme_color_override("font_color", Color(0.62, 0.74, 0.95))
		_status_label.visible = false
		vbox.add_child(_status_label)
		vbox.move_child(_status_label, chat_log.get_index() + 1)
	if _tw_timer == null:
		_tw_timer = Timer.new()
		_tw_timer.wait_time = 0.02
		_tw_timer.one_shot = false
		add_child(_tw_timer)
		_tw_timer.timeout.connect(_on_tw_tick)


func clear() -> void:
	flush()
	_live_active = false
	_live_sent = 0
	_live_shown = ""
	if chat_log:
		chat_log.text = ""


# --- сообщения-«пузыри» (переписка: агент слева, пользователь справа) ---

func add_user_message(escaped_text: String) -> void:
	flush()
	if chat_log:
		# [right] прижимает сам пузырь к правому краю, но выравнивание
		# наследуется и внутрь ячейки таблицы — весь текст «съезжал» вправо.
		# [p align=left] возвращает тексту сообщения нормальное левое
		# выравнивание ВНУТРИ пузыря, а пузырь остаётся справа.
		chat_log.text += "[right]" + _bubble(_t("you"), USER_HEADER, "[p align=left]" + escaped_text + "[/p]", USER_BG, USER_BORDER) + "[/right]\n"


func add_agent_message(bbcode_text: String) -> void:
	finalize_live_block()
	if chat_log:
		chat_log.text += _bubble(_t("agent_name"), AGENT_HEADER, bbcode_text, AGENT_BG, AGENT_BORDER)


func add_system(text: String) -> void:
	flush()
	if chat_log:
		chat_log.text += "[color=gray]" + text + "[/color]\n"


func add_success(text: String) -> void:
	# Зелёное уведомление об успехе (например, «страница загружена»).
	flush()
	if chat_log:
		chat_log.text += "[color=#7ddc84]" + text + "[/color]\n"


func add_code_preview(escaped_code: String) -> void:
	flush()
	if chat_log:
		chat_log.text += "[bgcolor=#1f2430][color=#8ab4f8] ▸ предлагаемый код [/color][/bgcolor]\n[bgcolor=#2b2b2b][code]" + escaped_code + "[/code][/bgcolor]\n"


# --- строка статуса («модель пишет код…») ---

func show_status(phase: String, elapsed: int, chars: int) -> void:
	if _status_label == null:
		return
	var line := phase
	if elapsed > 0:
		line += " · " + str(elapsed) + " " + _t("unit_sec")
	if chars > 0:
		line += " · " + str(chars) + " " + _t("unit_chars")
	_status_label.text = line
	_status_label.visible = true


func hide_status() -> void:
	if _status_label:
		_status_label.visible = false


func reset_live() -> void:
	flush()
	_live_active = false
	_live_sent = 0
	_live_shown = ""


# --- живой стрим ответа прямо в чат ---

func feed_live_stream(stream: String) -> void:
	if stream == "" or chat_log == null:
		return
	if not _live_active:
		flush()
		_live_start_len = chat_log.text.length()
		_live_active = true
		_live_sent = 0
		_live_shown = ""
		_repaint_live()
	if stream.length() > _live_sent:
		var delta := stream.substr(_live_sent)
		_live_sent = stream.length()
		_append_typed(_escape_bbcode(delta))


func _repaint_live() -> void:
	# Черновик ответа рисуем СРАЗУ в таком же пузыре, как финальное сообщение,
	# поэтому при замене черновика на оформленный ответ текст не «съезжает».
	if chat_log == null:
		return
	var body := _live_shown + "[color=gray]▌[/color]"
	chat_log.text = chat_log.text.substr(0, _live_start_len) \
		+ "\n[table=1][cell bg=" + AGENT_BG + " border=" + AGENT_BORDER \
		+ " padding=10,8,10,8][color=" + AGENT_HEADER + "][b]" + _t("agent_name") + "[/b][/color] [color=gray]" + _t("typing") + "[/color]\n" \
		+ body + "\n[/cell][/table]\n"


func finalize_live_block() -> void:
	# Стрим окончен: черновик убирается, его заменит оформленный пузырь.
	flush()
	if _live_active and chat_log:
		chat_log.text = chat_log.text.substr(0, _live_start_len)
	_live_active = false
	_live_sent = 0
	_live_shown = ""


# --- плавная «печать» по буквам ---

func flush() -> void:
	if _tw_buffer != "" and chat_log:
		if _live_active:
			_live_shown += _tw_buffer
			_tw_buffer = ""
			_repaint_live()
		else:
			chat_log.text += _tw_buffer
	_tw_buffer = ""
	if _tw_timer:
		_tw_timer.stop()


func _append_typed(text: String) -> void:
	_tw_buffer += text
	if _tw_timer and _tw_timer.is_stopped():
		_tw_timer.start()


func _on_tw_tick() -> void:
	if _tw_buffer == "" or chat_log == null:
		if _tw_timer:
			_tw_timer.stop()
		return
	# Скорость адаптивная: чем длиннее остаток, тем крупнее порция.
	var step: int = clamp(int(_tw_buffer.length() / 100.0) + 2, 2, 40)
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
	if _live_active:
		_live_shown += out
		_repaint_live()
	else:
		chat_log.text += out
	if _tw_buffer == "" and _tw_timer:
		_tw_timer.stop()


# --- служебное ---

func _bubble(header: String, header_color: String, body: String, bg: String, border: String) -> String:
	return "\n[table=1][cell bg=" + bg + " border=" + border + " padding=10,8,10,8][color=" + header_color + "][b]" + header + "[/b][/color]\n" + body + "\n[/cell][/table]\n"


func _escape_bbcode(text: String) -> String:
	var result = ""
	for i in range(text.length()):
		var c = text[i]
		if c == "[":
			result += "[lb]"
		elif c == "]":
			result += "[rb]"
		else:
			result += c
	return result
