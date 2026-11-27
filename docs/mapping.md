# Карта переноса: старый файл → новый модуль

Файл отвечает на вопрос «что на самом деле делает старый файл и куда он ложится».
Имена в старом проекте не считаются правдой: каждый файл прочитан по коду.

## Как получено

1. `docs/inventory.md` — машинная карта всех 370 файлов старого плагина: докстринг,
   классы, функции с сигнатурами, константы, упоминания инструментов, импорты.
   Собрана `ast` + регексами, без чтения вслепую.
2. Четыре субагента прочитали код по срезам: `godot_tools` A–H (16 файлов),
   `godot_tools` I–T (15 файлов), остальной Python (`main.py`, `api/`, `browser/`,
   `parsers/`, `server/`, `tools/`, `minilich/`), вся GDScript-часть (43 файла).
   Каждый файл проверялся по голове + списку функций, а не по названию.
3. По отчётам скелет перестроен **до** переноса кода: переименованы 5 модулей,
   удалены 4, добавлены 3, появились новые файлы (executor'ы, debugger-канал,
   части чата, `formats`, `runtime/`).

## Что изменилось в скелете после чтения кода

| Было в скелете | Стало | Почему |
|---|---|---|
| `project_text.files_list` | `project_text.tree` | старого инструмента `files_list` не существует: `project_tools` строит **дерево** и обзор проекта |
| `code_intel.symbols_card` | `code_intel.function_card` | инструмент называется `functions --card`, файл `function_card.py` |
| `code_intel.rename_analysis` | удалён | `analyze_rename` — это предпросмотр того же `usages`, отдельной фичи нет |
| `code_intel.arch_map` | удалён → `tools/check_limits.py` | `arch_map` — гейт лимитов **самого аддона агента**, а не возможность для проекта игрока |
| `context.librarian` | удалён | `librarian` — единственный владелец `ask`; второй модуль был бы копией |
| `editing.node_ops` | удалён → `scene_model.node_*` | `node_refactor.py` правит `.tscn` и скрипты: это сцены, а не «правки вообще» |
| `editing.symbol_refactor` | `editing.symbol_rename` | там только prepare/apply переименования; поиск ссылок живёт в `code_intel.usages` |
| `editing.split_scan` | `editing.split_py` | пила `.py` (`split_refactor.py`), рядом с `editing.split_gd` |
| `project_ops.resources` | `editing.resource_ops` | `resource_actions.py` — правка `.tres` через воронку записи |
| — | `editing.scene_ops` | `scene_actions.py` + `agent_scene_executor.gd`: схема правок сцены и исполнение |
| — | `project_ops.architecture` | `project_tools`: каркас проекта из `project.godot`, autoload, чистка висячих |
| — | `context.runtime_snapshot` | `runtime_debug.py`: read-only инспектор рантайма для чата (без MCP) |
| `python/formats/{gdscript,tscn}.py` | новые | вместо пяти парсеров `.gd` и четырёх разборов `.tscn` |
| `runtime/` (вне `editor/`) | новый каталог | игровая половина (`agent_runtime_bridge.gd`) — другой хост и жизненный цикл |

Итог: **43 модуля** в 9 областях, 569 файлов, 0 строк логики.

## python/godot_tools — 16 файлов (A–H)

