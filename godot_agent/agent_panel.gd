@tool
extends Control

# --- части (вынесены «пилой» split_gd) ---
const AgentPanelPart1 = preload("agent_panel_part1.gd")
const AgentPanelPart2 = preload("agent_panel_part2.gd")
const AgentPanelPart3 = preload("agent_panel_part3.gd")
const AgentPanelPart4 = preload("agent_panel_part4.gd")
const AgentPanelPart5 = preload("agent_panel_part5.gd")

@onready var chat_log: RichTextLabel = $VBoxContainer/ChatLog
@onready var input_field: TextEdit = $VBoxContainer/HBoxContainer/InputField
@onready var send_button: Button = $VBoxContainer/HBoxContainer/SendButton
@onready var http_request: HTTPRequest = $HTTPRequest

# Элементы подтверждения действий ИИ
@onready var pending_action_box: HBoxContainer = $VBoxContainer/PendingActionBox
@onready var action_label: Label = $VBoxContainer/PendingActionBox/ActionLabel
@onready var confirm_button: Button = $VBoxContainer/PendingActionBox/ConfirmButton
@onready var reject_button: Button = $VBoxContainer/PendingActionBox/RejectButton

# Кнопка выбора нейросети для открытого чата (под полем ввода) и ящик редких
# инструментов, который панель переносит в окно настроек — см.
# _on_settings_pressed и пояснение в plugin_universal.gd.
@onready var chat_model_btn: Button = $VBoxContainer/ChatModelBtn
@onready var advanced_box: VBoxContainer = $VBoxContainer/AdvancedBox
@onready var reinit_button: Button = $VBoxContainer/AdvancedBox/ReinitButton

# Адрес сервера, токен и заголовки живут в AgentServer — единственном месте,
# где плагин знает про локальный сервер. Здесь только имена маршрутов.
const CHAT_URL = AgentServer.URL_CHAT
const INIT_URL = AgentServer.URL_INIT
const CONFIRM_URL = AgentServer.URL_CHAT_CONFIRM_ACTION
const EDITOR_ACTION_RESULT_URL = AgentServer.URL_CHAT_EDITOR_ACTION_RESULT
const RUNTIME_RESULT_URL = AgentServer.URL_CHAT_RUNTIME_INSPECT_RESULT
const RUNTIME_CHECK_RESULT_URL = AgentServer.URL_CHAT_RUNTIME_CHECK_RESULT
const ROLLBACK_URL = AgentServer.URL_CHAT_ROLLBACK
const ROLLBACK_PREVIEW_URL = AgentServer.URL_CHAT_ROLLBACK_PREVIEW
const CHECK_LOG_URL = AgentServer.URL_PROJECT_CHECK_LOG
const SEND_LOG_URL = AgentServer.URL_PROJECT_SEND_LOG_ERRORS
const PROGRESS_URL = AgentServer.URL_CHAT_PROGRESS
const API_EXPORT_URL = AgentServer.URL_PROJECT_UPDATE_API_CACHE
const API_CACHE_STATUS_URL = AgentServer.URL_PROJECT_API_CACHE_STATUS
const PLAN_STEP_URL = AgentServer.URL_CHAT_PLAN_STEP
const PLAN_STOP_URL = AgentServer.URL_CHAT_PLAN_STOP
const CHAT_STOP_URL = AgentServer.URL_CHAT_STOP
const PLAN_ROLLBACK_CHAIN_URL = AgentServer.URL_CHAT_PLAN_ROLLBACK_CHAIN
const LIVE_INPUT_URL = AgentServer.URL_CHAT_LIVE_INPUT
const REFACTOR_FILE_PREVIEW_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_PREVIEW
const REFACTOR_FILE_APPLY_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_APPLY
const REFACTOR_FILE_POST_MOVE_SYNC_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_POST_MOVE_SYNC
const REFACTOR_NODE_PREVIEW_URL = AgentServer.URL_SCENE_REFACTOR_NODE_PREVIEW
const REFACTOR_NODE_APPLY_URL = AgentServer.URL_SCENE_REFACTOR_NODE_APPLY

var _pending_request_kind: String = "chat"
var _is_network_busy: bool = false
# Есть ли сейчас неотвеченное подтверждение. РАНЬШЕ этим флагом служило
# pending_action_box.visible, из-за чего старая панель кнопок рисовалась над
# строкой ввода одновременно с карточкой в чате. Теперь состояние живёт в
# переменной, а сама панель не показывается никогда (см. _set_pending_action).
var _pending_action_active: bool = false
# Список мест переименования с галочками (Этап 4.3). Пуст, если действие не
# связано с переименованием или список не пришёл.
var _pending_rename_usages: Array = []
var _rename_excluded: Dictionary = {}

# Plan-режим (цепочка действий): активен, когда пользователь подтвердил план
# и панель сама выполняет шаги через PLAN_STEP_URL по одному.
var _plan_active: bool = false
var _plan_chain_id: String = ""
var _plan_total: int = 0
var _plan_index: int = 0
var _plan_stop_button: Button = null
var _stop_button: Button = null
var _plan_rollback_chain_id: String = ""
var _plan_rollback_force_next: bool = false

# Визуальная карточка-чеклист активного плана (в чате).
var _active_plan_card: PlanChecklistCard = null

# Запоминаем детали последнего примененного WRITE-действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""
var _last_pending_action_paths: PackedStringArray = PackedStringArray()
var _editor_plugin: EditorPlugin = null
# Шлюз мутаций (ЗАДАЧА 4): единственное место, где плагин пишет в файлы и
# где решается, попадёт ли правка в историю отмены Godot. Создаётся раньше
# исполнителей и передаётся им: иначе каждый исполнитель снова решал бы это
# у себя, а решения разошлись бы (именно это и было первопричиной).
var _mutation_gate = null
var _scene_executor = null


# split_gd: тело — agent_panel_part1.gd
func handle_context_ask(what: String, paths: PackedStringArray) -> void:
	AgentPanelPart1.handle_context_ask(self, what, paths)
var _pending_scene_action: Dictionary = {}
var _pending_scene_expected_hash: String = ""
var _pending_scene_semantic_hash: String = ""
var _pending_scene_finalize_body: Dictionary = {}
var _project_settings_executor = null
var _pending_project_settings_action: Dictionary = {}
var _pending_project_settings_expected_hash: String = ""
var _pending_project_settings_semantic_hash: String = ""
var _pending_project_settings_finalize_body: Dictionary = {}
var _resource_executor = null
var _pending_resource_action: Dictionary = {}
var _pending_resource_expected_hash: String = ""
var _pending_resource_semantic_hash: String = ""
var _pending_resource_dependency_fingerprint: String = ""
var _pending_resource_finalize_body: Dictionary = {}
var _runtime_debugger = null
var _runtime_status: Dictionary = {"enabled": false, "protocol": 1, "sessions": []}
var _pending_runtime_request: Dictionary = {}
var _runtime_timeout_timer: Timer = null
var _pending_runtime_check: Dictionary = {}
var _runtime_check_session_id: int = -1
var _runtime_check_run_id: String = ""
var _pending_runtime_check_result_body: Dictionary = {}
var _scenes_to_reopen: PackedStringArray = PackedStringArray()  # v49: сцены, закрытые перед записью

# Версия истории отмены сцены на момент последнего известного сохранения
# (ЗАДАЧА 1). Позволяет отличить «сцену сохранили» от «в сцене есть правки»
# без несуществующего в скриптах is_scene_dirty().
var _scene_saved_versions: Dictionary = {}

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
# Коды, после которых повтор бессмысленен: сервер отклонил запрос окончательно.
# Проверяется ОДИН раз для всех видов, а не в каждой копии отдельно.
const FINALIZE_TERMINAL_CODES := [400, 403, 409, 410, 413]

var _finalize_retries: Dictionary = {}
var _finalize_retrying: Dictionary = {}

# Если сервер ответил, что для отката нужно подтверждение (файл менялся
# после действия агента) — следующее нажатие кнопки отката отправит force.
var _rollback_force_next: bool = false
# Адрес записи журнала для текущего отката (см. _on_message_rollback_requested).
# Пусто — откат «последнего изменения» из дополнительных настроек.
var _rollback_entry_id: String = ""
# Для какого именно адреса взведён force. Раньше флаг был общим, и повторное
# нажатие у ДРУГОГО сообщения молча откатывало с force, минуя подтверждение.
var _rollback_force_entry_id: String = ""

# Закрытие «вкладки-призрака» после отката, удалившего файл с диска.
var _ghost_close_path: String = ""
var _ghost_prev_script: Script = null

