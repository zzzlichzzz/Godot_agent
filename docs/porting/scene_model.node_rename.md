# scene_model.node_rename — read-only план переименования узла

**Статус:** этап 7 — ported, **принято аудитом 2026-10-30 (сессия 56)**: 36/36 кейсов
пересняты мной с эталона `prepare_node_rename` (полный словарь, Base64-байты, diff, порядок
файлов; оба отказа — буквальный текст), 8/8 синтетика (BOM/CRLF/по пути/корень/`scripts_only`/
без скриптов/`%Unique`), 1/1 вложенный `previous_name`; свои прогоны 1684 non-live + 3 live
(= collect-only), selfcheck 162/36, контракт 15, snapshot 345/0, layers/limits 472/0;
мутации M1 17 / M2 17 / M4 3 / M5 2 / M6 2 / M7 13 red, M3 эквивалентен по корпусу —
поведение ветки доказано отдельным дифференциалом, корпусу не хватает вложенного
`previous_name` (долг); подложки P1 (`gen_contract` 15 fail) / P2 2 / P3 1 red, все
файлы восстановлены побайтово.
**Обновлено:** 2026-10-30

## Цель

`node_rename_preview` возвращает план правок сцены и прикреплённых скриптов как
данные. Он не применяет план, не создаёт WAL, не пишет проект, не вызывает мост,
не меняет историю редактора. `scripts_only` исключает сцену из плана и счётчика
ссылок; `previous_name` задаёт имя, известное редактору, а не новую структуру сцены.
Основание: `docs/porting/_start-prompt.node_rename.md`, C.6.

## Старый код

Эталон read-only: `тест-плагина-ии/addons/Godot_agent/godot_agent`;
commit `ba0535d4dec43c32750e601a6ca86e377abc6af3`.
`node_refactor.py`: 46881 байт, SHA256
`2d708a384177fa0a8d4636f3f2dd373508ee316216319edf7d793255d8918a29`.

| Файл / фактический якорь | Поведение | Новая граница |
|---|---|---|
| `node_refactor.py:40-48` | Сырые байты; UTF-8-sig strict, при ошибке UTF-8 replacement; отдельный BOM | Чтение через собственный порт, чистое кодирование без изменения EOL |
| `:51-70` | Политика сцены и нормализация имени | PathPolicy и буквальные отказы; `.scn` — явно заданный промптом гейт, не поведение эталона |
| `:73-160` | Структура со spans, connections, анимации | Только принятый `formats.tscn.structure` |
| `:163-222` | Относительный путь и поиск узла | Уже реализовано в C.4; копировать нельзя, нужен согласованный reuse |
| `:225-288` | `prepare_node_rename`, seen_name, коллизии, new_path | Чистый домен |
| `:297-378` | Заголовок, parent детей, connections, анимации | Правки по исходным смещениям через `tscn.patch` |
| `:379-406` | Обратный порядок, diff, BOM, счёт ссылок сцены | Не менять принятый patch; отдельный подсчёт обоих режимов |
| `:408-487` | Прикреплённые скрипты, относительные пути, `%`, `$`, вызовы | Чтение через порт; синтаксические замены только в formats/gdscript |
| `:489-504` | `find_child`, lint после изменения, буквальный отказ | Один принятый lint, без чужого domain-импорта |
| `:506-539` | Байты скрипта, files, reference_count, полный результат | Именованная JSON-проекция после решения о bytes |
| `project_tools.py:1851-1917` | Структурный build_diff_preview, context=3, max_lines=600, хвостовая пустышка | kernel.diff.unified не эквивалентен; нужен буквальный структурный diff |
| `apply_prepared_node_refactor:969` | Применение и история | Вне C.6 |

Уточнение якорей промпта по прочитанному исходнику: `find_child` находится на
489-495, lint-отказ — на 497-504, а не 481-487 / 490-497. Хеш эталона совпал;
исправлять сам промпт или эталон не требуется.

