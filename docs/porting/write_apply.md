# editing.write_apply — применение плана и откат (часть 2 воронки)

**Статус:** этап `7` (см. `docs/PROGRESS.md`)
**Обновлено:** `2026-10-27`

## Цель

Применить ровно тот план, который показал `write_preview`: перечитать файлы,
сверить `expected` (сырые байты) и `steps[].expected_hash` (нормализованный
текст), записать квитанции, вернуть `entry_id` для отката. Откат возвращает
байты побайтово и отказывается затирать чужую правку (`conflict`).

## Границы

| Часть | Что делает | Состояния |
|---|---|---|
| 1 | `write_preview`: план, `digest`, диффы, WAL `PREPARED`; в проект не пишет | `DRAFT → PREPARED` |
| **2 (этот срез)** | `write_apply` + `write_rollback` + recovery | `PREPARED → APPLYING → COMMITTED`, `ROLLING_BACK → ROLLED_BACK`, `EXPIRED` |
| 3 | сцены, `.tscn`, мост редактора | — |

Стоп-условия: `.tscn`/`project.godot`/ресурсы не трогаем; `history_manager` не
переносим; stale-check только по хешам байтов, не по mtime; запись — только в
`write_apply` (R-12).

## Старый код

| Файл | Что берём |
|---|---|
| `symbol_refactor_part3.py:616+` `apply_prepared_rename` | порядок применения, проверка «не изменилось ли», откат при сбое |
| `history_manager.py` (210/271/326/345/368/552/595/708) | **смысл**: запись до эффекта, откат по записи; код не переносим (R-08) |
| `part3:470-505` | гейтинг уже отработал в части 1; здесь — только отказ, если план нарушает инварианты |

## Контракт плана и байтов (ADR-0005, «Что именно хешируется»)

- `expected[path]` — sha256 **сырых байтов** (BOM и `\r\n` входят);
- `steps[].expected_hash` — sha256 **нормализованного** текста, в котором
  посчитаны смещения (`\r\n`,`\r` → `\n`, BOM снят);
- `payload.newline` — `"crlf"`/`"lf"` по байтам; после правки стиль файла
  **восстанавливается**;
- BOM возвращается, если он был в сырых байтах (признак читается заново при
  `apply`, план его не хранит).

## Решения

1. **Куда пишет `apply`.** Порт `ProjectWriter` (`read_raw(rel)`,
   `write_raw(rel, data)`) объявлен в `ports.py` модуля; адаптер —
   `substrate/fs/atomic_write.py` (`AtomicFileWriter`): temp в том же каталоге,
   `flush`+`fsync`, `os.replace`, затем `fsync` каталога на POSIX. Домен не
   знает ни про диск, ни про `user://`.
2. **`entry_id`.** `"<plan_id>#<n>"`, где `n` — номер `APPLYING`-записи в WAL
   (1 для первого применения). Идемпотентный повтор находит тот же `entry_id`
   в `COMMITTED`, поэтому формат не меняется задним числом.
3. **Чем откатывать.** Бэкап **сырых байтов** в
   `state_dir/backup/<plan_id>/<index>.bin` (`substrate/store/backups.py`),
   `undo_token` = `<plan_id>/<index>.bin`. Инверсные правки отброшены: они
   требуют «умных» решений при откате и не дают побайтовой гарантии для
   CRLF/BOM. Восстановление = прочитать бэкап, записать атомарно, сверить
   sha256 с `expected[path]`.
4. **Recovery.** Одна точка входа — публичная `editing.rollback.recover(ports)`;
   её вызывает `runtime/bootstrap.py` после сборки портов, результат пишется в
   лог `godot_agent.recovery`. Правила ADR-0005: `PREPARED` старше
   `confirm_ttl` → `EXPIRED`; `APPLYING` с квитанциями → автооткат →
   `ROLLED_BACK`; `APPLYING` без квитанций → как `PREPARED` (эффекта не было).
