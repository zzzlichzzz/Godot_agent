# Проблемы использования агента нейросетями (срез на 2026-11-26)

Документ фиксирует только выявленные несоответствия, ограничения и точки отказа по текущему состоянию кода и контрактов — без вариантов решения и без рекомендаций по приоритетам.

---

## 1. Внутренний чат-контур (`PRIMING_TEMPLATE` ↔ `assistant_turn` / `chat`)

### 1.1. В системный промпт вместо дерева файлов и архитектуры передаются метаданные секции `project`
- **Где:**
  - `python/modules/assistant/write/operations/turn.py` (строки 27–28)
  - `python/modules/assistant/chat/app.py` (строки 37–40)
  - `python/modules/context/gather/domain/core.py` (`project_section`, строки 91–94)
  - `python/substrate/assistant/chat_gateway.py` (`ChatGateway.system_prompt`, строки 44–47)
  - `python/substrate/llm/api/agent_prompts.py` (`PRIMING_TEMPLATE`, строки 205–211)
- **Суть проблемы:** оба цикла вызывают `context` с `sections=['project']` и передают сериализованный JSON как аргумент `tree=...` в `gateway.system_prompt(...)`. Секция `project` содержит только `{"root", "project_file", "engine", "source"}` и не содержит списка файлов проекта. Параметр `architecture` при вызове из обоих модулей остаётся значением по умолчанию `""`.
- **Эффект:** модель в `assistant_turn` и `chat` стартует без карты файлов проекта и без описания его архитектуры, несмотря на прямые отсылки к ним в `PRIMING_TEMPLATE`.

### 1.2. Инструмент `list_files` описан в `PRIMING_TEMPLATE`, но отсутствует в обработчиках
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (пункт 8, строки 99–100)
  - `python/modules/assistant/write/operations/turn.py` (`READ`, строки 6–7; отказ на строках 70–71)
  - `python/modules/assistant/chat/domain/core.py` (`READ_ACTIONS`, строки 7–8; `read_requests`, строки 17–35)
- **Суть проблемы:** `PRIMING_TEMPLATE` прямо инструктирует модель использовать действие `list_files` (с параметром `dir`), но `list_files` отсутствует в словарях чтения и записи обоих циклов.
- **Эффект:** попытка модели запросить дерево/список каталогов через `list_files` завершается отказом `AppError('denied', 'действие не даёт разрешения: list_files')` в `assistant_turn` или ответом `Неизвестное действие: list_files` в `chat`.

### 1.3. Действие `gather_context` не передаёт параметры из промпта и сводится к секции `project`
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (пункт 12, строки 107–108)
  - `python/modules/assistant/write/operations/turn.py` (`read_args`, строка 16)
  - `python/modules/assistant/chat/domain/core.py` (`read_requests`, строка 30)
  - `python/substrate/context/gather_context.py` (`validate_request`, строки 39–68)
- **Суть проблемы:** `PRIMING_TEMPLATE` описывает `gather_context` с параметрами `query`, `symbols`, `godot_api`, `active_scene`, `diagnostics`, `max_chars` как замену цепочки вызовов разведки. При этом `turn.py` игнорирует все аргументы и вызывает `context` с `{'sections': ['project']}` (`chat` — с `{'sections': ['project', 'tools']}`).
- **Эффект:** модель получает ответ, не содержащий ни запрошенных символов, ни сведений Godot API, ни активной сцены, ни диагностик.

### 1.4. `find_symbol_usages` и `analyze_rename` описаны в `PRIMING_TEMPLATE`, но отсутствуют в `assistant_turn` и `chat`
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (пункты 13a, 13b, строки 115–120)
  - `python/modules/assistant/write/operations/turn.py` (`READ`, строки 6–7)
  - `python/modules/assistant/chat/domain/core.py` (`READ_ACTIONS`, строки 7–8)
- **Суть проблемы:** в реестре есть публичные инструменты `usages` и `analyze_rename`, однако они не включены в `READ`/`READ_ACTIONS` циклов `assistant_turn` и `chat`.
- **Эффект:** при выполнении инструкции промпта вызвать `find_symbol_usages` до `rename_symbol` или `analyze_rename` перед переименованием запрос отклоняется (`denied` в `assistant_turn`, `Неизвестное действие` в `chat`).