# Канал «Ошибки запуска игры»: кнопка создаётся кодом (без правки .tscn),
# а флаг означает, что текущее подтверждение — это отправка отчёта модели.
var _log_errors_button: Button = null
var _api_export_button: Button = null
const SAFE_RENAME_SETTING_FILE := "user://godot_agent_safe_rename.txt"
var _safe_rename_enabled: bool = true
# Галочка «переименовывать недоказанные ссылки». По умолчанию СТОИТ: значит
# ссылки, которые сервер не смог доказать, тоже переименовываются, но каждая
# попадает в отчёт с причиной. Снятие возвращает прежнее строгое поведение,
# где одна недоказанная ссылка отменяет всё переименование.
# Хранится в user:// рядом с прочими переключателями, поэтому переживает
# перезапуск редактора.
const RENAME_UNVERIFIED_SETTING_FILE := "user://godot_agent_rename_unverified.txt"
var _rename_unverified_enabled: bool = true
var _rename_unverified_check: CheckBox = null
# Выбор режима отказа для переименований. По умолчанию strict: он отказывает при
# любой недоказанной ссылке и при динамической ссылке по строке. probable эти
# блокировки снимает, поэтому включать его можно только осознанно — поэтому он
# НЕ входит в дефолт, даже когда галочка недоказанных ссылок стоит.
const RENAME_MODE_SETTING_FILE := "user://godot_agent_rename_mode.txt"
var _rename_mode: String = "strict"
var _rename_mode_option: OptionButton = null
var _safe_rename_check: CheckBox = null
var _safe_rename_button: Button = null
var _safe_rename_dialog: ConfirmationDialog = null
var _safe_rename_old_edit: LineEdit = null
var _safe_rename_new_edit: LineEdit = null
var _safe_rename_refs_check: CheckBox = null
var _safe_rename_status_label: Label = null
var _safe_rename_file_dialog: FileDialog = null
var _safe_rename_prepared: Dictionary = {}
var _safe_node_rename_button: Button = null
var _safe_node_rename_dialog: ConfirmationDialog = null
var _safe_node_rename_scene_edit: LineEdit = null
var _safe_node_rename_node_edit: LineEdit = null
var _safe_node_rename_new_edit: LineEdit = null
var _safe_node_rename_status_label: Label = null
var _safe_node_rename_scene_dialog: FileDialog = null
var _safe_node_rename_prepared: Dictionary = {}
var _pending_log_send: bool = false
# Explicit access policy for project/addon edits. allow_addons is durable;
# allow_self_edit is ephemeral and resets to false on every panel load.
const POLICY_SETTING_FILE := "user://godot_agent_policy.txt"
var _allow_addons: bool = false
var _allow_self_edit: bool = false
var _allow_addons_check: CheckBox = null
var _allow_self_edit_check: CheckBox = null
var _policy_warning_label: Label = null
var _policy_confirmation_dialog: ConfirmationDialog = null
var _policy_confirmation_pending: String = ""
var _policy_previous_allow_addons: bool = false
var _policy_previous_allow_self_edit: bool = false


# Автопроверка актуальности кэша API при старте панели: сервер (с браузером внутри) может подняться не сразу, поэтому при неудаче повторяем с нарастающей задержкой, а не молча сдаёмся после первой неудачи.
var _api_cache_check_attempts: int = 0
var _api_cache_check_timer: Timer = null

# Автопроверка лога после закрытия игры (переход is_playing_scene: true→false).
var _play_watch_timer: Timer = null
var _was_playing: bool = false
var _auto_check: bool = false

var _hl = null  # подсистема подсветки (agent_highlight.gd)
var _start_screen: Control = null
var _pending_chat_prompt: String = ""
var _pending_editor_context: Dictionary = {}
var _editor_context_script = null
var _site_resend_envelope: Dictionary = {}
var _chat_navigation_generation: int = 0
var _chat_drafts: Dictionary = {}
var _guard_timer: Timer = null       # таймер-охранник кнопок (вместо await — переживает перезагрузку скрипта)
var _guard_until_msec: int = 0        # до какого момента кнопки подтверждения заблокированы


# Живая трансляция: пока идёт запрос, отдельный HTTPRequest раз в секунду
# опрашивает /chat/progress и показывает статус + хвост ответа модели.

# v88.11: живой ввод — текст из поля панели зеркалируется в поле ввода сайта
# по мере набора (тротлинг-таймер + отдельный HTTPRequest, настройка в
# «Расширенных»; сервер вставляет текст без отправки).
const LIVE_INPUT_SETTING_FILE := "user://godot_agent_live_input.txt"
var _live_timer: Timer = null
var _live_toggle: CheckBox = null
var _live_enabled: bool = true
var _live_dirty: bool = false
var _live_inflight: bool = false
var _live_seq: int = 0
var _live_last_sent: String = ""
var _live_force_send: bool = false
var _progress_timer: Timer = null
var _progress_inflight: bool = false
# Весь визуал чата (пузыри, печать, стрим, статус) — в agent_chat_view.gd.
var _view: Node = null
# --- Чаты: список, создание, переименование, удаление ---
var _link: Node = null               # связь с сервером — весь транспорт и автозапуск в agent_server_link.gd

# Параметры последнего post_move_sync: короткий канал один на все запросы,
# поэтому обработчик должен знать, ЧЕЙ это ответ.
var _sync_old: String = ""
var _sync_new: String = ""
var _sync_is_folder: bool = false
var _pagewait_timer: Timer = null
var _pagewait_left: int = 0
var _pending_view: String = ""
var _loc = null                      # скрипт локализации agent_locale.gd
var _bar_btn_new: Button = null
var _bar_btn_ren: Button = null
var _bar_btn_del: Button = null
var _bar_btn_home: Button = null
var _chat_select: OptionButton = null
var _rename_edit: LineEdit = null  # inline-правка названия в строке чатов
var _current_chat_id: String = ""
# Модель ОТКРЫТОГО чата по ключу или "" — если открыт браузерный чат либо не
# открыт никакой. Нужна ровно для одного: показать на экране настроек кнопку
# «продолжить открытый чат на этой модели» и не показывать её там, где менять
# нечего. Отдельное поле, а не чтение записи чата: панель и так получает model в
# ответах /chats/open, /chats/new и /chats/model.
var _api_chat_model: String = ""
# Подпись открытого чата «провайдер · модель» — её присылает сервер готовой
# (site в ответах /chats/open, /chats/new, /chats/model; это же site_name записи
# чата). Панель её НЕ склеивает сама: имя провайдера знает только сервер, и
# вторая сборка той же строки разошлась бы с подписью чата в списке.
var _api_chat_site: String = ""
# Ждём ответ со списком провайдеров, чтобы открыть окно выбора нейросети.
var _chat_model_pick_wanted: bool = false
var _suppress_chat_select: bool = false

# ---------------------------------------------------------------------------
# Экспериментальные настройки (MiniLich) — заготовка нейросети для Godot.
# Это то, что осталось от старой версии, скрыто из UI. НЕ УДАЛЯТЬ: на этом
# завязаны внутренние механизмы и серверные запросы, оставить на будущее!
# ---------------------------------------------------------------------------
var _bar_btn_settings: Button = null
var _settings_dialog: AcceptDialog = null
var _settings_exp_header: Label = null
# Заголовок раздела редких инструментов в том же окне («Дополнительно»).
var _settings_adv_header: Label = null
var _minilich_check: CheckBox = null
var _minilich_status_label: Label = null
var _minilich_set_pending: bool = false  # true пока ответ на minilich_set не пришёл — не даём устаревшему minilich_status затирать галочку
# v58: кнопка «Обучение модели» + живая консоль прогресса обучения.
var _minilich_train_check: CheckBox = null
var _minilich_train_warn: Label = null
var _minilich_repos_edit: LineEdit = null
var _minilich_github_btn: Button = null
var _minilich_github_label: Label = null

# Подсистема проверки и установки обновлений
var _updater = null
var _update_badge: Button = null
var _update_dialog: AcceptDialog = null
var _update_check_btn: Button = null
var _update_check_status_label: Label = null
var _update_dialog_version_label: Label = null
var _update_dialog_changelog: RichTextLabel = null
var _update_dialog_progress: ProgressBar = null
var _update_dialog_status: Label = null
var _update_dialog_btn_auto: Button = null
var _update_dialog_btn_github: Button = null
var _update_dialog_btn_restart: Button = null
var _pending_update_info: Dictionary = {}


# split_gd: тело — agent_panel_part1.gd
func set_editor_plugin(plugin: EditorPlugin) -> void:
	AgentPanelPart1.set_editor_plugin(self, plugin)


# split_gd: тело — agent_panel_part1.gd
func set_runtime_debugger(debugger) -> void:
	AgentPanelPart1.set_runtime_debugger(self, debugger)


# split_gd: тело — agent_panel_part1.gd
func _on_runtime_status_changed(status: Dictionary) -> void:
	AgentPanelPart1._on_runtime_status_changed(self, status)


# split_gd: тело — agent_panel_part1.gd
func _start_runtime_inspect(envelope: Dictionary) -> void:
	AgentPanelPart1._start_runtime_inspect(self, envelope)


# split_gd: тело — agent_panel_part1.gd
func _on_runtime_inspect_completed(result: Dictionary) -> void:
	AgentPanelPart1._on_runtime_inspect_completed(self, result)


# split_gd: тело — agent_panel_part1.gd
func _on_runtime_inspect_timeout() -> void:
	AgentPanelPart1._on_runtime_inspect_timeout(self)


# split_gd: тело — agent_panel_part1.gd
func _send_runtime_result(status: String, snapshot) -> void:
	AgentPanelPart1._send_runtime_result(self, status, snapshot)


# split_gd: тело — agent_panel_part1.gd
func _start_runtime_check(envelope: Dictionary) -> void:
	AgentPanelPart1._start_runtime_check(self, envelope)


func _exit_tree() -> void:
	if not _pending_runtime_check.is_empty():
		if _runtime_debugger:
			_runtime_debugger.cancel_pending("cancelled")


# split_gd: тело — agent_panel_part1.gd
func _execute_bound_runtime_check(_envelope: Dictionary) -> void:
	AgentPanelPart1._execute_bound_runtime_check(self, _envelope)


# split_gd: тело — agent_panel_part1.gd
func _on_runtime_check_completed(result: Dictionary) -> void:
	AgentPanelPart1._on_runtime_check_completed(self, result)


# split_gd: тело — agent_panel_part1.gd
func _send_runtime_check_result(status: String, result_value) -> void:
	AgentPanelPart1._send_runtime_check_result(self, status, result_value)


