# Статус глубокой интеграции с Godot

Документ обновлён 2026-09-15 после исправлений и проверки на настоящем Godot 4.6.1,
включая коммит `0508272`. Подробности проверки и оставшиеся риски:
[`POST_TESTING_AUDIT.md`](POST_TESTING_AUDIT.md). Исходный замысел сохранён в
[`GODOT_INTEGRATION_ROADMAP.md`](GODOT_INTEGRATION_ROADMAP.md).

## Реализовано

| Возможность | Статус | Основные ограничения |
| --- | --- | --- |
| Контекст живого редактора | Реализовано | Текущий скрипт/caret отправляются при явной ссылке пользователя на текущий код либо выделении. Списки открытых файлов и generated `.uid` не засоряют модельный контекст. |
| `gather_context` | Реализовано | Один локальный пакет объединяет символы, сцену, зависимости, диагностику, ClassDB, autoload и InputMap под жёстким бюджетом. Не является полноценным LSP. |
| Семантический индекс | Реализовано | Инкрементальный индекс GDScript с объявлениями, ссылками и hash freshness. Консервативный parser намеренно отказывается от неоднозначных связей. |
| `rename_symbol` | Частично реализовано | Безопасно поддерживаются `class_name`, функции и сигналы. Переименование узлов, групп, InputMap actions и произвольных строковых ключей не включено. |
| `create_scene` / `edit_scene` | Реализовано | Новая сцена создаётся через native root, optional existing script и структурные операции. Destination не перезаписывается. Существующая сцена должна быть сохранена и закрыта; raw `.tscn` операции запрещены. |
| `edit_project_settings` | Реализовано | InputMap, autoload, main scene, layer names и display settings. Существующие actions/events сохраняются, точные повторы пропускаются. После реального изменения или отката `project.godot` нужен перезапуск редактора. |
| Проверка настоящим Godot | Реализовано | Baseline/candidate overlay для файловых действий и rename. Существующие `gd_lint`, `gd_api_check`, `tscn_lint` остаются первым барьером. |
| `transaction` | Реализовано | Один overlay, preview, confirm и history entry для `create_file`, `patch_file`, `move_file`. Scene/settings/resource действия остаются отдельными транзакциями. |
| `project_command` | Реализовано | Поддержаны `create_scene_component`, `create_input_action`, `register_autoload`, `rename_symbol`, `atomic_files`. |
| `edit_resource` | Реализовано | Только существующие текстовые `.tres`: свойства, ссылки, Animation value tracks, SpriteFrames, Theme и TileSet atlas source. Ресурс и его вложенные subresources должны быть закрыты в Inspector. Бинарные `.res` и изменение `.import` не поддерживаются. |
| `inspect_runtime` | Реализовано | Read-only active scene, bounded tree, явно запрошенные native ClassDB properties, custom errors/events и метрики. Нет общего stack/locals API и произвольных GDScript getters. |
| `run_check` | Автоматический запуск заблокирован | Протокол и unit tests сохранены, но панель не запускает/не останавливает игру и не отправляет check в непроверенную сессию. Стабильного доказательства принадлежности запуска через public API Godot 4.6.1 не найдено. |

## Runtime Bridge

`inspect_runtime` требует debug-only autoload. Плагин
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

Для проверки игры сейчас следует запускать её вручную и использовать
`inspect_runtime`. Автоматический `run_check` возвращает локальный отказ,
не запуская игру и не вызывая модель. Наличие единственной debugger session
не доказывает, что она запущена агентом. Это временная потеря функциональности
ради исключения остановки чужой игры, а не успешно работающий автотест.

Сохранённый протокол checks по-прежнему ограничивает шаги, InputMap, assertions,
размер снимка и полноту log delta. Это проверяется отдельно от доступности
автоматического запуска. Runtime evidence не является защищённым доказательством:
код проверяемого проекта находится в том же процессе, что и bridge.

## Проверка Godot

Для обычных файловых действий и rename сервер:

1. создаёт отдельные baseline и candidate копии проекта;
2. накладывает изменение только на candidate;
3. запускает обе копии через `agent_headless_validator.gd`;
4. загружает выбранные ресурсы и найденные статические referencers;
5. вычитает предсуществующие diagnostics baseline;
6. сохраняет validation receipt с хэшами кандидата, исходников и проверенных targets;
7. повторно проверяет receipt непосредственно перед записью.

Фактический запуск эквивалентен:

```text
godot --headless --path <overlay> --language en --log-file <log> --script res://.godot_agent_validation/validator.gd
```