### 1.5. Потеря аргументов и принудительное усечение в `read_file`, `read_function`, `search_project`, `ask_librarian`, `list_scene`
- **Где:**
  - `python/modules/assistant/write/operations/turn.py` (`read_args`, строки 11–18; ветка `paths`, строки 44–46)
  - `python/modules/assistant/chat/domain/core.py` (`read_requests`, строки 17–34)
  - `python/modules/code_intel/functions/tools.py` (`FUNCTIONS.args`, строки 34–40)
- **Суть проблемы:**
  - В `turn.py` при передаче `paths: [...]` (формат, указанный в пункте 1 `PRIMING_TEMPLATE`) каждый файл читается с жёстким `max_chars=6000` (независимо от числа файлов в списке и без учёта `30000` для одиночного `path`).
  - В `turn.py` для `read_function` формируется `'names': action.get('names') or [action.get('name')]`. Если модель вызывает `read_function` без `names` и `name` (для получения списка функций, как описано в пункте 2 `PRIMING_TEMPLATE`), отправляется `names: [None]`, что не проходит схему `items: {"type": "string"}` инструмента `functions`.
  - В `chat/domain/core.py` для `read_function` передаётся только `path` — поля `names`/`name` отбрасываются полностью, из-за чего извлечение тел конкретных функций в режиме `chat` невозможно.
  - В `turn.py` для `search_project` и `ask_librarian` передаётся только `query` — отбрасываются `max_results`, `context_lines`, `case_insensitive`, `budget_chars`. В `chat` для `search_project` также передаётся только `query`.

### 1.6. Действие `copy_file` описано в `PRIMING_TEMPLATE`, но не поддерживается в `assistant_turn` и `NativePlanner`
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (пункт 6, строки 95–96)
  - `python/modules/assistant/write/operations/turn.py` (`WRITE`, строки 8–9; отказ на строках 70–71)
  - `python/substrate/assistant/native_planner.py` (`_prepare`, строки 51–84)
- **Суть проблемы:** `copy_file` отсутствует и в множестве `WRITE` модуля `assistant.write`, и в ветках диспетчеризации `NativePlanner._prepare`.
- **Эффект:** вызов `copy_file` в `assistant_turn` немедленно завершает ход исключением `AppError('denied', 'действие не даёт разрешения: copy_file')`.

### 1.7. Действие `inspect_runtime` описано в `PRIMING_TEMPLATE`, но не имеет реализации в обработчиках
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (пункт 19, строки 152–153)
  - `python/modules/assistant/write/operations/turn.py` (строки 6–9)
  - `docs/parity.md` (`context.runtime_snapshot`, строка 80 — статус `skeleton`)
- **Суть проблемы:** в `PRIMING_TEMPLATE` описана схема и правила вызова `inspect_runtime`, при этом в `turn.py` (и среди активных публичных инструментов) обработчик отсутствует.
- **Эффект:** попытка вызвать `inspect_runtime` приводит к `denied` (`действие не даёт разрешения: inspect_runtime`).

### 1.8. Текстовый формат `agent_action` + `===DONE===` + проверка `judge` на каждом ходе
- **Где:**
  - `python/substrate/llm/api/agent_prompts.py` (строки 74–81, 158–169)
  - `python/modules/assistant/write/operations/turn.py` (строки 26–76)
  - `python/modules/assistant/chat/domain/core.py` (`run_turn`, строки 38–79)
  - `python/substrate/assistant/interactive_gateway.py` (строки 47–63, 151–160)
- **Суть проблемы:** вместо нативного tool calling модель обязана формировать текстовые блоки ````agent_action```` с ручными маркерами `===FILE_1===`/`_lines` и строкой `===DONE===`, а пропуск или ошибка разбора блока расходует ограниченный бюджет `max_turns=8` на повторные запросы.

---

## 2. Инструменты поиска и чтения (публичный контракт и MCP)

### 2.1. Отсутствует публичный инструмент получения списка/дерева файлов проекта
- **Где:**
  - `python/modules/project_text/tree/module.py` (строки 5–7)
  - `contract/capabilities/` (35 публичных контрактов, инструмента `tree` / `list_files` среди них нет)