## Старые тесты

`tests/test_node_refactor.py` прочитан целиком (374 строки); код не переносится.

| Строка tests-map / файл | Семейство | Судьба | Граница кейсов C.6 |
|---|---|---|---|
| 79 `test_node_refactor.py` | unit | corpus | prepare rename: дети, connections, анимации, скрипты, scripts_only, previous_name, обратное имя; apply/rollback/reparent/delete остаются вне среза |
| 56 `test_external_move_sync.py`; 64 `test_gdscript_move_fixes.py` | unit | corpus | Историческая принадлежность сохранена; перенос файлов/узлов не закрыт rename-preview |
| 80 `test_node_refactor_flow.py` | flow | corpus | Сценарий нового read-only инструмента не закрывает старое применение |
| 81 `test_node_refactor_live.py` | live | corpus | Реальное rename/apply/undo не закрывается unit или существующими 3 smoke-тестами |
| 113 `test_resource_action_flow.py`; 114 `test_resource_actions.py` | flow/unit | corpus | Ресурсные действия вне C.6 |
| 121 `test_scene_action_flow.py`; 122 `test_scene_actions.py` | flow/unit | corpus | Только план rename, не общий action-flow |
| 130 `test_tree_excludes_addon.py` | unit | corpus | Политика доступа проверяется отдельно; другие механики не объявляются перенесёнными |

Строки 44/82 (`repro_node_rename_double_intercept`, `test_node_rename_intercept`)
принадлежат `editing.symbol_rename`; не переassign и не считать покрытием C.6.
Все судьбы целевых старых строк заданы; `docs/tests-map.md` не меняется.

## Корпус

Снято **36 кейсов / 110 входов**, 22 успешных плана и 14 буквальных отказов,
в `fixtures/corpus/scene_model/node_rename/`. Один одноразовый `python -B` скрипт
с обычными `_bootstrap`/`node_refactor` импортами actual-old; byte-поля base64,
исключены только scene_res/absolute. Manifest содержит дату, commit, SHA/байты
источников, всех входов и кейсов, decoder/projection; каждый вызов доказал
равенство SHA всего fixture-проекта до/после. Capture.py удалён до тестов/кода.
Первый run остановился на настоящем FileNotFoundError; второй перезаписал только
свои проверенные файлы и поймал этот тип отказа. Exit0; обе версии stderr сохранены.

| Обязательные семейства | Откуда | План |
|---|---|---|
| Простое имя, потомки, обе стороны связи, несколько правок и анимации | actual prepare_node_rename | Буквальные планы и порядок files |
| `$`, quoted `$`, get_node/get_node_or_null/has_node, find_child, `%Unique` | actual prepare_node_rename | Включая характерные старые regex-ограничения, без улучшения |
| scripts_only, previous_name, обратное имя, коллизия, unchanged/unknown/ambiguous | actual prepare_node_rename | Счётчик, неизменность сцены, тип и текст отказа |
| Lint-отказ, BOM/CRLF/lone CR, битая кодировка, missing/path/tres | actual prepare_node_rename | Не смешивать отказ эталона с новыми safety-гейтами |
| Общий скрипт нескольких узлов, порядок ресурсов, недоступный/отсутствующий скрипт | actual prepare_node_rename | Сохранять порядок и пропуски эталона |

## Спецификация

- ToolSpec `node_rename_preview`, `effects=read`, idempotent, cheap;
  карточка `contract/capabilities/node_rename_preview.json`, 14→15.
- Args: обязательные `path`, `node`, `new_name`; необязательные `update_scripts=true`,
  `scripts_only=false`, `previous_name=""`; additionalProperties=false.
- Result по §2 промпта: action, scene, old_name, new_name, old_path, new_path,
  target_node_path, files, reference_count, affected_paths, scripts_only, previous_name.
- У native plan также есть `scene_res` и `files[].absolute`; проекция исключает
  дубль scene_res и host absolute, но не меняет остальные значения или порядок.