5. **Лок.** `substrate/store/lock.py: FileLock(state_dir)` — файл
   `project.lock` через `os.open(O_CREAT|O_EXCL)`, PID и время внутри, снятие в
   `finally`. Держится на весь интервал «перечитать `expected` → сверить →
   применить → квитанция». Второй `apply` → `conflict`, `reason=lock_busy`.
6. **Частичный откат.** Откат идёт от последней квитанции к первой; каждая
   восстановленная запись пишется как `RESTORED` (путь и хеш). Повторный откат
   продолжает с невосстановленных, а не с первого; уже восстановленный файл
   распознаётся по хешу `expected[path]`. Если файл не равен ни `applied_hash`,
   ни `expected[path]` — `conflict`, файл не трогаем.
7. **Сбой шага.** `write_apply` ловит **любое** исключение (не только
   `AppError`): `funnel.abort_plan` пишет `ROLLING_BACK`, восстанавливает
   квитанции в обратном порядке и пишет `ROLLED_BACK`, после чего наружу уходит
   исходный `AppError` или `internal`. Иначе `OSError` посреди плана оставлял бы
   проект «полуприменённым».
8. **`state_of` читает только `STATES`.** `RECEIPT`/`RESTORED` — учётные
   записи; если считать их состоянием плана, recovery видит `RECEIPT` вместо
   `APPLYING` и не откатывает, а повторный откат отвечает `plan_state:RESTORED`
   вместо `already_rolled_back`.

## Кейсы корпуса (сняты с эталона, итоговые БАЙТЫ)

Корпус `fixtures/corpus/editing/write_apply/` (14 кейсов) и
`fixtures/corpus/editing/rollback/` (4 кейса). Ветки `write_apply` и
`write_rollback` в `tools/_reference_runner.py` копируют фикстуру во временный
каталог, вызывают `prepare_rename` (+ `apply_prepared_rename` для записи) и
возвращают `{files: {rel: sha256}}` по сырым байтам: наружу не переносятся ни
тексты, ни квитанции эталона.

Кейс описывает сценарий (`scenario`): `preview_apply` или
`preview_apply_rollback`. `snapshot_diff` проигрывает его на копии фикстуры
настоящим агентом и сравнивает те же хеши — иначе `write_apply` не проверить:
он требует `plan_id` от предпросмотра.

Запись: 001 `strike→punch` в одном файле; 002 `take_damage→hurt` в трёх файлах
(`probable`+`allow_unverified`); 003 `probable` без флага — эталон применяет,
снимая запрет недоказанных ссылок; 004 `strict`+флаг → `conflict` (динамика);
005 переменная `hp`, исключено `party.gd:6`; 006 переменная `strict` →
`conflict`; 007 новое имя занято → `conflict`; 008 `new_name="2x y"` →
`invalid_input`; 009 локатор `:7` → `not_found`; 010 объявление в аддоне →
`denied`; 011 `old_name="func"` → `invalid_input`; 012 локатор вне проекта →
`denied`; 013 исключение динамического места не снимает strict-отказ →
`conflict`; 014 исключены все места `hp` → `conflict`.

Откат: 001 один файл; 002 три файла; 003 после исключения места; 004
предпросмотр отказал — откатывать нечего, ожидание совпадает с отказом.

У эталона нет своего отката (`history_manager` не портируется, R-08), поэтому
ожидание отката — `before_bytes` плана: байты ДО применения. Инварианты
(идемпотентность, stale, TTL, частичный откат, recovery, лок) в эталоне
отсутствуют — они проверяются тестами, а не корпусом.

## Тесты

- `python/modules/editing/write_apply/tests/test_core.py` — машина состояний на
  поддельном журнале: `PREPARED→APPLYING→COMMITTED`, запрет
  `COMMITTED→APPLYING` без нового digest, идемпотентность (`reuse`), `EXPIRED`,
  `stale_plan`, `plan_state:APPLYING`.