| Файл | Что делает по коду | Новый дом | Делить? |
|---|---|---|---|
| `answer_judge.py` | Детерминированный судья ответа модели: разбирает `agent_action`, гоняет write-действия по overlay в памяти, отдаёт findings severity/category | `verification.action_judge` | да: findings / read-действия / write-overlay / выбор варианта |
| `arch_map.py` | Зоны и лимиты строк **самого аддона**, индекс «имя → файл», гейт новых файлов | `tools/check_limits.py` (не модуль) | да: правила зон / индекс имён / гейт |
| `file_refactor.py` | Переименование и перенос файлов с обновлением ссылок в `.gd/.tscn/.tres` и относительных путей: prepare без записи → apply с откатом | `editing.file_refactor`, `editing.paths_preview` | да: поиск ссылок / внутренние пути / prepare / перенос каталога / apply |
| `function_card.py` | Карточка символа: тело дословно + все символы с адресами + callers/наследники/override | `code_intel.function_card` | да: сбор членов / связи / рендер |
| `gather_context.py` | Ограниченный read-only пакет контекста под один follow-up, с бюджетом | `context.gather` | нет |
| `gd_api_cache.py` | Кэш реального API Godot (ClassDB JSON), миграция старого места, цепочка наследования | `engine_kb.*` | нет |
| `gd_api_check.py` | Проверка `.gd` против кэша: несуществующий член, число аргументов, сигнал в `connect()` | `verification.api_check` | нет |
| `gd_functions.py` | Список имён функций и выдача тел по отступам | `code_intel.functions` | нет (и только через `formats/gdscript.py`) |
| `gd_lint.py` | Текстовый линт: скобки, кавычки, отступы, двоеточия, узкая проверка типов | `verification.gd_lint` | нет |
| `gd_semantic_parser.py` | Токенайзер GDScript + объявления с точными диапазонами | `formats/gdscript.py` | нет |
| `godot_headless_validation.py` | Копия проекта, overlay операций, GDScript-харнесс, `result.json`, код возврата | `verification.headless` | да: overlay/копия / харнесс / разбор результата |
| `high_level_actions.py` | Компиляция «действия» в структуру правки (settings) | `project_ops.settings_*` | нет |
| `history_manager.py` | Журнал записей, квитанции, откат, история изменений | `editing.rollback` | да: журнал (в `substrate/store`) / подготовка отката / публичная часть |
| `librarian.py` | Карта кода проекта, фрагменты, вызовы — единственный `ask` | `context.ask` | да: индекс / поиск фрагментов / вызовы / рендер |
| `node_refactor.py` | Переименование, перенос, удаление узлов с правкой скриптов и `.tscn` | `scene_model.node_rename/node_reparent/node_delete` | да: разбор .tscn (в kernel) / план / применение |
| `project_settings_actions.py` | Строгая схема правок `project.godot` (input, autoload, окно), digest, prepare | `project_ops.settings_set`, `settings_get` | нет |

## python/godot_tools — 15 файлов (I–T)

| Файл | Что делает по коду | Новый дом | Делить? |
|---|---|---|---|
| `project_tools.py` | Всё сразу: политика путей (`can_read/write`, `is_addon`), fs-примитивы, move/copy с hardlink и транзакцией смены регистра, дерево и обзор проекта, поиск подстроки, `describe_scene`, каркас архитектуры, снапшоты и диффы | разъезжается по 8 адресам (см. «Разбиение») | да, обязательно: 8 частей |
| `resource_actions.py` | Строгая схема правок `.tres` (sub_resource, theme, операции), canonical digest, хэш-гвард; C.24 D18/D19: собственный pure section/span byte producer и единственный replace_raw шаг общей WAL-воронки, native projection oracle | `editing.resource_ops` | нет |
| `runtime_checks.py` | Протокол проверки игры: шаги ввода, ассерты с допуском, request/result, разбор ошибок из лога | `verification.runtime_checks` | нет |
| `runtime_debug.py` | Read-only инспектор рантайма: секции снапшота, выбор сессии, вклейка статуса в промпт | `context.runtime_snapshot` | нет |
| `scene_actions.py` | Схема структурных правок сцены, `normalize_variant`, prepare, staged-файл сцены | `editing.scene_ops` | нет |
| `scene_deps.py` | Разбор `.tscn`: ext-ресурсы, узлы, connections, поиск `_on_*`, автодобавление `[connection]` | `scene_model.scene_deps`, `scene_model.connections` | нет |
| `split_gd.py` | Пила `.gd`: токенайзер, инвентарь, группы, план, применение, `--check-only` | `editing.split_gd` | да: токены/план/применение |
| `split_refactor.py` | Пила `.py` через `ast`: ссылки, группы, дубли имён, донор становится фасадом | `editing.split_py` | да: scan/plan/apply |
| `symbol_refactor.py` | Чистый фасад: ~80 реэкспортов из part1–3 + две функции упаковки | файла не будет | — |
| `symbol_refactor_data.py` | Две константы: ключевые слова GDScript, виды объявлений | `formats/gdscript.py` | — |
| `symbol_refactor_part1.py` | Владение символом (top-level/скоуп/вложенные классы), типизированные получатели, наследники, план переноса файла с `.uid`, правки в `.tscn` | `code_intel.usages` + `editing.symbol_rename` | да: скоуп / сцена / файл |
| `symbol_refactor_part2.py` | Доказательство безопасности ссылок (strict/probable), коллизии, занятость имени в проекте и ClassDB, `find_references`, `analyze_rename` | `code_intel.usages` | да: доказательство / отчёт |
| `symbol_refactor_part3.py` | `prepare_rename` без записи и `apply_prepared_rename` с откатом всех файлов и журналом | `editing.symbol_rename` | да: prepare / apply |
| `transaction_actions.py` | Воронка записи: prepare → stale-хэши → apply → rollback, квитанции | `editing.write_preview`, `write_apply`, `rollback` | нет |
| `tscn_lint.py` | Линт сцен: порядок секций, uid, `load_steps`, `Type.new()` → SubResource, топосорт, циклы, типы против ClassDB | `verification.tscn_lint` + `formats/tscn.py` | да: структура / ресурсы / синтаксис / типы |