# split_gd: тело — agent_panel_part1.gd
func _send_pending_runtime_check_result() -> void:
	AgentPanelPart1._send_pending_runtime_check_result(self)


# split_gd: тело — agent_panel_part1.gd
func _clear_runtime_check_state() -> void:
	AgentPanelPart1._clear_runtime_check_state(self)


# split_gd: тело — agent_panel_part1.gd
func _locale():
	AgentPanelPart1._locale(self)


# split_gd: тело — agent_panel_part1.gd
func _t(key: String) -> String:
	return AgentPanelPart1._t(self, key)


# split_gd: тело — agent_panel_part1.gd
func _json_headers() -> PackedStringArray:
	return AgentPanelPart1._json_headers(self)


var _theme_script = null


# split_gd: тело — agent_panel_part1.gd
func _T():
	AgentPanelPart1._T(self)


# split_gd: тело — agent_panel_part1.gd
func _apply_panel_theme() -> void:
	AgentPanelPart1._apply_panel_theme(self)


func _ready() -> void:
	_load_policy_settings()
	_ensure_script_autoreload_setting()
	if _editor_plugin and _editor_plugin.has_method("_ensure_fs_dock_connected"):
		_editor_plugin.call("_ensure_fs_dock_connected")
	# ChatLog остаётся в дереве (его прячет agent_chat_view.setup), но больше
	# ничего в него не пишется: все сообщения идут карточками через _view.
	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	chat_log.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chat_log.scroll_following = true
	if pending_action_box:
		pending_action_box.visible = false
	# Подтверждения показываются ТОЛЬКО карточкой в чате. Старая панель
	# PendingActionBox остаётся в дереве (её кнопки — приёмники сигналов и
	# охранник _guard_confirm_buttons), но больше никогда не показывается:
	# состояние «есть неотвеченное действие» держит _pending_action_active.
	if action_label:
		action_label.visible = false
		# Надпись из .tscn русская. Панель эту строку никогда не показывает
		# (подтверждения идут карточкой в чате), но держать в дереве русский
		# текст при английском языке нельзя: узел живой, и любая будущая правка,
		# которая снова его покажет, покажет и русское. Ставим из словаря сразу.
		action_label.text = _t("pending_default")
	if confirm_button:
		confirm_button.visible = false
	if reject_button:
		reject_button.visible = false
	if not send_button.pressed.is_connected(_on_send_pressed):
		send_button.pressed.connect(_on_send_pressed)
	if not http_request.request_completed.is_connected(_on_request_completed):
		http_request.request_completed.connect(_on_request_completed)
	if confirm_button and not confirm_button.pressed.is_connected(_on_confirm_pressed):
		confirm_button.pressed.connect(_on_confirm_pressed)
	if reject_button and not reject_button.pressed.is_connected(_on_reject_pressed):
		reject_button.pressed.connect(_on_reject_pressed)
	if reinit_button and not reinit_button.pressed.is_connected(_on_reinit_pressed):
		reinit_button.pressed.connect(_on_reinit_pressed)
	if chat_model_btn and not chat_model_btn.pressed.is_connected(_on_chat_model_pressed):
		chat_model_btn.pressed.connect(_on_chat_model_pressed)
	if advanced_box and advanced_box.get_parent() == $VBoxContainer:
		# Ящик редких инструментов не показывается в чате никогда: панель
		# переносит его в окно настроек при первом открытии настроек. До того он
		# просто лежит скрытым — кнопки в нём создаются и подключаются здесь.
		#
		# Проверка родителя обязательна: _ready() выполняется заново после
		# перезагрузки скрипта аддона, а ящик к этому моменту может уже стоять в
		# окне настроек — и тогда «спрятать» означало бы стереть весь раздел из
		# настроек до перезапуска редактора.
		advanced_box.visible = false
	if advanced_box and _log_errors_button == null:
		_log_errors_button = Button.new()
		_log_errors_button.text = _t("log_errors")
		advanced_box.add_child(_log_errors_button)
		_log_errors_button.pressed.connect(_on_check_log_pressed)
	if advanced_box and _api_export_button == null:
		_api_export_button = Button.new()
		_api_export_button.text = _t("api_export_btn")
		advanced_box.add_child(_api_export_button)
		_api_export_button.pressed.connect(_on_export_api_pressed)
	if advanced_box and _safe_rename_button == null:
		_safe_rename_button = Button.new()
		_safe_rename_button.text = _t("safe_rename_btn")
		_safe_rename_button.visible = false  # Функция вынесена в чекбокс настроек, ручной диалог доступен через Project -> Tools
		advanced_box.add_child(_safe_rename_button)
		_safe_rename_button.pressed.connect(_on_safe_rename_pressed)
	if advanced_box and _safe_node_rename_button == null:
		_safe_node_rename_button = Button.new()
		_safe_node_rename_button.text = _t("safe_node_rename_btn")
		_safe_node_rename_button.visible = false  # Функция вынесена в чекбокс настроек, ручной диалог доступен через Project -> Tools
		advanced_box.add_child(_safe_node_rename_button)
		_safe_node_rename_button.pressed.connect(_on_safe_node_rename_pressed)
	call_deferred("_check_api_cache_freshness")
	_ensure_file_logging_enabled()
	if _play_watch_timer == null:
		_play_watch_timer = Timer.new()
		_play_watch_timer.wait_time = 1.0
		_play_watch_timer.one_shot = false
		add_child(_play_watch_timer)
		_play_watch_timer.timeout.connect(_on_play_watch_tick)
		_play_watch_timer.start()
	if _guard_timer == null:
		_guard_timer = Timer.new()
		_guard_timer.one_shot = true
		add_child(_guard_timer)
		_guard_timer.timeout.connect(_on_guard_timeout)
	if _progress_timer == null:
		_progress_timer = Timer.new()
		_progress_timer.wait_time = 1.0
		_progress_timer.one_shot = false
		add_child(_progress_timer)
		_progress_timer.timeout.connect(_on_progress_tick)
	# v88.11: живой ввод — зеркалирование текста в браузер по мере набора.
	# Всегда активен по стандарту для анонимности в чатах браузера.
	_live_enabled = true
	if _live_timer == null:
		_live_timer = Timer.new()
		_live_timer.wait_time = 0.35
		_live_timer.one_shot = false
		add_child(_live_timer)
		_live_timer.timeout.connect(_on_live_input_tick)
		_live_timer.start()
	if input_field and not input_field.text_changed.is_connected(_on_live_input_changed):
		input_field.text_changed.connect(_on_live_input_changed)
	if advanced_box and _live_toggle == null:
		_live_toggle = CheckBox.new()
		_live_toggle.text = _t("live_input_toggle")
		_live_toggle.tooltip_text = _t("live_input_tip")
		_live_toggle.button_pressed = true
		_live_toggle.visible = false  # Функция всегда активна по стандарту, переключатель скрыт для анонимности
		advanced_box.add_child(_live_toggle)
		_live_toggle.toggled.connect(_on_live_input_toggled)
	_safe_rename_enabled = _load_safe_rename_setting()
	_rename_unverified_enabled = _load_rename_unverified_setting()
	_rename_mode = _load_rename_mode()
	if advanced_box and _rename_mode_option == null:
		# Режим виден и назван явно: probable снимает блокировку с динамических
		# ссылок по строке, и пользователь должен выбрать это руками, а не
		# получить молча.
		_rename_mode_option = OptionButton.new()
		_rename_mode_option.text = _t("rename_mode_label")
		_rename_mode_option.tooltip_text = _t("rename_mode_tip")
		_rename_mode_option.add_item(_t("rename_mode_strict"), 0)
		_rename_mode_option.add_item(_t("rename_mode_probable"), 1)
		_rename_mode_option.select(1 if _rename_mode == "probable" else 0)
		advanced_box.add_child(_rename_mode_option)
		_rename_mode_option.item_selected.connect(_on_rename_mode_selected)
	elif _rename_mode_option:
		_rename_mode_option.select(1 if _rename_mode == "probable" else 0)
	if advanced_box and _rename_unverified_check == null:
		# Галочка видимая: пользователь должен видеть, что недоказанные ссылки
		# переименовываются, и иметь возможность это отключить. Скрытый дефолт
		# означал бы молчаливую смену строгости переименования.
		_rename_unverified_check = CheckBox.new()
		_rename_unverified_check.text = _t("rename_unverified_toggle")
		_rename_unverified_check.tooltip_text = _t("rename_unverified_tip")
		_rename_unverified_check.button_pressed = _rename_unverified_enabled
		advanced_box.add_child(_rename_unverified_check)
		_rename_unverified_check.toggled.connect(_on_rename_unverified_toggled)
	elif _rename_unverified_check:
		_rename_unverified_check.button_pressed = _rename_unverified_enabled
	if has_node("ChatView"):
		_view = get_node("ChatView")
	else:
		var view_script = load(get_script().resource_path.get_base_dir() + "/agent_chat_view.gd")
		_view = view_script.new()
		_view.name = "ChatView"
		add_child(_view)
	_view.setup($VBoxContainer)
	# Откат доступен прямо из карточки ответа агента: карточка шлёт сигнал,
	# а вопрос и запрос на сервер обрабатываются здесь.
	if not _view.message_rollback_requested.is_connected(_on_message_rollback_requested):
		_view.message_rollback_requested.connect(_on_message_rollback_requested)
	if _hl == null:
		var hl_script = load(get_script().resource_path.get_base_dir() + "/agent_highlight.gd")
		_hl = hl_script.new()
	if _link == null:
		if has_node("ServerLink"):
			_link = get_node("ServerLink")
		else:
			var link_script = load(get_script().resource_path.get_base_dir() + "/agent_server_link.gd")
			_link = link_script.new()
			_link.name = "ServerLink"
			add_child(_link)
	if not _link.chats_response.is_connected(_on_chats_payload):
		_link.chats_response.connect(_on_chats_payload)
	if not _link.short_response.is_connected(_on_short_response):
		# Короткие запросы (живой ввод, опрос прогресса, остановка) идут
		# мимо очереди основных и приходят сюда.
		_link.short_response.connect(_on_short_response)
	if not _link.link_status.is_connected(_notify):
		_link.link_status.connect(_notify)
	if not _link.show_loading_requested.is_connected(_on_link_show_loading):
		_link.show_loading_requested.connect(_on_link_show_loading)
	if not _link.hide_loading_requested.is_connected(_on_link_hide_loading):
		_link.hide_loading_requested.connect(_on_link_hide_loading)
	if not _link.server_state_changed.is_connected(_on_server_state_changed):
		_link.server_state_changed.connect(_on_server_state_changed)
	if $VBoxContainer.has_node("ChatsBar"):
		var bar_old: HBoxContainer = $VBoxContainer/ChatsBar
		_chat_select = bar_old.get_child(0)
		# v63: bez etogo dlinnoe nazvanie chata rastyagivaet svoyo minimalnoe
		# shirinu po vsey svoey dline, i kogda panel uzhe tsentra ekrana (dok v bok),
		# knopki sprava vytesnyayutsya za granitsu. Obrezaem tekst ellipsisom i dayom
		# emu neboljshoy garantirovanniy minimum vmesto estestvennoy shiriny teksta.
		if _chat_select is OptionButton:
			_chat_select.clip_text = true
			_chat_select.custom_minimum_size.x = 40.0
		if not _chat_select.item_selected.is_connected(_on_chat_selected):
			_chat_select.item_selected.connect(_on_chat_selected)
		if bar_old.get_child_count() >= 5:
			_bar_btn_new = bar_old.get_child(1) as Button
			_bar_btn_ren = bar_old.get_child(2) as Button
			_bar_btn_del = bar_old.get_child(3) as Button
			_bar_btn_home = bar_old.get_child(4) as Button
		if bar_old.has_node("MiniLichSettingsBtn"):
			_bar_btn_settings = bar_old.get_node("MiniLichSettingsBtn") as Button
			if not _bar_btn_settings.pressed.is_connected(_on_settings_pressed):
				_bar_btn_settings.pressed.connect(_on_settings_pressed)
		else:
			_bar_btn_settings = Button.new()
			_bar_btn_settings.name = "MiniLichSettingsBtn"
			_bar_btn_settings.text = "⚙"
			_bar_btn_settings.pressed.connect(_on_settings_pressed)
			bar_old.add_child(_bar_btn_settings)
		if bar_old.has_node("UpdateBadge"):
			_update_badge = bar_old.get_node("UpdateBadge") as Button
			if not _update_badge.pressed.is_connected(_on_update_badge_pressed):
				_update_badge.pressed.connect(_on_update_badge_pressed)
		else:
			_update_badge = Button.new()
			_update_badge.name = "UpdateBadge"
			_update_badge.visible = false
			_update_badge.pressed.connect(_on_update_badge_pressed)
			bar_old.add_child(_update_badge)
		_apply_chatbar_texts()
	else:
		var bar := HBoxContainer.new()
		bar.name = "ChatsBar"
		_chat_select = OptionButton.new()
		_chat_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		# v63: obrezaem dlinnye nazvaniya chata ellipsisom, chtoby knopki
		# spravsa za krayem paneli pri uzkoy panele ne vytesnyalisj.
		_chat_select.clip_text = true
		_chat_select.custom_minimum_size.x = 40.0
		_chat_select.item_selected.connect(_on_chat_selected)
		bar.add_child(_chat_select)
		_bar_btn_new = Button.new()
		_bar_btn_new.text = "＋"
		_bar_btn_new.pressed.connect(_on_chat_new_pressed)
		bar.add_child(_bar_btn_new)
		_bar_btn_ren = Button.new()
		_bar_btn_ren.text = "✏"
		_bar_btn_ren.pressed.connect(_on_chat_rename_pressed)
		bar.add_child(_bar_btn_ren)
		_bar_btn_del = Button.new()
		_bar_btn_del.text = "🗑"
		_bar_btn_del.pressed.connect(_on_chat_delete_pressed)
		bar.add_child(_bar_btn_del)
		_bar_btn_home = Button.new()
		_bar_btn_home.pressed.connect(_show_start_ui)
		bar.add_child(_bar_btn_home)
		_bar_btn_settings = Button.new()
		_bar_btn_settings.name = "MiniLichSettingsBtn"
		_bar_btn_settings.text = "⚙"
		_bar_btn_settings.pressed.connect(_on_settings_pressed)
		bar.add_child(_bar_btn_settings)
		_update_badge = Button.new()
		_update_badge.name = "UpdateBadge"
		_update_badge.visible = false
		_update_badge.pressed.connect(_on_update_badge_pressed)
		bar.add_child(_update_badge)
		_apply_chatbar_texts()
		$VBoxContainer.add_child(bar)
		$VBoxContainer.move_child(bar, 0)
	if _updater == null:
		if has_node("AgentUpdater"):
			_updater = get_node("AgentUpdater")
		else:
			var updater_script = load(String(get_script().resource_path).get_base_dir() + "/agent_updater.gd")
			if updater_script:
				_updater = updater_script.new()
				_updater.name = "AgentUpdater"
				add_child(_updater)
		if _updater:
			if not _updater.update_available.is_connected(_on_updater_available):
				_updater.update_available.connect(_on_updater_available)
			if not _updater.update_progress.is_connected(_on_updater_progress):
				_updater.update_progress.connect(_on_updater_progress)
			if not _updater.update_completed.is_connected(_on_updater_completed):
				_updater.update_completed.connect(_on_updater_completed)
			if not _updater.update_error.is_connected(_on_updater_error):
				_updater.update_error.connect(_on_updater_error)
			if not _updater.check_completed.is_connected(_on_updater_check_completed):
				_updater.check_completed.connect(_on_updater_check_completed)
	call_deferred("_check_updates_startup")
	# Фоновое авто-обновление списка чатов при открытии панели — БЕЗ автозапуска
	# сервера: если сервер ещё не поднят, просто ждём, пока пользователь сам
	# нажмёт «новый чат»/«загрузить чат» (иначе при каждом открытии Godot
	# запускалась бы своя копия сервера, независимо от действий пользователя).
	call_deferred("_request_chats", "list", {}, false)
	if _start_screen == null:
		var ss_script = load(get_script().resource_path.get_base_dir() + "/agent_start_screen.gd")
		_start_screen = ss_script.new()
		_start_screen.name = "StartScreen"
		add_child(_start_screen)
		_start_screen.set_anchors_preset(Control.PRESET_FULL_RECT)
		_start_screen.new_chat_requested.connect(_on_start_new_chat)
		_start_screen.load_chat_requested.connect(_on_start_load_chat)
		_start_screen.delete_chat_requested.connect(_on_start_delete_chat)
		_start_screen.sites_tab_requested.connect(_on_sites_tab_requested)
		_start_screen.chats_tab_requested.connect(_on_chats_tab_requested)
		if _start_screen.has_signal("language_changed"):
			_start_screen.language_changed.connect(_on_language_changed)
		if _start_screen.has_signal("open_server_requested"):
			_start_screen.open_server_requested.connect(_on_open_server_folder_pressed)
		if _start_screen.has_signal("settings_requested"):
			_start_screen.settings_requested.connect(_on_settings_pressed)
		# Работа по ключу API. has_signal — на случай, если панель и стартовый
		# экран оказались из разных версий аддона после обновления.
		if _start_screen.has_signal("api_tab_requested"):
			_start_screen.api_tab_requested.connect(_on_api_tab_requested)
			_start_screen.api_settings_save_requested.connect(_on_api_settings_save)
			_start_screen.api_models_refresh_requested.connect(_on_api_models_refresh)
			_start_screen.api_test_requested.connect(_on_api_test_requested)
			_start_screen.new_api_chat_requested.connect(_on_start_new_api_chat)
		# Отдельной проверкой, а не рядом выше: сигнал смены модели у открытого
		# чата добавлен позже, и панель могла оказаться от более новой версии
		# аддона, чем сохранённая сцена — обращение к несуществующему сигналу
		# оборвало бы всё подключение и экран остался бы мёртвым.
		if _start_screen.has_signal("api_chat_model_requested"):
			_start_screen.api_chat_model_requested.connect(_on_api_chat_model)
		# Отдельной проверкой, а не внутри блока выше: сигнал появился позже
		# остальных, и экран прошлой версии его не объявляет — обращение к нему
		# оборвало бы подключение и всех предыдущих сигналов вместе с ним.
		if _start_screen.has_signal("api_models_scan_requested"):
			_start_screen.api_models_scan_requested.connect(_on_api_models_scan)
	_show_start_ui()
	call_deferred("_request_chats", "sites", {}, false)
	call_deferred("_on_language_changed")
	# Восстановление после перезагрузки скрипта: если панель перезагрузилась,
	# пока кнопки были временно заблокированы охранником — вернуть их в рабочее состояние.
	if confirm_button and reject_button and not _is_network_busy:
		confirm_button.disabled = false
		reject_button.disabled = false
	var se := EditorInterface.get_script_editor()
	if se and not se.editor_script_changed.is_connected(_on_editor_script_changed):
		se.editor_script_changed.connect(_on_editor_script_changed)
	if not input_field.gui_input.is_connected(_on_input_field_gui_input):
		input_field.gui_input.connect(_on_input_field_gui_input)
	if has_node("VBoxContainer/SettingsBox"):
		$VBoxContainer/SettingsBox.hide()
	# Оформление — последним: к этому моменту созданы и кнопки строки чатов,
	# и кнопки редких инструментов, иначе часть из них осталась бы без стиля.
	_apply_panel_theme()
	_refresh_chat_model_btn()


