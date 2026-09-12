# Статус глубокой интеграции с Godot

Документ фиксирует фактически реализованный объём дорожной карты на коммите
`15d85f5`. Исходный замысел и порядок развития сохранены в
[`GODOT_INTEGRATION_ROADMAP.md`](GODOT_INTEGRATION_ROADMAP.md).

## Реализовано

| Возможность | Статус | Основные ограничения |
| --- | --- | --- |
| Контекст живого редактора | Реализовано | Передаётся ограниченный снимок выбранных узлов, текущего скрипта, выделения, caret-контекста, открытых сцен и состояния запуска. Полный Inspector и весь проект не отправляются. |
| `gather_context` | Реализовано | Один локальный пакет объединяет символы, сцену, зависимости, диагностику, ClassDB, autoload и InputMap под жёстким бюджетом. Не является полноценным LSP. |
| Семантический индекс | Реализовано | Инкрементальный индекс GDScript с объявлениями, ссылками и hash freshness. Консервативный parser намеренно отказывается от неоднозначных связей. |
| `rename_symbol` | Частично реализовано | Безопасно поддерживаются `class_name`, функции и сигналы. Переименование узлов, групп, InputMap actions и произвольных строковых ключей не включено. |
| `edit_scene` | Реализовано | `add_node`, `set_node_property`, `attach_script`, `connect_signal`, `reparent_node`; только текстовые `.tscn`, локальные узлы и поддержанные tagged Variant. |
| `edit_project_settings` | Реализовано | InputMap, autoload, main scene, layer names и display settings. После применения или отката `project.godot` нужен перезапуск редактора. |
| Проверка настоящим Godot | Реализовано | Baseline/candidate overlay для файловых действий и rename. Существующие `gd_lint`, `gd_api_check`, `tscn_lint` остаются первым барьером. |
| `transaction` | Реализовано | Один overlay, preview, confirm и history entry для `create_file`, `patch_file`, `move_file`. Scene/settings/resource действия остаются отдельными транзакциями. |
| `project_command` | Реализовано | Поддержаны `create_scene_component`, `create_input_action`, `register_autoload`, `rename_symbol`, `atomic_files`. |
| `edit_resource` | Реализовано | Только существующие текстовые `.tres`: свойства, ссылки, Animation value tracks, SpriteFrames, Theme и TileSet atlas source. Бинарные `.res` и изменение `.import` не поддерживаются. |
| `inspect_runtime` | Реализовано | Read-only active scene, bounded tree, явно запрошенные native ClassDB properties, custom errors/events и метрики. Нет общего stack/locals API и произвольных GDScript getters. |
| `run_check` | Реализовано | Локальный запуск одной сцены, ожидания, InputMap actions, assertions, bounded screenshot и проверка log delta. Произвольные вызовы, raw key/mouse input и mutation RPC запрещены. |

## Runtime Bridge

`inspect_runtime` и `run_check` требуют debug-only autoload. Плагин
регистрирует `EditorDebuggerPlugin` автоматически, но не изменяет
`project.godot` без подтверждённого действия пользователя.

Настройка целевого проекта:

1. Открыть **Project Settings → Globals → Autoload**.
2. Выбрать `agent_runtime_bridge.gd` из установленной папки аддона.
3. Добавить его с именем `AgentRuntimeBridge`.
4. Перезапустить редактор после изменения autoload.
5. Запускать игру из редактора в debug-режиме.

Bridge активен только при `OS.is_debug_build()` и активном
`EngineDebugger`. Он не предоставляет методов изменения узлов, вызова
проектных функций, смены сцены или управления breakpoint.

Пример агрегированного чтения runtime:

```json
{
  "action": "inspect_runtime",
  "sections": ["active_scene", "tree", "properties", "errors", "metrics"],
  "properties": [
    {"node": "Player", "names": ["position", "velocity"]}
  ],
  "max_age_ms": 1000,
  "reason": "Проверить состояние игрока"
}
```

Пример локальной проверки:

```json
{
  "action": "run_check",
  "scene": "res://levels/level_01.tscn",
  "steps": [
    {"op": "wait_frames", "frames": 3},
    {"op": "input_action", "name": "move_right", "pressed": true},
    {"op": "wait_time", "ms": 500},
    {"op": "input_action", "name": "move_right", "pressed": false},
    {"op": "assert_node", "node": "Player", "exists": true},
    {
      "op": "assert_property",
      "node": "Player",
      "property": "position",
      "operator": "approx",
      "expected": {"type": "Vector2", "value": [100, 200]},
      "tolerance": 5
    },
    {"op": "assert_no_errors"}
  ],
  "timeout_ms": 12000,
  "screenshot": {
    "when": "failure",
    "max_width": 480,
    "max_height": 270,
    "quality": 0.65
  }
}
```

Ограничения `run_check`:

- 1–32 шага и минимум одно assertion;
- до 16 input-шагов и 16 assertions;
- до 1200 кадров и 10 секунд явных ожиданий;
- общий timeout 1–20 секунд;
- ввод только через существующие InputMap actions;
- читаются только верхнеуровневые native ClassDB properties;
- только один `inspect_runtime` или `run_check` на пользовательский ход;
- уже запущенная пользователем игра не перезапускается и не останавливается агентом;
- успешная проверка не вызывает модель повторно, неуспешная передаёт один
  агрегированный отчёт без автоматического цикла repair/check.