## Остальной Python (208 файлов)

| Файл / группа | Что делает по коду | Куда | В 1-ю версию? |
|---|---|---|---|
| `main.py` (297 КБ, 4697 строк) | Flask-хост панели: 38 роутов, диалог с моделью, разбор `agent_action`, сам гоняет домен и пишет через журнал | `channels/http/routes_*` + `assistant.chat` + `editing.*` | да, как набор маршрутов |
| `tools/agent_bridge.py` (142 КБ) | Второй хост того же домена без сервера: сам ищет корень и токен, **сам считает политику доступа**, сам ведёт квитанции `plan_id` | `protocol/dispatch` + `kernel/paths` | да, политика одна |
| `tools/godot_agent_mcp.py` | Чистый транспорт: 24 tool → argv → мост | `channels/mcp` | да |
| `tools/arch_audit.py` | Аудит структуры старого репо | `tools/check_limits.py` | как инструмент |
| `tools/release_prepare.py` | Сборка релиза | `tools/package.py` | как инструмент |
| `tools/{capture_*,arena_*,audit_aistudio_live,verify_*,make_search_golden}.py` | Одноразовые съёмщики трафика и золотых данных | — | нет |
| `api/openai_compat.py`, `api/anthropic_compat.py` | Транспорт к моделям: SSE, отмена, типы ошибок | `substrate/llm/api/` | да, если есть API-режим |
| `api/providers.py`, `api/model_cache.py`, `api/api_keys.py` | Реестр провайдеров, кэш моделей, ключи в `%APPDATA%` | `substrate/llm/api/providers_catalog.py`, `llm/models.py`, `llm/secrets.py` | да |
| `api/catalog.py`, `api/doh.py` | Каталог цен models.dev, DNS-over-HTTPS | — | нет |
| `backends/api_backend.py` | Сборка messages, стрим в панель, разбор `agent_action`, история, ошибки → текст | `assistant.routing` + `substrate/llm` | да |
| `backends/browser_backend.py`, `browser/*` (7), `parsers/*` (7) | Selenium/CDP: Chrome, вкладки, DOM и сетевые парсеры пяти сайтов | `substrate/llm/browser` | нет (Q-08) |
| `minilich/*` (8) | Локальная numpy-модель, обучение, GitHub-датасет | — | нет (Q-07) |
| `server/chat_routes.py` | Маршруты чата: план, многочастные ответы, применение шагов | `channels/http/routes_chat.py` | да |
| `server/agent_prompts.py` | Системные промпты и их сборка | `assistant/shared/prompts.py` | да |
| `server/api_history.py`, `server/chat_store.py` | История и хранилище чатов | `assistant.history` | да |
| `server/editor_context.py` | Контекст редактора для запроса | `context.editor_context` | да |
| `server/md_to_bbcode.py`, `rate_limit.py`, `server_auth.py`, `port_guard.py` | Рендер ответа, лимиты, токен, занятость порта | `channels/http/` | да |
| `server/dashboard.py`, `server/server_state.py` | Дев-журнал, состояние драйвера браузера | — | нет |
| `server/log_reader.py` | Чтение лога Godot и ошибок рантайма | `verification.headless`, `context.runtime_snapshot` | да |
| `selfcheck.py`, `_bootstrap.py` | Самопроверка на фейковых парсерах; хак `sys.path` | — | нет (пакеты вместо хака) |
| `python/tests/` (168 файлов) | Тесты старого поведения | источник кейсов в `fixtures/corpus` | только кейсы |

