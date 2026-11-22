# ADR-0017 — transformed bytes `.tres` и ограниченное resource `replace_raw`

Статус: **принят** аудитом 2026-11-03 (сессия 77; только моими прогонами — non-live 5225/0, selfcheck ok 503/271 ×2, snapshot 271/271 ×2, live 3/0, своя мутация SEC-24 guard `res://project.godot` red→restore→green, гейты 568/0 + limits 568/2 с R-06/D18-потолком 8400). Дата решения о границе: 2026-11-02, аудитор, D18 (`docs/porting/editing.resource_ops.md:1048–1054`).

## 1. Источник transformed bytes

Байты производит чистый section/span-трансформер в domain `resource_ops`.
IO выполняет module-owned порт поверх существующего DiskFileSystem; домен
получает raw bytes, нормализованный action и immutable dependency facts.
`replace_raw` не исполняет resource operations: он публикует готовые байты.
Шесть операций меняют только значения и необходимые ext_resource/sub_resource
секции, Animation tracks, SpriteFrames animations, Theme keys и TileSet atlas.
Нетронутые spans, комментарии, порядок, existing IDs и UID — byte-exact.
Новые IDs детерминированно выбираются среди свободных; одна цель даёт один output.
Неизвестный класс/property/Variant или неоднозначная структура — отказ до WAL,
не подделанный ClassDB/semantic preview. Граница поддержанного фиксируется кейсами.

## 2. Байтовый контракт и отказ BOM

UTF-8 BOM на входе: `invalid_input`, дословное native сообщение
`ResourceLoader не смог загрузить ресурс`, native code `load_failed`;
диагностика native Godot 4.6.3: `Parse Error: Expected '['.`. Записи нет.
BOM не принимается и не «сохраняется ради паритета» в непригодном engine файле.
CRLF, lone CR, mixed EOL сохраняются в нетронутых spans. Новые строки при
замене используют EOL заменяемой строки; при вставке — доминирующий EOL файла.
При равенстве частот доминирует первый встреченный EOL, при их отсутствии — LF.
Если final EOL отсутствовал, он не добавляется; если был — сохраняется.
Mixed EOL и отсутствие final LF имеют отдельные byte-level пины.
Native serializer приводит CRLF/CR к LF и добавляет final LF — это утверждённое
отклонение D18, а не обещание побайтового совпадения с ResourceSaver.

## 3. Почему `replace_raw` и чем ограничено расширение

Новый op не вводится. Только этим proposed ADR расширяется назначение accepted
ADR-0016: resource_ops может подготовить один `replace_raw` на resolved `.tres`.
Accepted ADR-0016 и `script_edit` не меняются. Payload — strict base64 готовых
raw bytes, `expected_hash` — SHA256 исходных raw bytes, не normalized text hash.
Canonical action digest независим от BOM/EOL/форматирования исходника;
raw expected hashes отдельно обнаруживают смену байтов. Изменение после preview
и repeat apply дают `stale_plan`; повтор finalize native не является repeat apply.
Dependencies read-only, их raw hashes включаются в preflight без write steps.
Target и dependencies проходят SEC-23 resolved identity/casefold/containment
до PREPARED. Addons/history/project.godot/escape запрещены при любых flags,
root plugin.cfg допускается только dependency. Generic guards неизменны.
Public projections не содержат raw/transformed bytes или абсолютных путей.
TOOLS=(), новых публичных инструментов нет, contract остаётся 27.

## 4. Порядок записи и компенсаций

Все операции одной цели сворачиваются до одного unique-target шага. Если план
содержит несколько целей, порядок фиксирован, все expected проверяются до
первого эффекта под непрерывным project lock. Общая воронка остаётся единственной:
validate → PREPARED → preview → preflight → backup → durable EFFECT_INTENT →
write_raw → durable RECEIPT → COMMITTED. Нет отдельного resource executor/WAL.
Rollback/recovery идут в обратном порядке receipt/intent по целям, возвращают
raw backups byte-exact и не перезаписывают чужую poststate-правку. Dependencies
не переписываются, нового batch API и новых filesystem примитивов нет.

## 5. Почему editor-половина снята

Четыре свежих actual-native применения в dossier `c24-f1-native-20261102`
охватили шесть operations с настоящим EditorPlugin, original panel/executor/
ResourceSaver/host, commit и raw rollback. Отдельная BOM-проба отказала без эффекта.
Они показали, что loader/saver не выполняет требуемый D18 byte-preserving контракт.
Аудитор выбрал (б): текстовый domain, без editor/** и новых verbs. Взамен принято
bounded textual validation: unsupported отказывает, native Inspector/game/import
checks и preview/cache/import notifications не эмулируются. UI/HTTP/auth proof
не заявлялся. Самодельный semantic hash не подменяет native engine validation.

## Закрытые отклонения и infrastructure

Только D18: (1) EOL/final EOL preservation, BOM-отказ; (2) span-сериализация,
comments/order/IDs/UID; (3) bounded textual validation вместо ClassDB/editor
preview; (4) existing WAL lifecycle вместо native temporary-save/reload/cache;
(5) R-06 cohesion editing-area: 8000 остаётся базой, warning только до 8400,
выше 8400 error. Последнее разрешает только area-ветку tools/check_limits.py,
без resource-specific/per-file исключений, иных лимитов или selector-изменений.
Red на нынешний 8001 error предшествует правке, 8401 error пинится после;
mutation удаления верхнего guard должна сделать safety pin красным.
Причина cohesion: resource span/operations связаны одним immutable document и
общим raw-byte контрактом; перенос feature logic в kernel или дробление по
размеру нарушило бы R-05/R-06/R-11. Потолок не является открытым расширением.
SEC-24 и deviations фиксируются до production. Новые отклонения/порты вне
module scope/правки infrastructure требуют отдельного решения аудитора.
