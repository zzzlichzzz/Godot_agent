# Проверка после пользовательских тестов

Актуально после `9837cb0`. Это отчёт о проверенном объёме, а не гарантия
отсутствия всех ошибок. Архитектурный план не равен реализованной функциональности;
текущий статус находится в [GODOT_INTEGRATION_STATUS.md](GODOT_INTEGRATION_STATUS.md).

## Исходные проблемы

| Проблема | Исправление |
| --- | --- |
| GDScript Variant inference, зарезервированное имя, void API, static hashing | Явные типы, корректные API, instance HashingContext; добавлена реальная компиляция 23 скриптов движком |
| Открытый файл в каждом запросе | Caret/script только для явной ссылки на текущий код или выделения; открытые списки и `.uid` исключены из модельного шума |
| Existing InputMap action прерывает работу | Effective-operation planner сохраняет прежние deadzone/events, пропускает точные повторы, добавляет недостающее; conflicting autoload path не угадывается |
| Новые сцены создавались сырым текстом | `create_scene`: native root, existing script и структурные operations; staged PackedScene публикуется без перезаписи destination |
| Чужая/обрезанная сводка вместо prompt | Удалена отправка несовпадающего composer «как есть»; строгая проверка после hooks и stale DOM; chat ID, admission, chat-scoped notes и атомарный transcript |
| Старое изображение input/потеря черновика | Централизованный reset caret/scroll/redraw/focus, per-chat drafts, immutable resend envelope; реальный UI repaint ещё требует ручного smoke |
| Желание локального auto-fix | Только эквивалентные wrappers/aliases/CRLF и exact already-satisfied; неоднозначные API/типы/ключи автоматически не переписываются |

## Дополнительные исправления

- Atomic text writes не обрезают исходник при ошибке записи staging.
- Recovery не использует hash внешней правки как разрешение её затереть.
- Явный no-op с checks всё равно проходит обязательную проверку Godot.
- Receipt включает проверенные targets/referencers; отсутствующий harness result блокирует применение.
- Незавершённые reservations сохраняются при pruning и failed recovery.
- Journal/API history не трактуют повреждение/ошибку чтения как пустую историю.
- API model switch сохраняет history до metadata; ошибки после принятого ответа не провоцируют remote resend.
- Перенос основного файла и UID выполняется согласованно; failed restoration оставляет evidence и reservation.
- Resource backup уникален, не удаляет чужой `.agent-backup`, сохраняется до reload/UID/semantic validation.
- Ресурсные UID и локальные subresources проверены настоящим Godot, а не только строковыми тестами.
- Заголовок авторизации и body limit проверяются до JSON; init/navigation не сбрасывают активную операцию.
- Windows case/path aliases учитываются в addon policy, duplicate detection и rollback blockers.
- Runtime result replay связан с контекстом/сессией/поколением и TTL; contention даёт retryable ответ.
- DeepSeek больше не повторяет Enter/click после неоднозначной отправки. При отсутствии подтверждения выдаётся предупреждение, а не второй запрос.
- Плагин не закрывает открытые сцены и не меняет persistent autoreload preference без спроса.
- File actions отказывают при несохранённых открытых script buffers. Из-за отсутствия public resource accessor у ScriptEditorBase проверка консервативна: все открытые buffers должны быть чистыми, если затронут открытый скрипт.

## Реальная проверка

Официальный Godot `4.6.1.stable.official.14d19694e` получен из GitHub release;
SHA256 архива сверён с метаданными выпуска:
`088da0457e2d1f7f8a45e6d4605a42b756ea33b9ccd75059bdbc01bb31c2b40d`.
Engine-тесты используют временный проект без включённого плагина, user autoload
и исходной игры; HOME/APPDATA/LOCALAPPDATA/XDG изолированы.

Запуск из `godot_agent/python`:

```powershell
python -B -X utf8 tests\run_integration_regressions.py --godot "C:\tools\Godot.exe"
```

Результат: все 52 набора прошли. В первом общем запуске прошёл 51 набор;
оставшийся ownership runner требовал лишний CLI-аргумент. После исправления
только этого runner он отдельно прошёл. Успешные 51 проверки без причины
повторно не запускались. В четырёх отдельных symlink cases не хватило прав Windows.

