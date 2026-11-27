# ADR-0016. Raw transfer, replace_raw, dir_case и фазовый WAL

Статус: **принято аудитором 2026-11-02 (сессия 76)** — C.22 принят; исходный статус был `proposed` (C.22, решения аудитора D1–D10 от 2026-11-02).

## Контекст

ADR-0005/0015 исполняют script_edit/create/delete. Текстовый create не выражает
перенос произвольных байтов, а script_edit меняет standalone LF в mixed-EOL файле.
Actual persisted-window probe: эффект create до RECEIPT остаётся после recovery
`left_prepared`. Native отдельно проверяет весь набор источников/ссылок/целей
до первого эффекта. File os.replace меняет leaf-case, но не casing родителя NTFS.

## Решения: четыре вопроса D1

### 1. Absent-цель и case-only

`Step(op="move", target=src, payload={"dest": dst}, expected_hash=raw_sha256(src),
compensates="move")`. В `WritePlan.expected`: source raw SHA и destination `""`.
Перенос выполняет только substrate/fs.move: raw os.replace, без декодирования;
отсутствующие родители цели создаёт этот же примитив, не отдельный op mkdir.
Источники — обычные файлы. Оба endpoint проходят guard_transfer и containment.

Общий verify_absent остаётся прежним. Только move допускает существующую цель
при case-only identity того же файла; чужой файл/каталог — stale_plan. Case-only
без temp-hop. Строки source/destination в WAL сохраняются дословно.

### 2. Intent и recovery

Под project lock сначала проверяется **весь** план, затем для каждого шага:
durable backup (если нужен) → durable EFFECT_INTENT → эффект → durable RECEIPT.
Intent содержит entry_id, op, target, dest, expected_hash и необходимые proof-
метаданные existing receipt (applied_hash/undo_token). Step/Receipt/WritePlan
не получают новых полей. Не добавляется второй журнал или обход shared funnel.

При intent без receipt recovery доказывает pre/post-state: либо эффект ещё не
был выполнен, либо обратный move/delete/create/raw-restore; чужое состояние —
conflict/RECOVERY_FAILED без перезаписи. Backup проверяется по raw SHA. Повтор
после обратного эффекта, но до RESTORED, должен безопасно завершить ту же фазу.
Intent не является новым lifecycle-state; state_of по-прежнему видит APPLYING.

Старые WAL без EFFECT_INTENT сохраняют ADR-0005 left_prepared. Это не доказательство
отсутствия эффекта старого плана, а совместимость; новый исполнитель пишет intent
и для accepted create/delete/script_edit, закрывая наблюдённое окно.

D11 (2026-11-02): WAL получил фазовую запись EFFECT_INTENT для **всех**
операций, включая ранее принятые в C.20. Один формат WAL и одна recovery-логика;
intent только для новых операций отвергнут. В принятом case106 меняется лишь
expect.wal_states и его bytes/SHA в manifest; исходный тест остаётся точным.
Новый safety-case `safety-create-receipt-gap` фиксирует persisted эффект после
durable intent без RECEIPT и byte-exact recovery: **наше поведение, не parity**,
поскольку native такого crash-состояния не имеет. Intent не начавшегося шага
проверяется как pre-state/no-op; для него не требуется RESTORED, финальный
ROLLED_BACK закрывает фазу. Чужое состояние всё равно даёт conflict.

### 3. Смешанные операции и обратный порядок

Moves владельцев и явных companions выполняются до replace_raw; каждый target
имеет одну операцию. Правка перемещаемого содержимого адресуется destination,
не вторым шагом того же source. Первоначальный expected destination остаётся
absent; preflight проверяет вычислимое post-state зависимых шагов без IO-эффектов.
replace_raw.expected_hash — raw SHA на момент этой операции, не absent-sentinel.

Companion import следует сразу за владельцем; UID тоже явный move при наличии.
Обратный проход сначала возвращает raw содержимое destination, затем companions
и владельца. Каждая компенсация durable RESTORED до следующей. Foreign UID,
неплановые ссылки и чужие post-state не удаляются и не перезаписываются.

### 4. Совместимость

Формы Step/Receipt/WritePlan и digest, accepted script_edit/create/delete,
общий guard_path и public paths_preview остаются прежними. Нового public ToolSpec
или capability нет: file_refactor — внутренний contributor, contract27/reports44.
R-11 seam C.21 идёт через __init__/public и requires, с одним exact lint edge.

## replace_raw

`Step(op="replace_raw", target=path, payload={"bytes_b64": ...},
expected_hash=raw_sha256(path))`. Только правки ссылок file_refactor; strict base64,
whole-file bytes, raw backup и raw post-hash. BOM/CRLF/lone CR/standalone LF
сохраняются буквально. Existing script_edit decode/encode не меняются.
Source discovery/internal/directory projection остаются единственными в C.21.
Публичные summaries не содержат machine absolute paths или native raw buffers.

## dir_case: второй и последний структурный вид

`Step(op="dir_case", target="res://chars", payload={"dest": "res://Chars"},
expected_hash="", compensates="dir_case")`. Preflight требует same real directory,
только различие регистра сегментов, без новых сегментов. Иначе invalid_input.
Substrate.rename_dir_case использует os.rename, не os.replace; bytes не меняет,
backup не нужен, applied_hash="". Вперёд всегда последним, inverse всегда первым.
Не эмитятся moves детей только из-за casing каталога; leaf-case остаётся move.

Intent без receipt: при same real directory и case-only путях выполняется swapped
dir_case; иначе conflict. NTFS доказывается actual names/Path.resolve(), не SHA
одного target. После inverse paths детей снова имеют прежний casing.