- `before_bytes` / `after_bytes` в эталоне — реальные bytes, НЕ их длины.
  Пользователь утвердил lossless Base64 ASCII; unit проверяет decode и SHA.
- Files: action, path, before_hash, before_bytes, after_bytes, diff, occurrences;
  diff сохраняет lines/added/removed/truncated и добавленные path/action.
- Ошибки invalid_input/not_found/denied; буквальные NodeRefactorError, без host paths.
- READ_TEXT_MAX_BYTES = 4 MiB из kernel; эталон не ограничивает чтение — это
  safety-различие фиксируется отдельным тестом, а не выдаётся за старую семантику.
- Собственные runtime-checkable Protocol; domain без IO/re/команд, app ≤80,
  tools ≤150, новые файлы ≤400. Никаких apply/undo/editor verbs.

## Решения по ходу

| Дата | Решение / предложение | Основание |
|---|---|---|
| 2026-10-30 | Только план как данные; ModuleSpec.corpus=corpus; старые 3 live — регрессия, не перенесённый rename/apply | §1/§6 C.6, R-12/R-17 |
| 2026-10-30 | Статусы шагов листа/PROGRESS обновлять по R-19; аудиторские шапки и независимое принятие не трогать | §1/§8 требуют лист и статус ported; вводная «этап не ставишь» не отменяет R-19 |
| 2026-10-30 | Пользователь утвердил lossless base64 для byte-полей; исключить только absolute/scene_res | JSON не поддерживает bytes; запись остаётся данными |
| 2026-10-30 | Пользователь разрешил перенос существующих C.4 lookup/relative-path функций в shared/node_path и C.4 делегирование | Один экземпляр логики, поведение и corpus C.4 не меняются |
| 2026-10-30 | Пользователь разрешил публичный reexport lint_gdscript, собственный callable-порт C.6 и минимальный bootstrap bind | Чужой domain не импортируется C.6; frozen lint_arch не меняется |
| 2026-10-30 | Пользователь разрешил append-only format-операции, без изменения старых APIs/__all__ | В gdscript нет операций rewrite; локальный regex в C.6 запрещён |
| 2026-10-30 | Пользователь разрешил C.6-only 5 inventories + context001 count13→14/name/read-effects/зависимый hash | Reverse byte/SHA proof обязателен; остальные expectations не меняются |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-30 | 1. лист создан | Обязательные документы/промпт/actual source/старый unit прочитаны; baseline снят до первой правки |
| 2026-10-30 | 2. корпус | 36 native cases / 110 inputs; 22 plans / 14 refusals, full dict/order, hashes; capture.py удалён до тестов |
| 2026-10-30 | 3. спецификация + красные тесты | 162 collected/executed: 160 failed / 2 passed / 0 errors, exit1 на production stubs. Manifest/AST зелёные; full plans/refusals/schema/dispatcher/format/limits/reuse красные |
| 2026-10-30 | 4. код | Собственные RawReader/Linter; single shared lookup/C.4 delegation, public lint/default bind; append-only formats/закрытые star APIs, pure plan, app без apply. Native selfcheck162/corpus36, contract15/snapshot345/static472/securityok |
| 2026-10-30 | 5. двойной прогон / M1–M5 / P1–P3 | M1 children55/120, M2 forward55/120, M3 count9/120, M4 lint6/120, M5 self-collision3/120 red; P1 stale1/1+gen red, P2 expected2/36, P3 IO1/1+lint red; 8/8 finally byte/SHA/EOL restore |
| 2026-10-30 | 6. клиентская проверка / live-регрессия | 8/8 args-file CLI probes/full parity/project SHA unchanged; nonlive1684 exact IDs/67files +existing live3; selfcheck162/corpus36, contract15/snapshot345/static472/securitygreen |

## Проверки