Режим `auto` не блокирует изменение, если executable Godot недоступен. Режим
`required` блокирует. Путь движка обычно передаётся плагином через
`OS.get_executable_path()`. Проверка не покрывает динамически вычисляемые пути
и все возможные игровые состояния. Явные `checks` в transaction требуют
доступный движок даже при no-op; ошибки явно проверяемых targets не вычитаются
как допустимый baseline. Отсутствующий или некорректный по схеме результат harness
не считается успехом: обязательны версия схемы и список корректных diagnostics.

## Транзакции И Откат

- `transaction` объединяет только файловые `create_file`, `patch_file` и
  `move_file` в один sparse overlay и одну запись истории.
- `create_scene`, `edit_scene`, `edit_project_settings`, `edit_resource` и `rename_symbol`
  используют собственные безопасные пакетные потоки.
- Частичное принятие multi-file preview запрещено.
- Применение all-or-restore защищает от обычных ошибок процесса, но не является
  настоящей crash-atomic файловой системой: между несколькими `os.replace`
  возможен сбой питания или процесса.
- Откат агента не использует `EditorUndoRedoManager` и не затрагивает стек
  Undo/Redo пользователя.
- Ручное изменение после действия требует force. Более новое изменение агента
  того же файла блокирует откат старой записи даже с force.
- Лимит 50 относится к завершённым записям; незавершённые reservations и их
  snapshots не удаляются при pruning. Кнопки history entry пока не
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
- сохранённый серверный протокол failed check анализирует результат без
  packaging/self-heal циклов. Автоматический запуск в панели пока отключён.

Эти ограничения относятся к серверным циклам анализа. Внутренние механизмы
провайдера (например продолжение обрезанного API-ответа) учитываются отдельно;
строгий предел одного сетевого обращения для любого backend не заявляется.

Локальные HTTP-запросы подтверждения, debugger protocol и progress polling не
являются обращениями к нейросети. Один model request на каждую задачу остаётся
целевой метрикой, а не абсолютной гарантией.

## Проверки

Полный офлайн-набор интеграционных тестов запускается из `godot_agent/python`:

```powershell
python -B -X utf8 tests\run_integration_regressions.py
python -B -X utf8 tests\run_integration_regressions.py --godot "C:\tools\Godot.exe"
```

`selfcheck.py --full` не входит в этот набор: он запускает длительное обучение
mini-lich и имеет известный предсуществующий сбой на malformed `\q`.

Общий запуск после расширения runner: **59/59 PASS**, 55 офлайн-наборов и
4 реальных engine-набора на официальном Godot 4.6.1. После последней правки
Inspector повторно прошли затронутые проверки: 26 executor-сценариев, 98/98
проверок GDScript wiring и ресурсный HTTP prepare/confirm/finalize/rollback flow.
После усиления assertions каталога отдельно прошли 123/123 проверки каталога.
Полный набор после этих адресных проверок повторно не запускался.

Live coverage включает компиляцию 23 addon scripts, PackedScene/ProjectSettings/
ResourceSaver, TileSet atlas и безопасные отказы, открытые чистые/грязные/неактивные
сцены, Inspector с root/embedded ресурсом, сохранение обоих значений autoreload
preference, отказ от неподтверждённого запуска и 8 случаев JPEG-размеров.
Пять production-validator тестов используют настоящий движок для baseline/candidate,
parse errors, explicit checks, referencers и freshness receipts; проверяют
неизменность исходных файлов и удаление собственных overlays.

Четыре symlink-теста пропущены из-за прав Windows. В headless editor остаются
shutdown RID/ObjectDB diagnostics; тесты не доказывают отсутствие утечек.
Пользовательский проект не запускался. Dirty script buffers и полный UI-поток
плагина не проверены живым редактором; frozen server EXE не пересобирался.

Перед релизом остаётся ручной smoke test реального интерфейса:

1. включить плагин в реальном проекте;
2. добавить `AgentRuntimeBridge` autoload;
3. дождаться `bridge_ready` в debug-запуске;
4. выполнить `inspect_runtime`;
5. проверить, что `run_check` объясняет отказ и не запускает/останавливает игру;
6. проверить отправку, новый чат, восстановление черновиков и browser composer;
7. проверить структурные scene/settings/resource действия и адресный rollback.

## Оставшиеся Направления

- безопасная идентификация принадлежащего агенту запуска перед возвратом `run_check`;
- восстановление rollback-кнопок после переоткрытия чата;
- более широкий rename для узлов, групп, InputMap actions и доказуемых ключей;
- общий stack/locals API, если Godot предоставит стабильный публичный интерфейс;
- live smoke на поддерживаемых версиях Godot и feature/version matrix;
- измерение реального количества model requests и токенов на пользовательских
  задачах;
- crash recovery для незавершённых многофайловых замен после остановки процесса.