## Редактор (43 файла GDScript)

| Файл | Что делает по коду | Куда | Делить? |
|---|---|---|---|
| `agent_entry.gd` | `EditorPlugin`: док, меню, контекст-меню FS и сцены, debugger | `editor/core/lifecycle.gd` | нет |
| `plugin_universal.gd` | Второй претендент на вход (шапка `agent_entry` говорит, что `plugin.cfg` указывает на него) | один вход, файл не переносим | — |
| `agent_server.gd` | Реестр URL и разделов, токен проекта, pid сервера | `bridge/server/endpoints.gd` + `core/config.gd` | да |
| `agent_server_link.gd` | `HTTPRequest`-клиент: очередь, короткий канал, автостарт `.exe`, ретраи | `bridge/server/session.gd` + `core/process_supervisor.gd` | да |
| `agent_runtime_bridge.gd` | Работает **в игре**: шаги проверки, снимок дерева, свойства, метрики, ошибки | `runtime/probe.gd`, `runtime/report.gd` | да |
| `agent_runtime_debugger.gd` | Канал editor ↔ runtime через `EditorDebuggerPlugin` | `bridge/server/debugger_session.gd` | нет |
| `agent_headless_validator.gd` | `SceneTree`-скрипт: manifest → load → result.json | `editor/harness/validate.gd` | нет |
| `agent_mutation_gate.gd` | Единственная точка записи: классификация пути, запись сцены/ресурса/настроек, undo | `verbs/guard/mutation_gate.gd` | да (`classify` → python) |
| `agent_scene_executor.gd` | prepare/execute операций сцены, detached load, сохранение, откат | `verbs/scene/scene_executor.gd` | да |
| `agent_resource_executor.gd` | Операции над `Resource`: temp-save, UID, копирование/переименование файла | `verbs/resource/resource_verbs.gd` | да |
| `agent_project_settings_executor.gd` | `simulate → apply → restore` над `ProjectSettings` | `verbs/project/settings_executor.gd` | да |
| `agent_integration_signals.gd` | Подписки на `script_changed/scene_saved`, перехват ручного rename | `core/editor_hooks.gd` | нет |
| `agent_editor_context.gd` | Статический снимок редактора для чата | `verbs/editors/context_snapshot.gd` | нет |
| `agent_theme.gd` | Цвета, шрифты, StyleBox, экранирование BBCode | `ui/theme/agent_theme.gd` | нет |
| `agent_updater.gd` | Проверка релиза, скачивание, перезапись аддона, рестарт сервера | `core/updater.gd` (установка → python) | да |
| `agent_chat_view.gd` | Визуал чата: пузыри, «печать», стрим, план, диффы, подтверждения | `ui/chat/*` (5 файлов) | да |
| `agent_panel.gd` + `part1..5` (265 КБ) | Разрезанный ножом один класс: состояние, ~40 URL, 200+ тонких обёрток, три экзекутора, план, перезагрузка сцен, настройки | `ui/panel/{shell,send_flow,confirm_flow,plan_flow,settings_toggles,rename_flow,scene_reload,tab_sync}` + `verbs/glue/executor_calls.gd` + `ui/dialogs/*` | да, радикально |
| `agent_start_screen.gd` (204 КБ) | Стартовый экран: чаты, сайты, ключи, выбор модели, статус | `ui/start/*` (7 файлов) | да |
| `agent_locale.gd` (86 КБ) | Русские и английские строки + выбор языка | `core/i18n/{ru,en,locale}.gd` | да |
| Карточки (5), `AgentStatusBar`, `agent_highlight` | Виджеты сообщений, диффов, плана; статус; подсветка | `ui/cards/*`, `ui/status/status_bar.gd`, `ui/editor/highlight.gd` | нет |
| `agent_api_export.gd` | Экспорт настроек API наружу | уточнить при переносе | ? |