Независимая база до листа: 1430 файлов, 26 промптов, **15** mechanic sheets
(именные *.md без README и _*.md), debris=0; после нового листа станет 16,
а не 17. Счёт в промпте не исправлялся. Old tree: 622 working-tree файла,
HEAD ba0535d4, ровно два чужих untracked лога, diff пуст.

| Команда / группа | Фактический результат |
|---|---|
| pytest python/modules | 598 passed |
| pytest code_intel/contract/formats/kernel | 543 passed |
| pytest integration | 318 passed |
| pytest security/tools | 60 passed |
| collect-only non-live | 1519 unique ID / 62 файла; exact executed=collected |
| live bridge / live editor | 1 passed / 2 passed; всего 3, no fail/err/skip |
| gen_contract --check | 14 / 0 |
| snapshot_diff | 309 / 0 |
| lint_arch / check_limits | 467 / 0; 467 / 0 warnings |
| security_audit | ok |

Baseline stdout/stderr/XML/SHA и exact-ID proof:
`%TEMP%/opencode/node-rename-c6-*` (approved opencode TEMP).
Первый snapshot в групповом драйвере превысил ошибочно выбранные 12 с;
это не успех. Отдельный повтор с timeout28 завершился: 309/0, exit0.

Вердикт `python -B tools/selfcheck.py scene_model.node_rename`:

```text
selfcheck scene_model.node_rename
  module         not_implemented заготовка: RuntimeError: python.modules.scene_model.node_rename.module: нет MODULE (R-05)
  layers         ok              файлов 467, нарушений нет
  limits         ok              файлов 467, предупреждений 0
  contract       ok              артефактов 14, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет: python/modules/scene_model/node_rename/tests
  corpus         not_implemented нет корпуса механики: fixtures/corpus/scene_model/node_rename
вердикт: blocked
```

Exit2, не успех. Отчёт: `reports/selfcheck/scene_model.node_rename.json`;
stdout/stderr: `%TEMP%/opencode/node-rename-c6-stage1-selfcheck.*`.

Stage3 native selfcheck: exit1/verdict fail; module без MODULE, static468/0,
contracts14/0/securityok, unit116 failed + 2 passed; corpus не привязан до MODULE.
Отдельный permanent suite: **162 tests / 160 failed / 2 passed / 0 errors**,
`node-rename-c6-red.{xml,stdout,stderr}`. Reference после capture: 622 SHA равны базе.

Stage4: первые 162 теста зелёные после исправления только собственных неверных
допущений о validate (возвращает problems) и fail-envelope (плоский kind/message).
Оба исходных вывода сохранены. Дополнительно **2/2 красных** кейса порядка отказа:
коллизия/unknown должны предшествовать чтению attached; вынесен один preflight,
native selfcheck **162 passed / corpus36 / verdictok**. Ещё **1/1 красный** guard
star-export ловил собственное расширение gdscript.__all__; убрана только своя
строка, операции доступны явно. Accepted tscn/gdscript prefixes byte-identical.
Schema не поддерживает tuple/pattern-validation: четыре ячейки diff проверяются
unit буквально; Base64 проверяется строгим decode/SHA, без расширения schema.

C.4 reverse byte/SHA и AST обеих moved функций совпали; native C.4 **285/65**
(247 прежних +38 новых integration по prefix node*), lint **126/37**. Lint core
не менялся. **7/7** inventory/context reversals byte/SHA/EOL идентичны,
`node-rename-c6-composition-proof.json`; context001 SHA
`cd35d4a883df03004f6e242ccf7e59389014d4d61c10ba102062e40403aa955e`.

```text
selfcheck scene_model.node_rename
  module         ok              scene_model.node_rename (node_rename_preview)
  layers         ok              файлов 472, нарушений нет
  limits         ok              файлов 472, предупреждений 0
  contract       ok              артефактов 15, расхождений нет
  security       ok              нарушений нет
  unit           ok              162 passed in 1.63s
  corpus         ok              кейсов 36, расхождений нет
вердикт: ok
```