Live coverage: компиляция 23 addon scripts; 17 executor-сценариев с реальными
PackedScene/ProjectSettings/ResourceSaver, сериализацией owners/properties/scripts/
signals, InputMap idempotency, Animation/SpriteFrames/Theme, UID, Windows file locks,
backup conflicts и восстановлением. Ownership-suite проверяет public ClassDB,
5 безопасных отказов и 8 decoded JPEG dimensions. Настоящие remote/replacement
игры и визуальный UI в этой suite не запускались.

Headless editor печатает shutdown Canvas/ObjectDB/RID leak diagnostics.
Executor/ownership harness допускают только конкретные RID-at-exit строки и
показывают их; другие engine/script ошибки проваливают тест. Это не leak-free
сертификация. Полный `selfcheck.py --full` с длительным mini-lich training не запускался.

## Ограничения и следующий этап

1. **Автоматический `run_check` временно отключён.** Public API проверенного Godot
   не позволяет доказать связь debugger session с конкретным editor launch и
   остановить только эту сессию. Панель отказывает до запуска; `inspect_runtime`
   для вручную запущенной игры остаётся. Это ограничение отражено и в prompt.
2. **Crash recovery не завершён.** Есть retained evidence/reservations и recovery
   обычных ошибок, но нет полного startup reconciliation после убийства процесса
   или питания. При `recovery_required` нельзя удалять backups/journal вручную
   до анализа сохранённых путей. Автоматический откат поверх внешних edits запрещён.
3. **Resource rename на Windows не crash-atomic.** Реальный locked-source probe
   показал, что Godot может удалить destination перед неудачным rename. Backup
   сохраняется; окно между последней freshness-check и mutation остаётся.
4. **Процессы и диски.** Locks журналов/history сериализуют threads одного сервера,
   не несколько независимых серверных процессов. Metadata/API history не являются
   одной crash-atomic транзакцией. Hard-link публикация/move требует поддержки
   файловой системы; cross-device move безопасно отказывается, без overwrite fallback.
5. **Runtime не security sandbox.** Project/extension code может влиять на данные
   собственного процесса и иметь getters с побочными эффектами. Проверки не являются
   доказательством корректности против злонамеренного проекта.
6. **Внешние сайты и UI.** Нужен ручной smoke настоящего browser composer, переключения
   чатов, focus/repaint и примера InputMap пользователя. DOM/network тесты в наборе
   имитируют сбои и не используют пользовательские аккаунты. Неоднозначный accepted
   send может потребовать ручной проверки чата; автоматический resend отключён.
7. **Сборка.** Проверены исходники Python/GDScript, а не заново собранный server EXE.
   Если используется frozen server, изменения Python требуют его пересборки обычным
   `python/build_server_exe.bat`. Установленная/запущенная пользовательская игра
   и её настройки тестами не изменялись.

Для релиза остаются отдельные задачи: восстановление незавершённых операций после
restart, безопасный владелец runtime-процесса, single-instance server coordination,
ручной browser/editor smoke и поддерживаемая матрица версий Godot. Они не отмечены
как исправленные только потому, что regression suite прошла.

## Продолжение 2026-09-15

Исходная точка повторно проверена после восстановления контекста: единый запуск
`run_integration_regressions.py --godot <Godot 4.6.1 console>` завершился
**52/52 PASS**. Четыре symlink cases пропущены из-за прав Windows; shutdown
RID/ObjectDB diagnostics воспроизводятся. Исходный проект не запускался.

Порядок дальнейшего аудита (каждый этап с изменениями: тесты, коммит, push):

1. Сохранить оставленные предыдущим чатом отчёт, статус и общий runner.
2. Production headless-validator: настоящий engine, baseline/candidate,
   parse errors, explicit checks, receipts и неизменность исходного проекта.
3. TileSet atlas: live edit, сохранение и повторная загрузка, безопасный отказ.
4. Дополнительные offline API suites: транспорт, secrets/limits, совместимость
   провайдеров; включить подходящие проверки в общий runner.
5. Editor/runtime: проверить границы обещаний и live-покрытия, защиту buffers,
   сохранение пользовательских настроек и отказ от неподтверждённого запуска.
6. Обновить результаты и оставшиеся ограничения без объявления ручного UI,
   crash recovery или frozen EXE проверенными по одним unit tests.