# split_gd: тело — agent_panel_part1.gd
func _set_pending_action(active: bool, description: String = "") -> void:
	AgentPanelPart1._set_pending_action(self, active, description)


# split_gd: тело — agent_panel_part1.gd
func _has_pending_action() -> bool:
	return AgentPanelPart1._has_pending_action(self)


# split_gd: тело — agent_panel_part1.gd
func _clear_pending_action_state() -> void:
	AgentPanelPart1._clear_pending_action_state(self)


# split_gd: тело — agent_panel_part1.gd
func _escape_bbcode(text: String) -> String:
	return AgentPanelPart1._escape_bbcode(self, text)


# split_gd: тело — agent_panel_part1.gd
func _set_ui_busy(busy: bool) -> void:
	AgentPanelPart1._set_ui_busy(self, busy)


# split_gd: тело — agent_panel_part1.gd
func _clear_chat_input(reset_live: bool = true) -> void:
	AgentPanelPart1._clear_chat_input(self, reset_live)


# split_gd: тело — agent_panel_part1.gd
func _restore_chat_draft() -> void:
	AgentPanelPart1._restore_chat_draft(self)


# split_gd: тело — agent_panel_part1.gd
func _finish_chat_send() -> void:
	AgentPanelPart1._finish_chat_send(self)


