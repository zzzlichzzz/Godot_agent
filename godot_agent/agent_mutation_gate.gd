@tool
extends RefCounted

# ============================================================================
# AGENT MUTATION GATE — единственное место, где плагин применяет изменения.
#
# Первопричина появления файла. Записи шли из пяти независимых мест:
# исполнителя сцены, исполнителя ресурса, исполнителя настроек, панели
# (_sync_resource_uid) и обработчиков отката. Каждое само решало, как писать,
# и ни одно не отвечало на два вопроса, которые задаёт пользователь:
#
#   1. «что именно ты сейчас изменил?» — без журнала это не отвечалось вовсе,
#      и откат опирался на догадки сервера;
#   2. «как мне это отменить?» — история Godot пополнялась непредсказуемо,
#      и одна операция агента могла рассыпаться на десять шагов Ctrl+Z.
#
# Что делает шлюз:
#   - ВЫБИРАЕТ способ записи по типу ресурса (classify);
#   - ВЕДЁТ журнал: что, куда, каким способом;
#   - ОБОРАЧИВАЕТ правку, идущую через API Godot, в одну запись истории
#     отмены, чтобы одна операция агента = одно нажатие Ctrl+Z.
#
# Чего шлюз НЕ делает намеренно:
#   - не кладёт массовый рефакторинг в историю Godot. Пятьдесят файлов,
#     переписанных одним переименованием, в истории редактора превратились бы
#     в пятьдесят нажатий Ctrl+Z. Такой откат ведётся журналом плагина.
#   - не переписывает файлы текстом: запись идёт либо через PackedScene /
#     ResourceSaver (формат остаётся корректным), либо её делает Python.
# ============================================================================

## Способ записи, выбранный по типу ресурса.
enum WriteKind {
	SCRIPT,## одиночный .gd — пишет Python, шлюз обновляет только кэш
	SCENE,   ## .tscn/.scn — PackedScene
	RESOURCE,## .tres и прочее — ResourceSaver
	PROJECT_SETTINGS, ## project.godot — ProjectSettings
	BULK,    ## массовый рефакторинг — вне undo Godot, только журнал
}

const SCENE_EXTENSIONS := [".tscn", ".scn"]
const RESOURCE_EXTENSIONS := [".tres"]
const SCRIPT_EXTENSIONS := [".gd"]
const PROJECT_SETTINGS_FILE := "res://project.godot"

## Действие, которое шлюз умеет отменить. Живёт отдельно от шлюза, потому
## что UndoRedo умеет звать только метод объекта, а не Callable.
##
## Ключевой момент — _applied. Правка к моменту commit_action УЖЕ применена
## (её выполнил исполнитель), поэтому run() обязан быть холостым. Иначе
## commit_action(execute=true) выполнил бы запись второй раз и пользователь
## получил бы удвоенную правку. Отсюда же и redo: после unrun() run()
## применяет правку по-настоящему.
class UndoEntry extends RefCounted:
	var apply: Callable
	var revert: Callable
	var _applied: bool = true

	func run() -> void:
		if _applied:
			return
		if apply.is_valid():
			apply.call()
			_applied = true

	func unrun() -> void:
		if not _applied:
			return
		if revert.is_valid():
			revert.call()
		_applied = false


var _plugin: EditorPlugin
## Журнал операций агента: путь, вид записи, примечание, время.
var journal: Array[Dictionary] = []
var journal_depth: int = 0

var _undo_entry: UndoEntry = null
var _undo_context: Object = null
## Сколько записей истории плагин создал за сеанс: проверка правила
## «одна операция агента = одна запись» не должна гадать.
var undo_actions: int = 0


func configure(plugin: EditorPlugin) -> void:
	_plugin = plugin


## Вид записи для пути path. Это единственное место, где решается, КАК писать;
## дальше все исполнители спрашивают здесь и не решают сами.
func classify(path: String) -> WriteKind:
	if path == "":
		return WriteKind.BULK
	if path == PROJECT_SETTINGS_FILE:
		return WriteKind.PROJECT_SETTINGS
	var extension := path.get_extension().to_lower()
	var dotted := "." + extension
	if SCENE_EXTENSIONS.has(dotted):
		return WriteKind.SCENE
	if RESOURCE_EXTENSIONS.has(dotted):
		return WriteKind.RESOURCE
	if SCRIPT_EXTENSIONS.has(dotted):
		return WriteKind.SCRIPT
	# Каталог или незнакомое расширение: пишет Python, откат ведём журналом.
	return WriteKind.BULK


## Вид записи поимённо — для сообщений и журнала.
static func kind_name(kind: WriteKind) -> String:
	match kind:
		WriteKind.SCENE: return "scene"
		WriteKind.RESOURCE: return "resource"
		WriteKind.PROJECT_SETTINGS: return "project_settings"
		WriteKind.SCRIPT: return "script"
		_: return "bulk"