Stage4 exit0, evidence `node-rename-c6-selfcheck-stage4-preflight.*`;
snapshot **345/0 =309 accepted+36 C.6**, tools untouched.

Submitted-file mutations по одному, без накопления; каждый backup сделан
`shutil.copyfile`, finally восстановил исходные SHA/bytes/LF/CRLF **8/8**.
M1 затронул только новый append-only блок tscn; M2 изменил только C.6 caller,
accepted patch не менялся. Все pytest exit1, actual failures, zero errors.
P1/P3 дополнительно дали native gen_contract/lint_arch exit1. Commands, IDs,
JUnit/stdout/stderr/before-mutated-after в `node-rename-c6-{M1..M5,P1..P3}.*`.
Disposable mutation driver удалён, точные byte-backups оставлены аудитору в TEMP.

Final disjoint pytest: **680 modules +588 code_intel/contract/formats/kernel
+356 integration +60 security/tools =1684 non-live**. Exact executed/collected
unique sets equal1684, **67 files**, no failure/error/skip/duplicate. Existing
bridge1/editor2 live passed, всего **1687**; это smoke bridge/editor, не перенос
rename apply/undo. Форматные3 теста вне native selfcheck; всего C.6 новых165.
После cleanup все165 повторены зелёными.

CLI `tools/probe.py node_rename_preview --args-file ... --project ...`:
002 full edits/scripts, 006 scripts_only, 007 previous_name, 008 reverse,
016 literal lint refusal, 018 BOM, 022 denied, 035 truncated diff. **8/8** whole
native projections/refusals совпали, before/after project SHA одинаковы.
`node-rename-c6-probes-proof.json` содержит argv/answers/hash maps.

Final native selfcheck: **162 passed in1.93s /36 corpus/0, verdictok**;
C.4 **285/65**, lint **126/37**. Contract15/0, snapshot345/0, layers/limits472/0,
securityok. Old **622/622 SHA unchanged**, HEADba0535d4, только два прежних
чужих untracked logs, diffempty. Источник lint/schema/tools/editorverbs frozen.

Godot live импортировал новые fixture scripts и создал72 `.gd.uid`. Проверены
их ASCII uid-format, отсутствие в baseline, принадлежность только110 собственным
manifest inputs; удалены по точному списку, не recursive. Ни один исходный UID
не изменён/удалён. SHA inventory удаления в `node-rename-c6-generated-uids.json`.
Итог **1588 files/+158/0 baseline deletions**, corpus147=36cases+110inputs+manifest;
11 остальных=Python5/tests3/sheet1/report1/card1. Debris0,26prompts/16named sheets.

Final scope proof: C.4 extraction reverse byte equality + AST двух функций,
bootstrap reverse ровно двух bind-строк, original format/lint-facade/WORKLOG
prefixes; composition7/7, mutation8/8. Accepted schema/checking tools/editorverbs/
lint core/прочие mechanics/cards/corpora/tests-map и auditor-only файлы frozen.
`node-rename-c6-final-scope-proof.json` + final inventory в approved TEMP.
New card SHA `0e6646113a57a8790e0e668450750f29ea4f0ca5ede96684369368c6d97c97af`,4855B.
Диагностические reverse-попытки выявили только снятую patch-tool terminal blank
line bootstrap; восстановлен исходный один LF, reverse bytes теперь совпадают.
Неверный ключ file вместо path исправлен только в census driver, не manifest.
13 authorized byte-backups +8 independent mutation backups сохранены аудитору.

## Следующее действие

Независимый C.6 аудит: новый actual-old capture36, whole plans/refusals,
M1–M5/P1–P3, own regression/IDs/probes/gates и семь scope reversals; только
аудитор ставит acceptance/README/handoff. Следующую механику не начинать без промпта.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Нет активных scope-блокеров | Пользователь выбрал Base64 и точечный reuse; поведение принятых механик/проверочные инструменты остаются замороженными |