- `python/modules/editing/rollback/tests/test_core.py` — `entry_id`, порядок
  отката (`reversed`, только свои квитанции), `already_rolled_back`,
  `no_receipts`, продолжение после `RESTORED`.
- `tests/py/contract/test_write_apply_contract.py` и
  `tests/py/contract/test_write_rollback_contract.py` — схемы, наборы ошибок,
  `details.reason` в каждом конфликте, нет абсолютных путей и стектрейсов,
  синхронизация с `contract/capabilities/*.json`.
- `tests/py/integration/test_write_apply_disk.py` — настоящий временный проект:
  apply/rollback, байты, CRLF, BOM, повторный apply, stale по правке и по
  digest, TTL, чужой лок, конфликт отката, сбой второго шага, recovery
  `APPLYING` с квитанциями и `EXPIRED`.
- `tests/py/security/test_write_boundary.py` — запись только внутрь проекта и
  `state_dir`; `..`/абсолютный путь → `denied` без создания файла; в WAL нет
  секретов и абсолютных путей; лок снимается после `apply`.

## Причины отказа (закрытый набор)

`conflict` отвечает `details.reason` из `editing/shared/conflict_reasons.py`: кроме причин воронки (`unverified_references`, `dynamic_references`, `all_usages_excluded`, `name_conflict`) есть `already_applied`, `already_rolled_back`, `lock_busy`, `no_receipts`, `backup_missing`, `backup_mismatch`, `post_state_mismatch` и `plan_state:<STATE>`. Каждый `conflict` обязан иметь `hint` (ADR-0005).

## Ход работы

1. Лист создан до кода; затем переписан по факту.
2. Адаптеры: `atomic_write`, `backups`, `lock`; порты модулей; журнал получил
   `append`/`modified_at`/`plan_ids`; `shared/plan_log.py` — единственный
   читатель WAL для обеих механик.
3. `editing/shared/script_edits.py` — чистые байтовые операции (BOM/CRLF/
   смещения), `editing/shared/funnel.py` — путь, сверка `expected`, откат,
   `abort_plan`.
4. `write_apply` и `rollback` (домен, app, tools, module, recovery).
5. Корпус: ветки `_reference_runner.py` (`write_apply`/`write_rollback`),
   `snapshot_diff.scenario_answer`, снятие 14+4 кейсов.
6. Тесты, затем записи.

## Проверки (2026-10-27)

- `selfcheck editing.write_apply` — ok, exit 0: модуль ok (`write_apply`),
  слои/лимиты 449/0, контракт 7 артефактов/0, security ok, unit 43, корпус 14/0.
- `selfcheck editing.rollback` — ok, exit 0: unit 24, корпус 4/0.
- `selfcheck editing.write_preview` — ok, exit 0: unit 45, корпус 16/0 (часть 1
  не тронута).
- `snapshot_diff` — 98 кейсов, 0 расхождений (search 16, functions 17, usages
  18, analyze_rename 13, write_preview 16, write_apply 14, rollback 4).
- `pytest python/modules tests/py` — 284 passed, 0 failed.
- `security_audit --json` — ok; `lint_arch` 449/0; `check_limits` 449/0;
  `gen_contract --check` 7/0.

Полные отчёты: `reports/selfcheck/editing.write_apply.json`,
`reports/selfcheck/editing.rollback.json`.

## Отличия от эталона

Записаны в `docs/deviations.md`: своего отката у эталона нет (корпус отката
сверяет `before_bytes`); корпус записи проигрывается сценарием
`preview→apply`, потому что `write_apply` требует `plan_id`; `state_of`
игнорирует учётные записи `RECEIPT`/`RESTORED`.

## Следующее действие

Часть 3: `editing.scene_ops`/`editing.resource_ops` после `formats/tscn.py` и
моста редактора; `code_intel.function_card`.