## Разбиение крупных файлов

Ты был прав: делить придётся почти всё крупное. Ниже — по фактам из кода, а не по «хочется».

| Старый файл | Части (новые файлы) |
|---|---|
| `project_tools.py` (100 КБ) | 1. `kernel/paths.py` — политика путей: `can_read/can_write/can_reference`, `is_addon/is_agent`; 2. `project_text/tree` — обход, `policy_snapshot`, дерево проекта; 3. `project_text/read` — read/create/patch, атомарная запись; 4. `editing/file_refactor` — move/copy, hardlink, транзакция смены регистра каталога; 5. `project_text/search` — поиск подстроки, расширения, сниппеты; 6. `scene_model/tree` — `describe_scene`; 7. `project_ops/architecture` — `project.godot`, autoload, обзор; 8. `kernel/diff.py` — снапшоты, `unified_diff_text`, дифф-превью |
| `tscn_lint.py` (74 КБ) | `tscn_structure` (порядок секций, uid, `load_steps`), `tscn_resources` (`Type.new()` → SubResource, топосорт, циклы), `tscn_syntax` (свойства, скобки, `parent=`, connections), `tscn_types` (сверка с ClassDB) |
| `split_gd.py` | `gd_split_tokens` (токенайзер, инвентарь), `gd_split_plan` (группы, план), `gd_split_apply` (`--check-only`, применение) |
| `split_refactor.py` | `py_split_scan` (ссылки, импорты, строки), `py_split_plan` (группы, дубли имён), `py_split_apply` (фасад, применение) |
| `symbol_refactor_part1.py` | `symbol_scope` (владение, скоупы, наследники), `symbol_scene_edits` (правки свойств и connections), `symbol_file_rename` (план переноса файла с `.uid`) |
| `symbol_refactor_part2.py` | `symbol_ref_proof` (безопасность ссылок, коллизии, имена проекта и ClassDB), `symbol_ref_report` (`find_references`, `analyze_rename`) |
| `symbol_refactor_part3.py` | `symbol_prepare` (`prepare_rename` без записи), `symbol_apply` (применение, откат, журнал) |
| `agent_panel.gd` + `part1..5` | `shell` (только каркас и узлы), `send_flow`, `confirm_flow`, `plan_flow`, `settings_toggles`, `rename_flow`, `scene_reload`, `tab_sync`, `verbs/glue/executor_calls`, `ui/dialogs/{safe_rename,safe_node_rename}` |
| `agent_start_screen.gd` (204 КБ) | `home`, `chats_list`, `sites_list`, `status_loading`, `api_settings`, `api_picker`, `api_catalog_fmt` |
| `agent_locale.gd` (86 КБ) | `i18n/ru.gd`, `i18n/en.gd`, `i18n/locale.gd` |
| `agent_chat_view.gd` | `chat_stream`, `chat_messages`, `cards_factory`, `chat_plan_diff`, `chat_confirm` |
| `librarian.py` | индекс, поиск фрагментов, вызовы, рендер ответа |
| `history_manager.py` | журнал (`substrate/store/journal.py`), подготовка отката, публичная часть |
| `file_refactor.py` | поиск ссылок, внутренние пути, prepare, перенос каталога, apply |
| `function_card.py` | сбор членов, связи (callers/наследники), рендер |
| `answer_judge.py` | findings, read-действия, write-overlay, выбор варианта |
| `godot_headless_validation.py` | overlay/копия проекта, GDScript-харнесс, разбор результата |