`assert_no_errors` требует доступный и полный delta `user://logs/godot.log`.
При ротации, исчезновении или переполнении лимита лога assertion завершается
неуспешно, а не считается подтверждённым отсутствием ошибок.

## Проверка Godot

Для обычных файловых действий и rename сервер:

1. создаёт отдельные baseline и candidate копии проекта;
2. накладывает изменение только на candidate;
3. запускает обе копии через `agent_headless_validator.gd`;
4. загружает выбранные ресурсы и найденные статические referencers;
5. вычитает предсуществующие diagnostics baseline;
6. сохраняет validation receipt, связанный с хэшами кандидата;
7. повторно проверяет receipt непосредственно перед записью.

Фактический запуск эквивалентен:

```text
godot --headless --path <overlay> --language en --log-file <log> --script res://.godot_agent_validation/validator.gd
```

Режим `auto` не блокирует изменение, если executable Godot недоступен. Режим
`required` блокирует. Путь движка обычно передаётся плагином через
`OS.get_executable_path()`. Проверка не покрывает динамически вычисляемые пути
и все возможные игровые состояния, поэтому runtime-поведение проверяет
отдельный `run_check`.

## Транзакции И Откат

- `transaction` объединяет только файловые `create_file`, `patch_file` и
  `move_file` в один sparse overlay и одну запись истории.
- `edit_scene`, `edit_project_settings`, `edit_resource` и `rename_symbol`
  используют собственные безопасные пакетные потоки.
- Частичное принятие multi-file preview запрещено.
- Применение all-or-restore защищает от обычных ошибок процесса, но не является
  настоящей crash-atomic файловой системой: между несколькими `os.replace`
  возможен сбой питания или процесса.
- Откат агента не использует `EditorUndoRedoManager` и не затрагивает стек
  Undo/Redo пользователя.
- Ручное изменение после действия требует force. Более новое изменение агента
  того же файла блокирует откат старой записи даже с force.
- Журнал проекта ограничен 50 записями. Кнопки history entry пока не
  восстанавливаются после переоткрытия чата.

## Запросы К Модели

Минимизируются именно обращения к модели, а не локальные HTTP-вызовы:

- compact editor context добавляется только к текущему ходу и не сохраняется в
  API history;
- `gather_context` заменяет цепочку read/list/librarian одним локальным пакетом;
- `transaction` объединяет взаимозависимые файловые правки;
- `inspect_runtime` получает один aggregate snapshot и делает один follow-up
  модели для интерпретации;
- успешный `run_check` делает ноль follow-up запросов модели;
- неуспешный `run_check` делает не более одного follow-up без автоматического
  repair/check loop.

Локальные HTTP-запросы подтверждения, debugger protocol и progress polling не
являются обращениями к нейросети. Один model request на каждую задачу остаётся
целевой метрикой, а не абсолютной гарантией.

## Проверки

Полный офлайн-набор интеграционных тестов запускается из `godot_agent/python`:

```powershell
$tests = @(
  "test_editor_context.py", "test_gather_context.py", "test_semantic_index.py",
  "test_rename_symbol.py", "test_rename_symbol_flow.py", "test_scene_actions.py",
  "test_scene_action_flow.py", "test_project_settings_actions.py",
  "test_project_settings_flow.py", "test_godot_headless_validation.py",
  "test_transaction_actions.py", "test_transaction_flow.py",
  "test_high_level_actions.py", "test_high_level_flow.py",
  "test_resource_actions.py", "test_resource_action_flow.py",
  "test_runtime_debug.py", "test_runtime_debug_flow.py", "test_runtime_checks.py",
  "test_runtime_check_flow.py", "test_answer_judge.py", "test_gdscript_wiring.py",
  "test_chat_pending_cleanup.py", "test_rollback_by_entry.py",
  "test_tree_excludes_addon.py", "test_pyinstaller_spec.py",
  "test_api_end_to_end.py", "test_megaprompt_once.py", "test_qwen_no_double_send.py"
)
$tests | ForEach-Object {
  python (Join-Path "tests" $_)
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

`selfcheck.py --full` не входит в этот набор: он запускает длительное обучение
mini-lich и имеет известный предсуществующий сбой на malformed `\q`.

Без установленного Godot CLI Python-тесты и static wiring не доказывают
GDScript parse/API compatibility. Перед релизом необходим ручной smoke test:

1. включить плагин в реальном проекте;
2. добавить `AgentRuntimeBridge` autoload;
3. дождаться `bridge_ready` в debug-запуске;
4. выполнить `inspect_runtime`;
5. выполнить успешный и заведомо неуспешный `run_check`;
6. проверить освобождение InputMap actions и остановку только принадлежащей
   проверке сцены;
7. проверить структурные scene/settings/resource действия и адресный rollback.

## Оставшиеся Направления

- восстановление rollback-кнопок после переоткрытия чата;
- более широкий rename для узлов, групп, InputMap actions и доказуемых ключей;
- общий stack/locals API, если Godot предоставит стабильный публичный интерфейс;
- live smoke на поддерживаемых версиях Godot и feature/version matrix;
- измерение реального количества model requests и токенов на пользовательских
  задачах;
- crash recovery для незавершённых многофайловых замен после остановки процесса.