# split_gd: тело — agent_panel_part1.gd
func _switch_chat_draft(next_chat_id: String) -> void:
	AgentPanelPart1._switch_chat_draft(self, next_chat_id)


# split_gd: тело — agent_panel_part1.gd
func _on_server_state_changed(running: bool) -> void:
	AgentPanelPart1._on_server_state_changed(self, running)


# split_gd: тело — agent_panel_part1.gd
func _on_open_server_folder_pressed() -> void:
	AgentPanelPart1._on_open_server_folder_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _show_stop_button() -> void:
	AgentPanelPart1._show_stop_button(self)


# split_gd: тело — agent_panel_part1.gd
func _hide_stop_button() -> void:
	AgentPanelPart1._hide_stop_button(self)


# split_gd: тело — agent_panel_part1.gd
func _on_stop_pressed() -> void:
	AgentPanelPart1._on_stop_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _refresh_chat_model_btn() -> void:
	AgentPanelPart1._refresh_chat_model_btn(self)


# split_gd: тело — agent_panel_part1.gd
func _on_chat_model_pressed() -> void:
	AgentPanelPart1._on_chat_model_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _on_input_field_gui_input(event: InputEvent) -> void:
	AgentPanelPart1._on_input_field_gui_input(self, event)


# --- v88.11: живой ввод — зеркалирование текста панели в поле сайта ---

# split_gd: тело — agent_panel_part1.gd
func _on_live_input_changed() -> void:
	AgentPanelPart1._on_live_input_changed(self)


# split_gd: тело — agent_panel_part1.gd
func _on_live_input_tick() -> void:
	AgentPanelPart1._on_live_input_tick(self)