## Массовый ли это путь. Массовый рефакторинг в историю Godot не пишется
## сознательно: см. комментарий в шапке файла.
static func is_bulk(kind: WriteKind) -> bool:
	return kind == WriteKind.BULK or kind == WriteKind.SCRIPT


## Записать сцену root в scene_path через PackedScene.
##
## Так выглядит запись сцены у ВСЕХ, кто пишет сцены: исполнитель сцены и любой
## будущий код. Файловая система редактора узнаёт об изменении точечно, без
## полного пересчёта проекта.
func write_scene(root: Node, scene_path: String) -> Error:
	var packed := PackedScene.new()
	var pack_error := packed.pack(root)
	if pack_error != OK:
		return pack_error
	var save_error := ResourceSaver.save(packed, scene_path)
	record(scene_path, WriteKind.SCENE, error_string(save_error))
	notify_changed(scene_path)
	return save_error


## Записать ресурс resource в path через ResourceSaver.
func write_resource(resource: Resource, path: String) -> Error:
	var save_error := ResourceSaver.save(resource, path)
	record(path, WriteKind.RESOURCE, error_string(save_error))
	notify_changed(path)
	return save_error


## Сохранить project.godot через ProjectSettings.
func write_project_settings() -> Error:
	var save_error := ProjectSettings.save()
	record(PROJECT_SETTINGS_FILE, WriteKind.PROJECT_SETTINGS,
		error_string(save_error))
	notify_changed(PROJECT_SETTINGS_FILE)
	return save_error


## Открыть запись истории отмены на одну операцию агента.
##
## label   — что покажет пользователю в меню «Отменить»;
## context — корень сцены, чтобы запись попала в историю СЦЕНЫ, а не в общую
##           историю редактора (как у обычных правок в редакторе сцен);
## apply   — что сделать, если пользователь нажмёт «Повторить»;
## revert  — что сделать, если нажмёт «Отменить».
##
## Повторный вызов, пока запись не закрыта, игнорируется: одна операция агента
## не должна распадаться на две записи истории.
func begin_undo(label: String, apply: Callable, revert: Callable,
		context: Object = null) -> bool:
	if _undo_entry != null:
		return false
	var manager := _editor_undo_redo()
	if manager == null:
		return false
	var entry := UndoEntry.new()
	entry.apply = apply
	entry.revert = revert
	_undo_entry = entry
	_undo_context = context
	manager.create_action(label, UndoRedo.MERGE_DISABLE, context)
	# do-метод холостой: правка уже применена исполнителем. См. UndoEntry.
	manager.add_do_method(entry, "run")
	manager.add_undo_method(entry, "unrun")
	return true


## Закрыть запись истории отмены. Ровно одна на одну операцию агента.
func commit_undo() -> bool:
	var manager := _editor_undo_redo()
	if _undo_entry == null or manager == null:
		return false
	manager.commit_action()
	_undo_entry = null
	_undo_context = null
	undo_actions += 1
	return true


## Забыть несохранённую запись отмены, не показывая её в истории.
func abort_undo() -> void:
	_undo_entry = null
	_undo_context = null


## Открыта ли сейчас запись отмены. Исполнители проверяют это, чтобы не
## закоммитить чужую запись.
func undo_pending() -> bool:
	return _undo_entry != null


## Контекст текущей записи (корень сцены).
func undo_context() -> Object:
	return _undo_context


## Внести операцию в журнал плагина.
##
## before_hash/after_hash — хеши файла до и после записи. Пустой before_hash
## означает «файла не было»: появление файла тоже нужно уметь откатить.
func record(path: String, kind: WriteKind, note: String = "",
		before_hash: String = "", after_hash: String = "") -> void:
	journal.append({
		"path": path,
		"kind": kind_name(kind),
		"note": note,
		"before_hash": before_hash,
		"after_hash": after_hash,
		"msec": Time.get_ticks_msec(),
	})
	journal_depth = journal.size()


## Последняя запись журнала по пути path (сравнение без учёта регистра: на
## Windows это один и тот же файл).
func last_entry(path: String) -> Dictionary:
	var lowered := path.to_lower()
	for index in range(journal.size() - 1, -1, -1):
		if str(journal[index].get("path", "")).to_lower() == lowered:
			return journal[index]
	return {}


## Сообщить редактору об изменении одного файла. Точечно, без полного scan():
## полный пересчёт проекта стоил бы секунд ради одного файла.
func notify_changed(path: String) -> void:
	if path == "":
		return
	var efs := EditorInterface.get_resource_filesystem()
	if efs and efs.has_method("update_file"):
		efs.call("update_file", path)


## Менеджер истории отмены редактора.
##
## Имя важно: в плане задач было написано EditorInterface.get_undo_redo(), но
## такого метода в Godot 4.6 НЕТ — проверено get_method_list() у движка.
## Настоящее имя — get_editor_undo_redo(), и оно возвращает
## EditorUndoRedoManager. Ровно поэтому код из плана и не заработал бы.
func _editor_undo_redo() -> Object:
	return EditorInterface.get_editor_undo_redo()