- **Суть проблемы:** модуль `project_text.tree` уже реализован и принимает параметры `subdir`, `max_depth`, `max_entries`, `only_exts` (`python/modules/project_text/tree/app.py`, строки 6–30), но объявлен только как `internal_services=("project_text.tree",)` с пустым `provides_tools`.
- **Эффект:** внешний клиент (MCP, HTTP `/tools/call`, CLI) не имеет способа получить структуру каталогов и список файлов проекта через инструменты агента.

### 2.2. В инструменте `read` нет чтения по диапазону строк или смещению
- **Где:**
  - `python/modules/project_text/read/tools.py` (строки 4–17)
  - `python/modules/project_text/read/domain/core.py` (строки 4–7)
- **Суть проблемы:** `read` принимает только `path` и `max_chars` (до 200 000 символов от начала файла) и обрезает текст по префиксу `text[:max_chars]`. Параметры `start_line`, `end_line` или `offset` отсутствуют.
- **Эффект:** при усечении (`truncated: true`, в том числе при лимите `6000` символов в `turn.py`) нейросеть не может прочитать середину или конец файла отдельным запросом.

### 2.3. Ограничения фильтрации и пагинации в `search`
- **Где:**
  - `python/modules/project_text/search/tools.py` (строки 11–90)
- **Суть проблемы:** `search` выполняет только буквальный поиск подстроки; отсутствуют регулярные выражения, фильтр включения по каталогу/расширению (есть только `exclude_rel_prefixes`) и смещение/курсор для получения следующих результатов при `truncated: true`.
- **Эффект:** на большом проекте при срабатывании квоты `max_results` модель не может дочитать оставшиеся совпадения или сузить поиск до одной папки/типа файлов.

### 2.4. Зависимость `usages` и `analyze_rename` от точного `declaration` вида `res://path.gd:line`
- **Где:**
  - `python/modules/code_intel/usages/tools.py` (обязательный параметр `declaration`)
  - `contract/capabilities/usages.json`, `contract/capabilities/analyze_rename.json`
- **Суть проблемы:** оба инструмента требуют точный строковый локатор объявления (`res://...:строка`), который предварительно нужно искать другими вызовами (`search`/`functions`).

---

## 3. Инструменты правки и интеграция с профилем редактора

### 3.1. Для внешнего MCP-клиента нет типизированного инструмента произвольной правки/создания файлов
- **Где:**
  - `python/modules/editing/write_preview/tools.py` (строки 101–140)
  - `python/modules/editing/file_refactor/module.py` (`provides_tools=()`)
  - `python/modules/editing/resource_ops/module.py` (`provides_tools=()`)
  - `python/modules/assistant/write/operations/common_tool_defs.py` (строка 12: `ACTION`)
- **Суть проблемы:**
  - `write_preview` / `write_apply` покрывают только переименование символов (`kind`, `old_name`, `new_name`, `declaration`).
  - `editing.file_refactor` и `editing.resource_ops` не экспортируют публичных инструментов.
  - `split_apply` ограничен планами `split_plan` для `.py`.
  - В результате единственная точка подготовки произвольных файловых правок через MCP — `assistant_plan`, схема которого (`ACTION`) описывает лишь `{"action": string}` с `additionalProperties: True`, без перечня допустимых действий и их обязательных полей.
- **Эффект:** внешний клиент по схеме `tools/list` не видит ни формата `create_file`/`patch_file`/`transaction`, ни поддерживаемых операций сцен/ресурсов/настроек.

### 3.2. Редакторские модули `context.editor_context` и `editing.scene_ops` отключены при запусках MCP и HTTP
- **Где:**
  - `python/channels/mcp/stdio.py` (строка 47: `profile='cli'`)
  - `python/runtime/http_services.py` (строка 114: `profile='cli'`)
  - `python/runtime/bootstrap.py` (строки 149–150: фильтр `item.spec.environment == "editor" and profile != "editor"`)
  - `plugin.cfg` (строка 7: `script="editor/native/agent_entry.gd"`) vs `plugin.gd` (строки 7–22)
- **Суть проблемы:**
  - И MCP-процесс (`stdio.py`), и HTTP-сервер панели (`build_http_agent`) собирают `Agent` в профиле `'cli'`, из-за чего все модули с `environment="editor"` (`context.editor_context`, `editing.scene_ops`) не регистрируются.
  - Одновременно `plugin.cfg` подключён к `editor/native/agent_entry.gd`, а не к `plugin.gd`, поднимающему `editor/core/lifecycle.gd` и TCP-мост `editor/bridge/`.
