@tool
extends Object

# ---------------------------------------------------------------------------
# Локализация плагина (RU/EN).
# Выбранный язык хранится в user://godot_agent_lang.txt и переживает
# перезапуск редактора. По умолчанию — русский.
#
# Использование из любого скрипта аддона:
#   var L = load("...папка аддона.../agent_locale.gd")
#   L.t("send")      -> "Отправить" / "Send"
#   L.get_lang()     -> "ru" / "en"
#   L.set_lang("en")
# ---------------------------------------------------------------------------

const LANG_FILE := "user://godot_agent_lang.txt"

static var _cur: String = ""

const RU := {
    "dock_title": "ИИ Агент",
    "title": "Браузерный ИИ-Агент",
    "hint": "С чего начнём?",
    "btn_load": "Загрузиться",
    "btn_new": "Новый чат",
    "hdr_chats": "Сохранённые чаты",
    "hdr_sites": "Выберите сайт (нейросеть)",
    "back": "Назад",
    "no_chats": "Пока нет сохранённых чатов. Начните новый!",
    "untitled": "Без названия",
    "site_fallback": "Сайт",
    "sites_empty": "Список сайтов пуст (сервер запущен?).",
    "add_own": "Добавить свою страницу (скоро)",
    "add_own_tip": "В разработке: универсальный парсер подберёт алгоритм чтения страницы.",
    "support": "Поддержать автора:",
    "support_tips": "Чаевые (CloudTips)",
    "support_boosty": "Boosty",
    "connecting": "Подключение к серверу…",
    "srv_wait_boot": "Сервер ещё запускается — ваше действие выполнится автоматически, как только он поднимется…",
    "srv_dead": "Сервер агента не отвечает. Запустите его вручную (godot_agent_server.exe или python main.py).",
    "srv_search": "Ищу сервер…",
    "srv_not_found": "Не нашёл сервер. Убедитесь, что файл godot_agent_server.exe лежит по пути res://addons/Godot_agent/godot_agent/python/dist/ или res://addons/godot_agent/python/dist/, либо запустите python main.py вручную.",
    "srv_start": "Запускаю сервер…",
    "srv_fail": "Сервер так и не поднялся. Проверьте окно сервера (консоль).",
    "srv_connecting_n": "Подключение… (ещё до %d с)",
    "system_ready": "Система готова. Работаем через локальный Браузерный ИИ-Агент!",
    "send": "Отправить",
    "sending": "Ждём...",
    "advanced_show": "⚙️ Дополнительно",
    "advanced_hide": "⚙️ Скрыть доп. инструменты",
    "input_placeholder": "Спросите или дайте указание (Ctrl+Enter для отправки)...",
    "allow": "Разрешить",
    "reject": "Отклонить",
    "pending_default": "Агент хочет выполнить действие...",
    "reinit": "Переинициализировать (переслать структуру проекта)",
    "rollback": "Откатить последнее изменение",
    "log_errors": "🐞 Ошибки запуска игры",
    "menu": "Меню",
    "tip_new": "Новый чат (новая страница в браузере)",
    "tip_rename": "Переименовать чат",
    "tip_delete": "Удалить чат из списка",
    "tip_menu": "В начало (выбор чата/сайта)",
}

const EN := {
    "dock_title": "AI Agent",
    "title": "Browser AI Agent",
    "hint": "Where shall we start?",
    "btn_load": "Load a chat",
    "btn_new": "New chat",
    "hdr_chats": "Saved chats",
    "hdr_sites": "Choose a site (AI)",
    "back": "Back",
    "no_chats": "No saved chats yet. Start a new one!",
    "untitled": "Untitled",
    "site_fallback": "Site",
    "sites_empty": "Site list is empty (is the server running?).",
    "add_own": "Add your own page (soon)",
    "add_own_tip": "In development: a universal parser will learn how to read the page.",
    "support": "Support the author:",
    "support_tips": "Tips (CloudTips)",
    "support_boosty": "Boosty",
    "connecting": "Connecting to the server…",
    "srv_wait_boot": "The server is still starting — your action will run automatically as soon as it is up…",
    "srv_dead": "The agent server is not responding. Start it manually (godot_agent_server.exe or python main.py).",
    "srv_search": "Looking for the server…",
    "srv_not_found": "Server not found. Make sure godot_agent_server.exe is located at res://addons/Godot_agent/godot_agent/python/dist/ or res://addons/godot_agent/python/dist/, or run python main.py manually.",
    "srv_start": "Starting the server…",
    "srv_fail": "The server never came up. Check the server console window.",
    "srv_connecting_n": "Connecting… (up to %d s left)",
    "system_ready": "System ready. Running through the local Browser AI Agent!",
    "send": "Send",
    "sending": "Waiting...",
    "advanced_show": "⚙️ Advanced",
    "advanced_hide": "⚙️ Hide advanced tools",
    "input_placeholder": "Ask or give an instruction (Ctrl+Enter to send)...",
    "allow": "Allow",
    "reject": "Reject",
    "pending_default": "The agent wants to perform an action...",
    "reinit": "Reinitialize (resend project structure)",
    "rollback": "Roll back the last change",
    "log_errors": "🐞 Game launch errors",
    "menu": "Menu",
    "tip_new": "New chat (a new page in the browser)",
    "tip_rename": "Rename chat",
    "tip_delete": "Delete chat from the list",
    "tip_menu": "Back to start (choose chat/site)",
}


static func get_lang() -> String:
    if _cur == "":
        _cur = _read_saved()
    return _cur


static func set_lang(lang: String) -> void:
    _cur = "en" if lang == "en" else "ru"
    var f := FileAccess.open(LANG_FILE, FileAccess.WRITE)
    if f:
        f.store_string(_cur)
        f.close()


static func _read_saved() -> String:
    if FileAccess.file_exists(LANG_FILE):
        var f := FileAccess.open(LANG_FILE, FileAccess.READ)
        if f:
            var v := f.get_as_text().strip_edges()
            f.close()
            if v == "en":
                return "en"
    return "ru"


static func t(key: String) -> String:
    var d: Dictionary = EN if get_lang() == "en" else RU
    if d.has(key):
        return str(d[key])
    if RU.has(key):
        return str(RU[key])
    return key