# split_gd: тело — agent_panel_part1.gd
func _on_live_input_response(_result: int, _code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	AgentPanelPart1._on_live_input_response(self, _result, _code, _headers, _body)


# split_gd: тело — agent_panel_part1.gd
func _on_live_input_toggled(pressed: bool) -> void:
	AgentPanelPart1._on_live_input_toggled(self, pressed)


# split_gd: тело — agent_panel_part1.gd
func _load_live_input_setting() -> bool:
	return AgentPanelPart1._load_live_input_setting(self)


# split_gd: тело — agent_panel_part1.gd
func _save_live_input_setting(enabled: bool) -> void:
	AgentPanelPart1._save_live_input_setting(self, enabled)


# split_gd: тело — agent_panel_part1.gd
func _on_safe_rename_toggled(pressed: bool) -> void:
	AgentPanelPart1._on_safe_rename_toggled(self, pressed)


# split_gd: тело — agent_panel_part1.gd
func _load_safe_rename_setting() -> bool:
	return AgentPanelPart1._load_safe_rename_setting(self)


# split_gd: тело — agent_panel_part1.gd
func _save_safe_rename_setting(enabled: bool) -> void:
	AgentPanelPart1._save_safe_rename_setting(self, enabled)


# split_gd: тело — agent_panel_part1.gd
func _on_rename_unverified_toggled(pressed: bool) -> void:
	AgentPanelPart1._on_rename_unverified_toggled(self, pressed)


# split_gd: тело — agent_panel_part1.gd
func _load_rename_unverified_setting() -> bool:
	return AgentPanelPart1._load_rename_unverified_setting(self)


# split_gd: тело — agent_panel_part1.gd
func _save_rename_unverified_setting(enabled: bool) -> void:
	AgentPanelPart1._save_rename_unverified_setting(self, enabled)


# split_gd: тело — agent_panel_part1.gd
func _on_rename_mode_selected(index: int) -> void:
	AgentPanelPart1._on_rename_mode_selected(self, index)


# split_gd: тело — agent_panel_part1.gd
func _load_rename_mode() -> String:
	return AgentPanelPart1._load_rename_mode(self)


# split_gd: тело — agent_panel_part1.gd
func _save_rename_mode(mode: String) -> void:
	AgentPanelPart1._save_rename_mode(self, mode)


# split_gd: тело — agent_panel_part1.gd
func _load_policy_settings() -> void:
	AgentPanelPart1._load_policy_settings(self)


# split_gd: тело — agent_panel_part1.gd
func _save_allow_addons_policy() -> void:
	AgentPanelPart1._save_allow_addons_policy(self)


# split_gd: тело — agent_panel_part1.gd
func _policy_body(extra: Dictionary = {}) -> Dictionary:
	return AgentPanelPart1._policy_body(self, extra)


# split_gd: тело — agent_panel_part1.gd
func _policy_json(value) -> String:
	return AgentPanelPart1._policy_json(self, value)


# split_gd: тело — agent_panel_part1.gd
func _on_allow_addons_toggled(pressed: bool) -> void:
	AgentPanelPart1._on_allow_addons_toggled(self, pressed)


# split_gd: тело — agent_panel_part1.gd
func _on_allow_self_edit_toggled(pressed: bool) -> void:
	AgentPanelPart1._on_allow_self_edit_toggled(self, pressed)


# split_gd: тело — agent_panel_part1.gd
func _request_policy_enable(kind: String) -> void:
	AgentPanelPart1._request_policy_enable(self, kind)


# split_gd: тело — agent_panel_part1.gd
func _close_policy_confirmation() -> void:
	AgentPanelPart1._close_policy_confirmation(self)


# split_gd: тело — agent_panel_part1.gd
func _restore_settings_window() -> void:
	AgentPanelPart1._restore_settings_window(self)


# split_gd: тело — agent_panel_part1.gd
func _on_reinit_pressed() -> void:
	AgentPanelPart1._on_reinit_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _on_send_pressed() -> void:
	AgentPanelPart1._on_send_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _send_chat_raw(prompt: String, ignore_mismatch: bool) -> void:
	AgentPanelPart1._send_chat_raw(self, prompt, ignore_mismatch)


# split_gd: тело — agent_panel_part1.gd
func _capture_editor_context() -> Dictionary:
	return AgentPanelPart1._capture_editor_context(self)


# split_gd: тело — agent_panel_part1.gd
func _on_confirm_pressed() -> void:
	AgentPanelPart1._on_confirm_pressed(self)


# split_gd: тело — agent_panel_part1.gd
func _on_reject_pressed() -> void:
	AgentPanelPart1._on_reject_pressed(self)


## Сколько мест переименования показываем галочками в карточке. Ограничение
## только на показ: снятые места адресуются своим id, а не порядковым номером.
const RENAME_USAGE_LIST_LIMIT := 40


# split_gd: тело — agent_panel_part1.gd
func _rename_usage_card_box(card) -> VBoxContainer:
	return AgentPanelPart1._rename_usage_card_box(self, card)


# split_gd: тело — agent_panel_part1.gd
func _attach_rename_usage_checklist(card) -> void:
	AgentPanelPart1._attach_rename_usage_checklist(self, card)


# split_gd: тело — agent_panel_part1.gd
func _send_confirm_request(approved: bool) -> void:
	AgentPanelPart1._send_confirm_request(self, approved)


# split_gd: тело — agent_panel_part1.gd
func _send_scene_result(execution: Dictionary, envelope: Dictionary) -> void:
	AgentPanelPart1._send_scene_result(self, execution, envelope)


# split_gd: тело — agent_panel_part1.gd
func _finalize_body(kind: String) -> Dictionary:
	return AgentPanelPart1._finalize_body(self, kind)


# split_gd: тело — agent_panel_part1.gd
func _send_pending_finalize(kind: String) -> void:
	AgentPanelPart1._send_pending_finalize(self, kind)


# split_gd: тело — agent_panel_part1.gd
func _schedule_finalize_retry(kind: String) -> void:
	await AgentPanelPart1._schedule_finalize_retry(self, kind)


# split_gd: тело — agent_panel_part1.gd
func _discard_pending_finalize(kind: String) -> void:
	AgentPanelPart1._discard_pending_finalize(self, kind)


# split_gd: тело — agent_panel_part1.gd
func _prepare_scene_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	return AgentPanelPart1._prepare_scene_action(self, pending, prepare_data)


# split_gd: тело — agent_panel_part1.gd
func _execute_scene_action(envelope: Dictionary) -> void:
	AgentPanelPart1._execute_scene_action(self, envelope)


# split_gd: тело — agent_panel_part1.gd
func _prepare_project_settings_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	return AgentPanelPart1._prepare_project_settings_action(self, pending, prepare_data)


# split_gd: тело — agent_panel_part1.gd
func _execute_project_settings_action(envelope: Dictionary) -> void:
	AgentPanelPart1._execute_project_settings_action(self, envelope)


# split_gd: тело — agent_panel_part1.gd
func _prepare_resource_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	return AgentPanelPart1._prepare_resource_action(self, pending, prepare_data)


# split_gd: тело — agent_panel_part1.gd
func _execute_resource_action(envelope: Dictionary) -> void:
	AgentPanelPart1._execute_resource_action(self, envelope)


# split_gd: тело — agent_panel_part1.gd
func _start_plan_execution(total: int) -> void:
	AgentPanelPart1._start_plan_execution(self, total)


# split_gd: тело — agent_panel_part1.gd
func _request_plan_step() -> void:
	AgentPanelPart1._request_plan_step(self)


# split_gd: тело — agent_panel_part1.gd
func _end_plan_execution() -> void:
	AgentPanelPart1._end_plan_execution(self)


# split_gd: тело — agent_panel_part1.gd
func _show_plan_stop_button() -> void:
	AgentPanelPart1._show_plan_stop_button(self)


# split_gd: тело — agent_panel_part2.gd
func _hide_plan_stop_button() -> void:
	AgentPanelPart2._hide_plan_stop_button(self)


# split_gd: тело — agent_panel_part2.gd
func _on_plan_stop_pressed() -> void:
	AgentPanelPart2._on_plan_stop_pressed(self)


# split_gd: тело — agent_panel_part2.gd
func _note_autoload_removed(json) -> void:
	AgentPanelPart2._note_autoload_removed(self, json)


# split_gd: тело — agent_panel_part2.gd
func _maybe_prompt_project_reload(json) -> void:
	AgentPanelPart2._maybe_prompt_project_reload(self, json)


# split_gd: тело — agent_panel_part2.gd
func _on_reload_project_confirmed() -> void:
	AgentPanelPart2._on_reload_project_confirmed(self)


# split_gd: тело — agent_panel_part2.gd
func _show_plan_rollback_dialog(chain_id: String, desc: String) -> void:
	AgentPanelPart2._show_plan_rollback_dialog(self, chain_id, desc)


# split_gd: тело — agent_panel_part2.gd
func _on_plan_rollback_confirmed() -> void:
	AgentPanelPart2._on_plan_rollback_confirmed(self)


# split_gd: тело — agent_panel_part2.gd
func _send_plan_rollback_chain_request(force: bool) -> void:
	AgentPanelPart2._send_plan_rollback_chain_request(self, force)


# split_gd: тело — agent_panel_part2.gd
func _on_message_rollback_requested(entry_id: String) -> void:
	AgentPanelPart2._on_message_rollback_requested(self, entry_id)


# split_gd: тело — agent_panel_part2.gd
func _show_battle_choice_summary(data: Dictionary) -> void:
	AgentPanelPart2._show_battle_choice_summary(self, data)


# split_gd: тело — agent_panel_part2.gd
func _on_rollback_pressed(entry_id: String = "") -> void:
	AgentPanelPart2._on_rollback_pressed(self, entry_id)


# split_gd: тело — agent_panel_part2.gd
func _send_rollback_request(force: bool) -> void:
	AgentPanelPart2._send_rollback_request(self, force)


# split_gd: тело — agent_panel_part2.gd
func _show_rollback_dialog(desc: String) -> void:
	AgentPanelPart2._show_rollback_dialog(self, desc)


# split_gd: тело — agent_panel_part2.gd
func _on_rollback_confirmed() -> void:
	AgentPanelPart2._on_rollback_confirmed(self)


# split_gd: тело — agent_panel_part2.gd
func _ensure_file_logging_enabled() -> void:
	AgentPanelPart2._ensure_file_logging_enabled(self)


# split_gd: тело — agent_panel_part2.gd
func _on_check_log_pressed() -> void:
	AgentPanelPart2._on_check_log_pressed(self)


# split_gd: тело — agent_panel_part2.gd
func _check_api_cache_freshness() -> void:
	AgentPanelPart2._check_api_cache_freshness(self)


# split_gd: тело — agent_panel_part2.gd
func _schedule_api_cache_check_retry() -> void:
	AgentPanelPart2._schedule_api_cache_check_retry(self)


# split_gd: тело — agent_panel_part2.gd
func _on_export_api_pressed() -> void:
	AgentPanelPart2._on_export_api_pressed(self)


# split_gd: тело — agent_panel_part2.gd
func _export_api_to_server(silent: bool) -> void:
	AgentPanelPart2._export_api_to_server(self, silent)


# split_gd: тело — agent_panel_part2.gd
func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	await AgentPanelPart2._on_request_completed(self, result, response_code, headers, body)


# split_gd: тело — agent_panel_part2.gd
func _log_error(msg: String) -> void:
	AgentPanelPart2._log_error(self, msg)


# split_gd: тело — agent_panel_part2.gd
func _scroll_chat_to_end() -> void:
	AgentPanelPart2._scroll_chat_to_end(self)


# split_gd: тело — agent_panel_part2.gd
func _guard_confirm_buttons() -> void:
	await AgentPanelPart2._guard_confirm_buttons(self)


# split_gd: тело — agent_panel_part2.gd
func _on_guard_timeout() -> void:
	AgentPanelPart2._on_guard_timeout(self)


# split_gd: тело — agent_panel_part2.gd
func _reconcile_confirm_buttons() -> void:
	AgentPanelPart2._reconcile_confirm_buttons(self)


# split_gd: тело — agent_panel_part2.gd
func _auto_reload_changed_scene(p: String) -> void:
	AgentPanelPart2._auto_reload_changed_scene(self, p)


# split_gd: тело — agent_panel_part2.gd
func _scene_reload_would_lose_edits(p: String) -> bool:
	return AgentPanelPart2._scene_reload_would_lose_edits(self, p)


# split_gd: тело — agent_panel_part2.gd
func _scene_history(root: Node) -> UndoRedo:
	return AgentPanelPart2._scene_history(self, root)


# split_gd: тело — agent_panel_part2.gd
func _scene_undo_version(p: String) -> int:
	return AgentPanelPart2._scene_undo_version(self, p)


# split_gd: тело — agent_panel_part2.gd
func _mark_scene_clean(p: String) -> void:
	AgentPanelPart2._mark_scene_clean(self, p)


# split_gd: тело — agent_panel_part2.gd
func _on_editor_scene_saved(path: String) -> void:
	AgentPanelPart2._on_editor_scene_saved(self, path)


# split_gd: тело — agent_panel_part2.gd
func _scene_reload_blocked_notice(p: String) -> void:
	AgentPanelPart2._scene_reload_blocked_notice(self, p)


# split_gd: тело — agent_panel_part3.gd
func _open_pending_scene_paths() -> PackedStringArray:
	return AgentPanelPart3._open_pending_scene_paths(self)


# split_gd: тело — agent_panel_part3.gd
func _close_scenes_before_write() -> void:
	AgentPanelPart3._close_scenes_before_write(self)


# split_gd: тело — agent_panel_part3.gd
func _reopen_scenes_after_write() -> void:
	AgentPanelPart3._reopen_scenes_after_write(self)


# split_gd: тело — agent_panel_part3.gd
func _close_target_scenes_before_write(extra_targets: PackedStringArray) -> void:
	AgentPanelPart3._close_target_scenes_before_write(self, extra_targets)


# split_gd: тело — agent_panel_part3.gd
func _remap_scenes_to_reopen(old_path: String, new_path: String) -> void:
	AgentPanelPart3._remap_scenes_to_reopen(self, old_path, new_path)


# split_gd: тело — agent_panel_part3.gd
func _sync_resource_uid(_old_path: String, new_path: String) -> void:
	AgentPanelPart3._sync_resource_uid(self, _old_path, new_path)


# split_gd: тело — agent_panel_part3.gd
func _notify_path_changed(path: String) -> void:
	AgentPanelPart3._notify_path_changed(self, path)


# split_gd: тело — agent_panel_part3.gd
func _refresh_changed_paths(paths) -> void:
	AgentPanelPart3._refresh_changed_paths(self, paths)


# split_gd: тело — agent_panel_part3.gd
func _ensure_script_autoreload_setting() -> void:
	AgentPanelPart3._ensure_script_autoreload_setting(self)


# split_gd: тело — agent_panel_part3.gd
func _force_reload_open_script() -> void:
	AgentPanelPart3._force_reload_open_script(self)


# split_gd: тело — agent_panel_part3.gd
func _dirty_open_scripts(target_paths: PackedStringArray) -> PackedStringArray:
	return AgentPanelPart3._dirty_open_scripts(self, target_paths)


# split_gd: тело — agent_panel_part3.gd
func _sync_open_script_with_disk(target_path: String) -> void:
	AgentPanelPart3._sync_open_script_with_disk(self, target_path)


# split_gd: тело — agent_panel_part3.gd
func _find_open_code_edit_for(script_editor, target_script: Script, target_path: String) -> CodeEdit:
	return AgentPanelPart3._find_open_code_edit_for(self, script_editor, target_script, target_path)


# split_gd: тело — agent_panel_part3.gd
func _normalized_script_text(text: String) -> String:
	return AgentPanelPart3._normalized_script_text(self, text)


# ---------------------------------------------------------------------------
# Автопроверка лога после закрытия игры: следим за is_playing_scene()
# и после остановки игры сами проверяем лог. В браузер при этом НИЧЕГО
# не уходит — отправка ошибок по-прежнему только после подтверждения.
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _on_play_watch_tick() -> void:
	await AgentPanelPart3._on_play_watch_tick(self)


# split_gd: тело — agent_panel_part3.gd
func _auto_check_log() -> void:
	AgentPanelPart3._auto_check_log(self)


# ---------------------------------------------------------------------------
# Подсветка строк, изменённых агентом.
# Красим не по номерам строк, а ПО СОДЕРЖИМОМУ блока: при любой правке
# блок ищется заново, и подсветка «переезжает» вместе с кодом. Если
# пользователь отредактировал сам блок — подсветка гаснет (это уже
# не код агента).
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _on_progress_tick() -> void:
	AgentPanelPart3._on_progress_tick(self)


# split_gd: тело — agent_panel_part3.gd
func _on_short_response(id: String, result: int, code: int,
		headers: PackedStringArray, body: PackedByteArray) -> void:
	AgentPanelPart3._on_short_response(self, id, result, code, headers, body)


# split_gd: тело — agent_panel_part3.gd
func _on_short_stop_response(_result: int, _code: int) -> void:
	AgentPanelPart3._on_short_stop_response(self, _result, _code)


# split_gd: тело — agent_panel_part3.gd
func _on_progress_response(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	AgentPanelPart3._on_progress_response(self, _result, response_code, _headers, body)


# ---------------------------------------------------------------------------
# Чаты: список, создание, выбор (открывает страницу в браузере),
# переименование, удаление. Сохранённый диалог восстанавливается в панели.
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _request_chats(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	AgentPanelPart3._request_chats(self, kind, extra, allow_autostart)


# split_gd: тело — agent_panel_part3.gd
func _on_chats_payload(kind: String, json: Dictionary, extra: Dictionary) -> void:
	AgentPanelPart3._on_chats_payload(self, kind, json, extra)


# split_gd: тело — agent_panel_part3.gd
func _fill_chat_list(chats) -> void:
	AgentPanelPart3._fill_chat_list(self, chats)


# split_gd: тело — agent_panel_part3.gd
func _on_chat_selected(index: int) -> void:
	AgentPanelPart3._on_chat_selected(self, index)


# split_gd: тело — agent_panel_part3.gd
func _on_chat_new_pressed() -> void:
	AgentPanelPart3._on_chat_new_pressed(self)


# split_gd: тело — agent_panel_part3.gd
func _on_chat_rename_pressed() -> void:
	AgentPanelPart3._on_chat_rename_pressed(self)


# split_gd: тело — agent_panel_part3.gd
func _finish_chat_rename(new_title: String) -> void:
	AgentPanelPart3._finish_chat_rename(self, new_title)


# split_gd: тело — agent_panel_part3.gd
func _cancel_chat_rename() -> void:
	AgentPanelPart3._cancel_chat_rename(self)


# split_gd: тело — agent_panel_part3.gd
func _close_rename_edit() -> void:
	AgentPanelPart3._close_rename_edit(self)


# split_gd: тело — agent_panel_part3.gd
func _on_chat_delete_pressed() -> void:
	AgentPanelPart3._on_chat_delete_pressed(self)


# split_gd: тело — agent_panel_part3.gd
func _on_delete_confirmed() -> void:
	AgentPanelPart3._on_delete_confirmed(self)


# split_gd: тело — agent_panel_part3.gd
func _on_start_delete_chat(chat_id: String) -> void:
	AgentPanelPart3._on_start_delete_chat(self, chat_id)


# split_gd: тело — agent_panel_part3.gd
func _render_transcript(entries) -> void:
	AgentPanelPart3._render_transcript(self, entries)


# ---------------------------------------------------------------------------
# Стартовый экран, переключение сайтов и проверка "не тот сайт".
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _on_editor_script_changed(scr: Script) -> void:
	AgentPanelPart3._on_editor_script_changed(self, scr)


# split_gd: тело — agent_panel_part3.gd
func _show_start_ui() -> void:
	AgentPanelPart3._show_start_ui(self)


# split_gd: тело — agent_panel_part3.gd
func _enter_chat_ui() -> void:
	AgentPanelPart3._enter_chat_ui(self)


# split_gd: тело — agent_panel_part3.gd
func _apply_chatbar_texts() -> void:
	AgentPanelPart3._apply_chatbar_texts(self)


# split_gd: тело — agent_panel_part3.gd
func _on_language_changed() -> void:
	AgentPanelPart3._on_language_changed(self)


# split_gd: тело — agent_panel_part3.gd
func _on_sites_tab_requested() -> void:
	AgentPanelPart3._on_sites_tab_requested(self)


# split_gd: тело — agent_panel_part3.gd
func _on_chats_tab_requested() -> void:
	AgentPanelPart3._on_chats_tab_requested(self)


# split_gd: тело — agent_panel_part3.gd
func _on_start_new_chat(site_id: String) -> void:
	AgentPanelPart3._on_start_new_chat(self, site_id)


# split_gd: тело — agent_panel_part3.gd
func _on_start_load_chat(chat_id: String) -> void:
	AgentPanelPart3._on_start_load_chat(self, chat_id)


# split_gd: тело — agent_panel_part3.gd
func _handle_site_mismatch(site_name: String, prompt: String) -> void:
	AgentPanelPart3._handle_site_mismatch(self, site_name, prompt)


# split_gd: тело — agent_panel_part3.gd
func _on_site_switch_yes() -> void:
	AgentPanelPart3._on_site_switch_yes(self)


# split_gd: тело — agent_panel_part3.gd
func _on_site_switch_no() -> void:
	AgentPanelPart3._on_site_switch_no(self)


# ---------------------------------------------------------------------------
# Уведомления о загрузке страницы + автозапуск сервера.
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _begin_page_wait() -> void:
	AgentPanelPart3._begin_page_wait(self)


# split_gd: тело — agent_panel_part3.gd
func _on_pagewait_tick() -> void:
	AgentPanelPart3._on_pagewait_tick(self)


# split_gd: тело — agent_panel_part3.gd
func _on_browser_status(json: Dictionary) -> void:
	AgentPanelPart3._on_browser_status(self, json)


# ---------------------------------------------------------------------------
# Работа по ключу API: настройки, список моделей, проверка подключения.
# Панель здесь только курьер: форму рисует и заполняет стартовый экран, а
# состояние настроек целиком приходит с сервера — своего представления о нём
# панель не держит, поэтому оно не может разойтись с файлом на диске.
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part3.gd
func _on_api_tab_requested() -> void:
	AgentPanelPart3._on_api_tab_requested(self)


# split_gd: тело — agent_panel_part3.gd
func _on_api_settings_save(data: Dictionary) -> void:
	AgentPanelPart3._on_api_settings_save(self, data)


# split_gd: тело — agent_panel_part3.gd
func _on_api_models_refresh(provider: String, free_only: bool) -> void:
	AgentPanelPart3._on_api_models_refresh(self, provider, free_only)


# split_gd: тело — agent_panel_part3.gd
func _on_api_models_scan(force: bool) -> void:
	AgentPanelPart3._on_api_models_scan(self, force)


# split_gd: тело — agent_panel_part3.gd
func _on_api_test_requested(provider: String, model: String) -> void:
	AgentPanelPart3._on_api_test_requested(self, provider, model)


# split_gd: тело — agent_panel_part3.gd
func _on_start_new_api_chat(provider: String, model: String) -> void:
	AgentPanelPart3._on_start_new_api_chat(self, provider, model)


# split_gd: тело — agent_panel_part3.gd
func _on_api_payload(kind: String, json: Dictionary) -> void:
	AgentPanelPart3._on_api_payload(self, kind, json)


# split_gd: тело — agent_panel_part3.gd
func _push_api_switch_target() -> void:
	AgentPanelPart3._push_api_switch_target(self)


# split_gd: тело — agent_panel_part3.gd
func _on_api_chat_model(provider: String, model: String) -> void:
	AgentPanelPart3._on_api_chat_model(self, provider, model)


# split_gd: тело — agent_panel_part3.gd
func _notify(text: String, kind: String = "info") -> void:
	AgentPanelPart3._notify(self, text, kind)


# split_gd: тело — agent_panel_part3.gd
func _on_link_show_loading(text: String) -> void:
	AgentPanelPart3._on_link_show_loading(self, text)


# split_gd: тело — agent_panel_part3.gd
func _on_link_hide_loading() -> void:
	AgentPanelPart3._on_link_hide_loading(self)


# split_gd: тело — agent_panel_part3.gd
func _close_ghost_script_tabs_for_move(old_path: String, is_folder: bool) -> void:
	AgentPanelPart3._close_ghost_script_tabs_for_move(self, old_path, is_folder)


# split_gd: тело — agent_panel_part3.gd
func _close_ghost_script_tab(target_path: String) -> void:
	AgentPanelPart3._close_ghost_script_tab(self, target_path)


# split_gd: тело — agent_panel_part3.gd
func _after_ghost_close() -> void:
	AgentPanelPart3._after_ghost_close(self)
# ---------------------------------------------------------------------------
# Окно настроек агента: безопасное переименование, инструменты и обновления.
# Экспериментальные настройки MiniLich скрыты (заготовка на будущее).
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part4.gd
func _on_settings_pressed() -> void:
	AgentPanelPart4._on_settings_pressed(self)


# ---------------------------------------------------------------------------
# Подсистема проверки и установки обновлений
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part4.gd
func _check_updates_startup() -> void:
	AgentPanelPart4._check_updates_startup(self)


# split_gd: тело — agent_panel_part4.gd
func _open_update_dialog(info: Dictionary) -> void:
	AgentPanelPart4._open_update_dialog(self, info)


# split_gd: тело — agent_panel_part4.gd
func _on_updater_available(info: Dictionary) -> void:
	AgentPanelPart4._on_updater_available(self, info)


# split_gd: тело — agent_panel_part4.gd
func _on_updater_progress(phase: String, current: int, total: int) -> void:
	AgentPanelPart4._on_updater_progress(self, phase, current, total)


# split_gd: тело — agent_panel_part4.gd
func _on_updater_completed(_restart_needed: bool) -> void:
	AgentPanelPart4._on_updater_completed(self, _restart_needed)


# split_gd: тело — agent_panel_part4.gd
func _on_updater_error(msg: String) -> void:
	AgentPanelPart4._on_updater_error(self, msg)


# split_gd: тело — agent_panel_part4.gd
func _on_updater_check_completed(has_update: bool, info: Dictionary) -> void:
	AgentPanelPart4._on_updater_check_completed(self, has_update, info)


# split_gd: тело — agent_panel_part4.gd
func _on_update_badge_pressed() -> void:
	AgentPanelPart4._on_update_badge_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_check_updates_pressed() -> void:
	AgentPanelPart4._on_check_updates_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_update_auto_pressed() -> void:
	AgentPanelPart4._on_update_auto_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_update_github_pressed() -> void:
	AgentPanelPart4._on_update_github_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_update_restart_pressed() -> void:
	AgentPanelPart4._on_update_restart_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_train_mode_toggled(pressed: bool) -> void:
	AgentPanelPart4._on_train_mode_toggled(self, pressed)


# split_gd: тело — agent_panel_part4.gd
func _on_minilich_toggled(pressed: bool) -> void:
	AgentPanelPart4._on_minilich_toggled(self, pressed)


# split_gd: тело — agent_panel_part4.gd
func _on_github_fetch_pressed() -> void:
	AgentPanelPart4._on_github_fetch_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func _on_minilich_payload(kind: String, json: Dictionary) -> void:
	AgentPanelPart4._on_minilich_payload(self, kind, json)


# split_gd: тело — agent_panel_part4.gd
func _minilich_status_text(json: Dictionary) -> String:
	return AgentPanelPart4._minilich_status_text(self, json)


# ---------------------------------------------------------------------------
# Безопасное переименование файла с обновлением ссылок в проекте.
# ---------------------------------------------------------------------------

# split_gd: тело — agent_panel_part4.gd
func _on_safe_rename_pressed() -> void:
	AgentPanelPart4._on_safe_rename_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func open_safe_rename(prefill_path: String = "") -> void:
	AgentPanelPart4.open_safe_rename(self, prefill_path)


# split_gd: тело — agent_panel_part4.gd
func _ensure_safe_rename_dialog() -> void:
	AgentPanelPart4._ensure_safe_rename_dialog(self)


# split_gd: тело — agent_panel_part4.gd
func _on_safe_rename_browse() -> void:
	AgentPanelPart4._on_safe_rename_browse(self)


# split_gd: тело — agent_panel_part4.gd
func _on_safe_rename_preview() -> void:
	AgentPanelPart4._on_safe_rename_preview(self)


# split_gd: тело — agent_panel_part4.gd
func _on_safe_rename_apply() -> void:
	AgentPanelPart4._on_safe_rename_apply(self)


# v106 (audit 1.4): последовательная очередь post_move_sync-запросов.
var _fs_move_queue: Array = []
var _fs_move_busy := false

# ЗАДАЧА 3: перехват переименования узла человеком в дереве сцен.
# Очередь — как у перемещений файлов; сцена на диске НЕ переписывается
# (scripts_only): узел уже переименован в памяти редактора, и там могут быть
# несохранённые правки, которые перезапись файла потеряет.
var _node_rename_queue: Array = []
var _node_rename_busy := false
var _node_rename_suppress := 0
var _node_sync_ctx: Dictionary = {}
# Карта «путь в редакторе → путь на диске»: scripts_only не переписывает .tscn,
# поэтому после первого перехвата путь в редакторе расходится с диском, и все
# следующие синхронизации должны строиться по дисковому пути (контракт
# сервера: node_path — полный путь узла на диске, previous_name — имя у редактора).
var _node_disk_names: Dictionary = {}


# split_gd: тело — agent_panel_part4.gd
func handle_filesystem_move(old_path: String, new_path: String, is_folder: bool = false) -> void:
	AgentPanelPart4.handle_filesystem_move(self, old_path, new_path, is_folder)


# split_gd: тело — agent_panel_part4.gd
func _process_fs_move_queue() -> void:
	AgentPanelPart4._process_fs_move_queue(self)


# split_gd: тело — agent_panel_part4.gd
func _send_post_move_sync(clean_old: String, clean_new: String, is_folder: bool) -> void:
	AgentPanelPart4._send_post_move_sync(self, clean_old, clean_new, is_folder)


# split_gd: тело — agent_panel_part4.gd
func _on_post_move_sync_response(result: int, response_code: int,
		body_bytes: PackedByteArray) -> void:
	AgentPanelPart4._on_post_move_sync_response(self, result, response_code, body_bytes)


# --- ЗАДАЧА 3: перехват переименования узла человеком -----------------------

# split_gd: тело — agent_panel_part4.gd
func handle_scene_node_renamed(scene_path: String, old_path: String,
		old_name: String, new_name: String) -> void:
	AgentPanelPart4.handle_scene_node_renamed(self, scene_path, old_path, old_name, new_name)


# split_gd: тело — agent_panel_part4.gd
func _process_node_rename_queue() -> void:
	AgentPanelPart4._process_node_rename_queue(self)


# split_gd: тело — agent_panel_part4.gd
func _node_rename_body(item: Dictionary) -> Dictionary:
	return AgentPanelPart4._node_rename_body(self, item)


# split_gd: тело — agent_panel_part4.gd
func _send_node_rename_sync(item: Dictionary) -> void:
	AgentPanelPart4._send_node_rename_sync(self, item)


# split_gd: тело — agent_panel_part4.gd
func _node_disk_path_for_sync(scene_path: String, old_path: String, old_name: String) -> String:
	return AgentPanelPart4._node_disk_path_for_sync(self, scene_path, old_path, old_name)


# split_gd: тело — agent_panel_part4.gd
func _note_node_disk_name(scene_path: String, editor_path: String, disk_path: String) -> void:
	AgentPanelPart4._note_node_disk_name(self, scene_path, editor_path, disk_path)


# split_gd: тело — agent_panel_part4.gd
func _scene_node_paths(scene_path: String) -> PackedStringArray:
	return AgentPanelPart4._scene_node_paths(self, scene_path)


# split_gd: тело — agent_panel_part4.gd
func _tscn_attr(header: String, key: String) -> String:
	return AgentPanelPart4._tscn_attr(self, header, key)


# split_gd: тело — agent_panel_part4.gd
func _scene_has_node_path(scene_path: String, node_path: String) -> bool:
	return AgentPanelPart4._scene_has_node_path(self, scene_path, node_path)


# split_gd: тело — agent_panel_part4.gd
func _scene_node_name_count(scene_path: String, node_name: String) -> int:
	return AgentPanelPart4._scene_node_name_count(self, scene_path, node_name)


# split_gd: тело — agent_panel_part4.gd
func _node_path_with_leaf(node_path: String, leaf: String) -> String:
	return AgentPanelPart4._node_path_with_leaf(self, node_path, leaf)


# split_gd: тело — agent_panel_part4.gd
func _node_rename_failed(reason: String) -> void:
	AgentPanelPart4._node_rename_failed(self, reason)


# split_gd: тело — agent_panel_part4.gd
func _finish_node_rename_roundtrip() -> void:
	AgentPanelPart4._finish_node_rename_roundtrip(self)


# split_gd: тело — agent_panel_part4.gd
func _short_channel_error_text(response_code: int, body: PackedByteArray) -> String:
	return AgentPanelPart4._short_channel_error_text(self, response_code, body)


# split_gd: тело — agent_panel_part4.gd
func _on_node_rename_sync_response(result: int, response_code: int,
		body: PackedByteArray) -> void:
	AgentPanelPart4._on_node_rename_sync_response(self, result, response_code, body)


# split_gd: тело — agent_panel_part4.gd
func _on_node_rename_apply_response(result: int, response_code: int,
		body: PackedByteArray) -> void:
	AgentPanelPart4._on_node_rename_apply_response(self, result, response_code, body)


# split_gd: тело — agent_panel_part4.gd
func _on_safe_node_rename_pressed() -> void:
	AgentPanelPart4._on_safe_node_rename_pressed(self)


# split_gd: тело — agent_panel_part4.gd
func open_safe_node_rename(prefill_scene: String = "", prefill_node: String = "") -> void:
	AgentPanelPart4.open_safe_node_rename(self, prefill_scene, prefill_node)


# split_gd: тело — agent_panel_part5.gd
func _ensure_safe_node_rename_dialog() -> void:
	AgentPanelPart5._ensure_safe_node_rename_dialog(self)


# split_gd: тело — agent_panel_part5.gd
func _on_safe_node_rename_scene_browse() -> void:
	AgentPanelPart5._on_safe_node_rename_scene_browse(self)


# split_gd: тело — agent_panel_part5.gd
func _on_safe_node_rename_preview() -> void:
	AgentPanelPart5._on_safe_node_rename_preview(self)


# split_gd: тело — agent_panel_part5.gd
func _on_safe_node_rename_apply() -> void:
	AgentPanelPart5._on_safe_node_rename_apply(self)