Что **не** надо делить: `gather_context` (370 строк, одна ответственность), `gd_lint`, `gd_api_check`, `gd_functions`, `transaction_actions`, `resource_actions`, `scene_actions`, `scene_deps`, `runtime_checks`, `runtime_debug`, `project_settings_actions`.

## Что дублировалось (и почему новая раскладка это убирает)

| Дубль | Где было | Куда уходит |
|---|---|---|
| Политика доступа | `main.py` (`_can_read_path`, `_can_write_path`, `_with_rename_policy`) **и** `agent_bridge.py` (`_access_policy`, `_assert_agent_path_writable`) | одна `kernel/paths.py` |
| Два хоста домена | `main.py` (Flask) и `agent_bridge.py` (MCP) | `protocol/dispatch.py` — один, каналы только переводят протокол |
| Разбор `agent_action` | `parsers/parser_base.py`, `backends/api_backend.py`, `main._describe_action` | `assistant/shared/message_model.py` |
| Пять парсеров `.gd` | `gd_functions._FUNC_RE`, `gd_lint`, `gd_api_check`, `librarian._gd_signatures`, `gd_semantic_parser` | `formats/gdscript.py` |
| Четыре разбора `.tscn` | `project_tools.describe_scene`, `node_refactor.parse_tscn_structure`, `scene_deps`, `tscn_lint` | `formats/tscn.py` |
| Чтение файла с BOM + RLock | `file_refactor` ≡ `node_refactor` (побайтово одинаково) | `substrate/fs/disk_fs.py`, `kernel/paths.py` |
| sha256 | пять мест: `file_refactor`, `node_refactor`, `godot_headless_validation`, `history_manager`, `project_settings_actions` | `kernel/ids.py` |
| Транзакция prepare/apply/stale | `file_refactor` ↔ `node_refactor` (свои классы ошибок на каждую копию) | `editing/write_preview` + `substrate/store/plan_store.py` |
| Валидаторы схем | `high_level_actions` ↔ `project_settings_actions` | `project_ops/shared/settings_model.py` |
| Overlay-патч | `answer_judge` заново воспроизводит `project_tools.patch_project_file` | `substrate/fs/memory_fs.py` |
| Сбор слоёв контекста | `gather_context` ↔ `librarian` | `context/shared/{snippets,ranking}.py` |
| Словарь действий | `answer_judge` ↔ `parser_base._KNOWN_ACTIONS` | контракт `contract/capabilities/*.json` |
| Выборка членов класса | `gd_api_cache` ↔ `librarian._godot_api` | `engine_kb/shared/catalog_index.py` |
| Теневая история сцен | `agent_panel_part2` ↔ `agent_mutation_gate` | один `verbs/guard/mutation_gate.gd` |

## Что не переносим

`minilich/*` (локальная модель), `browser/*` и `parsers/*` (Selenium/CDP, отложено), `api/{catalog,doh}` (цены и обход DNS), `server/{dashboard,server_state,port_guard}`, одноразовые съёмщики из `python/tools`, `selfcheck.py`, `python/tests` как тесты (только кейсы), `plugin_universal.gd` (второй вход), `symbol_refactor.py` (фасад пересобирается естественно).

## Итог

- Прочитано по коду: 43 `.gd` + 31 файл `godot_tools` + `main.py`, `agent_bridge.py`, `godot_agent_mcp.py`, каталоги `api/`, `backends/`, `browser/`, `parsers/`, `server/`, `tools/`, `minilich/`.
- 43 модуля в 9 областях, 569 файлов, 0 строк логики.
- Делить нужно 16 старых файлов; 11 файлов делить не нужно.
- 14 видов дублирования получают по одному адресу.