- **Эффект:** через реестр инструментов (`tools/list`, `context`, `scene_ops`) модульный мост живого редактора неактивен; в HTTP-контуре контекст редактора передаётся отдельным путём через `InteractiveGateway` (`attach_to_prompt`), а структурные операции `NativePlanner` идут через `EngineOverlay`, а не через открытый редактор.

### 3.3. Перегруженный и неоднородный список инструментов в `tools/list`
- **Где:**
  - `python/channels/mcp/server.py` (строки 38–39)
  - `python/runtime/bootstrap.py` (`Agent.tools`, строки 89–90)
  - `contract/capabilities/*.json` (35 публичных спецификаций)
- **Суть проблемы:** `McpServer` отдаёт единым плоским списком все активные `ToolSpec` без разделения на уровни: рядом находятся базовые read-примитивы (`read`, `search`, `functions`), узкие предпросмотры рефакторинга (`node_rename_preview`, `split_gd_scan`), внутренний оркестратор-диалог (`chat`, `assistant_turn`, `judge`) и непрозрачный `assistant_plan`. Описания инструментов написаны частично на русском, частично на английском.

---

## 4. Структура кодовой базы для ИИ-разработчика самого плагина

### 4.1. Параллельное существование двух контуров в Python и GDScript
- **Где:**
  - Python: `python/modules/*` и `python/substrate/{assistant,code_intel,context,editing,engine,project,scene,verification}/*`
  - GDScript: `editor/native/*` (подключён в `plugin.cfg`) и `editor/{core,bridge,ui,settings,harness}/*` (подключены в `plugin.gd`)
  - `editor/native/python/minilich/`
- **Суть проблемы:** логика одноимённых областей (HTTP-роуты, контекст, рефакторинг сцен/файлов/символов, панель UI, точка входа плагина) присутствует в двух разных реализациях одновременно; часть связей работает через динамическую подмену `sys.modules` и глобального состояния (`NativeServerReferences` в `python/runtime/http_services.py`, `NativePlanner` в `python/substrate/assistant/native_planner.py`, `JudgeRead` в `python/substrate/assistant/judge_read.py`, `ChatGateway` в `python/substrate/assistant/chat_gateway.py`).
- **Эффект:** при поиске места для правки ИИ-исполнитель сталкивается с дублирующимися файлами и нетривиальным runtime-связыванием без явных статических импортов.

### 4.2. Остаточные TODO-заглушки рядом с действующей реализацией
- **Где:**
  - `python/channels/mcp/handlers.py` (3 строки, `# TODO: реализация...`)
  - `python/runtime/profiles.py` (3 строки, `# TODO: реализация.`)
- **Суть проблемы:** оба файла содержат только комментарии `# TODO`, тогда как обработка MCP реализована в `python/channels/mcp/server.py`, а профили заданы в `python/runtime/bootstrap.py`.

### 4.3. Жёсткие байтовые/строчные пины нативных файлов при правках в `substrate/`
- **Где:**
  - `tools/check_limits.py` (строки 22–62: `VERBATIM_DIRS`, `API_VERBATIM_DIR = "python/substrate/llm/api"`, `SERVER_NATIVE_CAPS` с SHA-256 и др.)
- **Суть проблемы:** часть нативных файлов (включая `python/substrate/llm/api/agent_prompts.py` и `python/substrate/assistant/server/{chat_routes.py, server_state.py}`) находится под ограничениями/проверками эталонной неизменности, что ограничивает прямую правку этих файлов без нарушения текущих пинов.

### 4.4. Объём обязательного контекста на старте работы по `AGENTS.md`
- **Где:**
  - `AGENTS.md` (таблица чтения из 9 пунктов)
  - `RULES.md` (1012 строк, ~83 КБ), `docs/tests-map.md` (702 строки, ~100 КБ), `docs/PROGRESS.md` (168 строк, ~63 КБ), `docs/NOTES.md` (513 строк, ~61 КБ), `docs/parity.md` (321 строка, ~39 КБ)
- **Суть проблемы:** инструкция требует последовательного чтения перечисленных документов до первой правки кода, что занимает значительную долю контекстного окна модели до начала работы над задачей.