Новых op ровно три: move, replace_raw, dir_case; структурных transfer-вида два.
Четвёртого нового op, mkdir, content move_dir или directory-delete нет.
Пустые каталоги при rollback **не воссоздаются** (решение D4/D8).

## Политика и намеренная граница

guard_transfer не ослабляет guard_path: project.godot нельзя rename, но можно
править ссылками; root plugin.cfg transfer разрешён, addons case-insensitive
запрещены, agent-tree relocation запрещён даже при trusted flags (SEC-22).
companion_script информационный. Native files публикуются лексикографически;
absolute/raw исключены. Полный закрытый список отличий — C.22 в deviations.md.

## Проверки до реализации и сдачи

Корпус → спецификация → red → production. Raw binary/BOM/mixed-EOL/standalone LF;
whole-plan stale до effects; explicit UID/import; NTFS casing/inverse; intent
без receipt и crash на границах; foreign post-state конфликт; legacy WAL;
негативный foreign-domain lint и mutation exact public edge; security endpoints.
M1 destination check, M2 source SHA, M3 raw roundtrip, M4 compensation, intent/
dir_case/guard защита: каждый mutation red и byte-exact restore до final gates.

Это proposed решение и спецификация, не утверждение о наличии реализации.

## Дополнение пользователя при продолжении (2026-11-02)

Разрешены pure details extraction в C.21 directory.py (references/API прежние)
и узкие internal маршруты snapshot_diff/selfcheck/probe для C.22. Не меняются
27 capability-артефактов, 44 отчёта, selector остальных механик и context001.

Native external_move_record выражается move с `payload.already_moved=true`:
plan.expected[source]="", plan.expected[dest]=raw SHA, step.expected_hash=raw SHA.
Перед apply source отсутствует, dest — обычный файл с указанным SHA; backup
берётся с dest. Forward только фиксирует intent/receipt, повторно не переносит.
Inverse проверяет dest post-state и переносит его обратно. После interruption
такой intent является rollback anchor, а не доказательством нового forward IO.
Каталог представлен пофайлово; directory-delete/move_dir/четвёртого op нет.
Это явное разрешённое исключение к исходному D1, не неявный payload bypass.

## Неразрешённые границы external-sync (2026-11-02)

Actual frozen corpus из12 sync-вызовов выявил отдельный STOP перед production:
directory-sync не правит внешние relative load/preload, тогда как общий C.21
project_directory правит; external NTFS leaf-case оставляет source как alias
destination, против действующего source-absent anchor; empty directory native
имеет rollback anchor, но разрешённые per-file moves/dir_case его не выражают.
Zero-step COMMITTED получает no_receipts при rollback, не native parity.
Нужны explicit решения, перечисленные в worksheet. Это НЕ одобренные
исключения, defaults/правила отсутствия source/closed deviations пока прежние.

После решения sync должен держать один project lock от scan до COMMITTED и
использовать общий эффектный цикл funnel, а не повторять исполнитель или
обходить нереентерабельный lock. Step/Receipt/WritePlan и public contract27
не расширяются. Корпус уже доступен selfcheck; отсутствие sync честно fail.

## D13 — разрешённая спецификация external-sync (2026-11-02)

Предыдущий STOP исторический: D13.1–D13.3 разрешены аудитором. C.21 public seam
получает keyword-only external_relative: bool=True. False используется только
C.22 directory external-sync: existing directory projection обрабатывает
раздельно moved documents и external documents с пустым moved map; внешние
relative literals не трогаются, точные res:// prefix/directory переписываются.
Default ветка дословно вызывает прежнюю projection. Корпус25/25 и report C.21
не переснимаются. Внутренние relative ссылки moved GD проецируются как прежде.

Leaf case-only anchor исключается до WritePlan только после тройного доказательства:
одинаковый фактический realpath source/destination, равные raw SHA обоих путей
и захваченного snapshot, actual_rel обоих равен публикуемому destination.
Несоответствие → conflict; generic verify_absent остаётся прежним. Никакого
Entry/receipt для этого anchor; anchor_already_completed печатается отдельно.
При обычном external move source absent, destination SHA: существующий move
с already_moved=True сохраняет обратный перенос, не выполняя forward IO.
Directory-case использует последний dir_case/первый inverse, не leaf anchors.
Обычный directory anchor компилируется по raw files общего snapshot.existing,
включая orphan/skip contents: native external anchor возвращает целое дерево;
это не расширение ordinary prepare moved_files_map и не второй scanner.

Внешний no-op не создаёт WritePlan вообще: patches=[], moved=[], plan_id=None,
entry_id=None только в возвращённом отчёте, WAL отсутствует. В частности пустой
каталог не возвращается назад: мы не выполняли его внешнее перемещение.
Один lock удерживается от snapshot до COMMITTED (или no-op). Shared execute
содержит единственный effect loop; write_apply сохраняет свою domain decision
и reporting callback, sync пользуется тем же executor с собственным summary.
Порядок durable backup→EFFECT_INTENT→effect→RECEIPT неизменен для всех операций.

Проверка декларации R-11 на реальном импорте: C.22 использует явный
`import python.modules.editing.paths_preview as paths_preview`, не импорт
из родительского namespace. Тогда imports_of видит ровно объявленное public
package edge, а удаление исключения делает красными и отдельный pin, и
реальный lint_arch. Foreign domain/app/substrate по-прежнему запрещены.
Parent-case pin отдельно наблюдает реальный os.rename каждого изменённого
segment и проверяет actual casing/raw inverse; наблюдаемая эквивалентность
os.replace на конкретном NTFS не меняет обязательный выбор примитива D9.
