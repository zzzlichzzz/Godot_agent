# scene_model.tree — сводка файла сцены

**Статус:** этап 7 / ported (готов к независимому аудиту C.3)
**Обновлено:** 2026-10-29

## Цель

Read-инструмент `scene`: дословная текстовая сводка эталона и полная структурная
проекция узлов, связей и ресурсов. Без Godot, записи, исправлений и иных механик.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/project_tools.py:1269-1367`, describe_scene | путь, utf-8-sig/errors=replace, ресурсы, узлы/скрипты/связи, текст, обрезка | путь/порт в app, разбор только formats/tscn.py, проекция/рендер в domain |

Commit `ba0535d4dec43c32750e601a6ca86e377abc6af3`; SHA256 файла
`79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877`.
Номера промпта смещены: функция заканчивается на 1367, чтение 1278, глубина 1313,
обрезка 1365–1366. Поведение берётся из реального файла, не из пересказа.

## Старые тесты

Собственных строк tree в tests-map нет. Строки 56–130 принадлежат node_rename;
владельцы/судьбы не меняются, новые строки не добавляются. Старые тесты/host-код
не копируются и не запускаются как новая suite. Корпуса C/C.2 неприкосновенны.

## Корпус

Сняты40 случаев/34 input-файла до кода: minimal/player, вложенность/parent=".",
instance/script/root-связи, unique/editable, sub/resource, missing attrs/duplicate IDs,
BOM/CRLF/loneCR, empty/no nodes, text/binary .scn/чужой suffix, max_chars/exact
boundary/Unicode/битый UTF8. Один TEMP python -B-скрипт вызывал старый describe_scene
обычным импортом из старого каталога, снимал результаты/отказы и manifest; удалён
до реализации. Проекция из локальных данных реального вызова через trace
(без изменения эталона/нового парсера). Ожидания не правились руками.

## Спецификация

- `scene(path,max_chars=12000)`: read/idempotent/cheap, strict schema.
- `{text,truncated,nodes,connections,resources:{ext,sub}}`. Узлы
  `{name,type,parent,path,depth,script,instance}`, nullable parent/script/instance;
  связи `{from,to,signal,method}` с исходными путями; ext `{id,type,path,uid}`, sub `{id,type}`.
- Общий READ_TEXT_MAX_BYTES, порт RawReader.read_raw, существующий fs/default_ports.
- `.tscn`/`.scn` (текстовый .scn эталон принимает), typed invalid_input/not_found/denied,
  без абсолютных host-путей. max_chars целое ≥0, без нового произвольного максимума.
- Порядок/отступ/скрипт/instance/ресурсы/обрезка буквально; truncated по факту
  len полного текста > max_chars. Структура целиком, даже когда текст обрезан.
- Domain без IO/парсера. Только formats разбирает Godot-текст; данные не команды.
- patch/пересечения и форматный корпус не меняются, баги эталона не исправляются.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-29 | Добавить минимальное `formats/tscn.py: rows(text)` с отдельным паритетом/мутациями | structure/fields теряют sub/missing IDs/duplicate rows и имеют другие regex/границы; это третий ответ в единственном format-файле, не второй parser в модуле. Старые функции сохраняются дословно. |
| 2026-10-29 | rows отдаёт raw parent/attrs/связи/ресурсы, domain считает depth/path и рендерит | глубина — правило сводки (M1), path: root '.', direct name, иначе parent + '/' + name |
| 2026-10-29 | utf-8-sig/errors=replace и universal newlines до rows | совпадает с чтением эталона, включая одиночный CR |
| 2026-10-29 | Baseline до листа 1018 файлов, ноль мусора | полный SHA256-инвентарь TEMP scene-tree-c3-baseline.json; старые файл/логи отдельно |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-29 | 1. лист/обязательное чтение/эталон | до production-кода и корпуса, old Git два чужих ??/пустой diff |
| 2026-10-29 | 2. корпус | 40 cases / 34 inputs, реальный describe_scene, locals из trace, manifest SHA256; скрипт удалён до реализации |
| 2026-10-29 | 3. спецификация/тесты | 152 tests, 150 failures, 0 errors, 2 passed, exit1 на production stubs; 35 new format tests и один additive API pin, остальные own module/integration |
| 2026-10-29 | 4. код | rows единственно в formats (старый prefix byte-identical после обратного API pin); core/app/Protocol/ToolSpec/MODULE; только новая scene.json; native selfcheck ok/unit128/corpus40 |
| 2026-10-29 | 5. дифференциал/мутации | snapshot179/0; M1–M3/schema/expectation/IO/rows F1-F2/card red; каждый файл byte-restored, SHA256/EOL одинаковы |
| 2026-10-29 | 6. real read/live регрессия | probe scene exit0/full expected; live3 passed20.72s; 809 non-live;812 exact collected/executed IDs,52 files; native gates/selfchecks ok |
| 2026-10-29 | 7. ported/записи | sheet/PROGRESS/parity/WORKLOG49 закрыты; готов независимому аудиту, auditor-owned README/handoff не менялись |

## Проверки

Аудит 2026-10-29 (сессия 50): **принято на этапе 7 своими прогонами** — 809 non-live + 3 live
(= collect-only), корпус переснят с эталона через `app.call` 40/40 и дифференциал по 50 файлам
`fixtures/**` (0 расхождений), M1–M4 и P1–P3 красные, `tscn.py F535566EF2FE`, `gen_contract` 11,
snapshot 179/0. Свидетельства — `docs/WORKLOG.md`, сессия 50.

Baseline: 250 + 348 + 60 = 658 non-live, live 3 (21.83s), contract 10,
layers/limits 456/0, security ok, gd_lint selfcheck unit126/corpus37,
scene_ops unit25/live. Snapshot до кода уже увидел новый corpus: старые139 совпали,
новые40 красные на stub; это не заявляется успешным общим прогоном.
Эталон project_tools.py 102471 bytes. Реализация: module tests50 + formats135 =185 passed;
integration scene66 зелёных через native selfcheck. Selfcheck unit128 включает own116
и 12 существующих test_scene_ops.py по штатному glob test_scene*. Полный snapshot179/0
(139 прежних +40 новых). Contract11, layers/limits458/0, security ok.
Первый integration/selfcheck был red: uncaught domain ValueError→internal (4 отказа);
app теперь типизирует его invalid_input дословно. Ошибочный test-pin effects tuple исправлен
на фактическое поле ToolSpec str='read', требование read/idempotent/cheap не ослаблено.
Selective generation через tools.gen_contract.rendered(): CLI без флагов проверяет,
--write переписал бы чужие карты. Другие десять artifacts не менялись.
Разрешённый context tools snapshot: только count10/names+scene/effect read и case hash
fee9752ce0ed1e480b593af0753c37ff06e30a2fb5a75adbe36c01160cb16dc3;
два contract inventory и gd_lint integration inventory добавили scene/count10.
Обратные byte-изменения воспроизводят baseline SHA256; исходные CRLF сохранены.

### Submitted-file mutations (строго по одной)

| Мутация | Прогон | Доказательство |
|---|---|---|
| M1 depth всегда1 | parity33: 5 failed | nested/missing_attrs/out_of_order/large/truncate |
| M2 без script text | parity33: 7 failed | player/script/resources/duplicates/sections/comment_header/relative |
| M3 без text cut | parity+boundary37: 5 failed | truncate/zero/unicode_cut и limits0/14 |
| TOOLS добавляет result-schema field без card | gen_contract exit1 | устарел scene.json |
| EXPECT меняет один text | parity+pin34: 2 failed | ровно003-nested.tscn + manifest pin |
| IO import pathlib в domain | AST1 failed, lint_arch exit1 | запрещён IO-импорт pathlib |
| F1 rows теряет uid | rows34: 1 failed | resources.tscn |
| F2 rows не сбрасывает cur на секции | rows34: 2 failed | editable.tscn/sections.tscn |
| CARD искажает tool_name | gen_contract exit1 + contract test1 failed | scene.json gate и strict equality |

shutil.copyfile backups в approved TEMP; каждый вывод restored identical: True.
Core DB7164485858, 2583 bytes/58 LF/0CRLF; tscn F535566EF2FE,9550 bytes/228 LF/0CRLF;
tools A0F7EA984EFC,2367 bytes/40 LF/0CRLF; case003 18AD06399BAD,1274 bytes/58 LF/0CRLF;
card 80A0AB59DDD8,4692 bytes/195 LF/0CRLF. Полные JSON/XML/stdout/stderr сохранены TEMP.
Первый IO runner ожидал слово «наруш» в native выводе; AST и lint были red, но runner
assertion упал. После коррекции проверки фактического pathlib повторный прогон подтвердил
оба exit1 и byte restoration. Это не изменение теста/проверки механики.
Измеренные baseline-якоря:
schema 629FCE54E6FE, lint_arch 1FAD8E7470D5, gen_contract FA7E6E91C872,
security_audit 2CF0D7F6B1AF, editor_verbs CDAF8D23A6BF, executor B7AFF592B75D,
tscn BF844574D6E5, gd_lint core 9EBB211FB387.

Финал: modules300 passed1.66s, main449 passed19.33s, guards60 passed4.36s,
live3 passed20.72s: 809 non-live +3 live =812. Все 812 collected/executed уникальных
node IDs совпадают точно,52 файла (50 non-live,2 live), errors/failures/skips0.
Formats135, selfcheck tree128 passed1.17s/corpus40/0, gd_lint126 passed4.49s/corpus37/0,
scene_ops25 passed0.26s/corpus live. Contract11, snapshot179/0, layers/limits458/0,securityok.
Реальный native probe scene через dispatcher/default_ports/fs exit0, полный ответ001-player.tscn
совпал с эталоном; JSON args через TEMP --args-file, stdout/stderr отдельно.
Audit:1018→1101 files,83 additions,удалений/кэшей/backup/tmp/orig/zz0;
baseline-якоря (кроме разрешённого rows) и все старые corpora неизменны.
Удаление только rows/API дополнения восстанавливает SHA256 принятого tscn BF844574D6E5.
Reverse-byte proof разрешённых foreign inventory/context/API изменений проходит.
Старый Git два чужих??/empty diff, project_tools/оба лога SHA256 identical.
Доказательства: TEMP scene-tree-c3-final-audit.json, collect-final.txt,
{modules,main,guards,live}-after.xml, probe-native.stdout/stderr и native final stdout/stderr.
После финального scope audit owned TEMP scripts/copyfile backups удалены,
submitted hashes проверены; diagnostic metadata/XML/JSON/stdout/stderr сохранены.

### Честные границы

- `.scn` допускается как в эталоне, бинарный Godot-парсер не добавлен; пустые/неузловые
  данные дают literal refusal. Quoted/escaped/malformed header quirks не исправляются.
- parent/path — структурные данные, не реальный editor tree; parent='.' depth1,
  иной parent.count('/')+2, без нормализации глубины/родителей. UID/duplicate rows сохранены.
- max_chars считает Unicode-символы, suffix сверх лимита; структура всегда полная.
- read_raw и4MiB — существующая безопасная подложка, не новая запись/редакторная механика.
- gen_contract проверяет ToolSpec/card, не произвольный domain result; runtime-result
  shape отдельно проверен strict schema test. Dispatcher/замороженный validator не менялись.
- Старый format corpus C и gd_lint corpus C.2 неизменны; overlap patch и wiring109
  остаются прежними отдельными вопросами. Новые tests-map строки не добавлялись.
- Единственные разрешённые изменения принятых fixtures/tests — registry composition
  count/names/effects/hash и API pin rows; обратные bytes совпадают с baseline.
- Stage7 здесь — porter's verification, не заявление независимой приёмки.

## Следующее действие

Независимый аудит C.3 по _start-prompt.scene_tree.md §7: пересъёмка/сравнение текстовых bytes и full projection,
мутации submitted files и старого format prefix, native gates/test-ID reconciliation; новые механики не начинать без отдельного промпта.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| snapshot/inventory/подложка | Разрешены пользователем: «продолжай по рекомендованным». Итог 139 + N / 0; только tools count/names/effects + hash context/001 и добавление scene в три списка; schema tools без обновления карты → gate red, отдельный strict runtime-result тест. Runner/чужие реализации неизменны. |
