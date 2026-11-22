# scene_model.connections — связи сигналов сцены

**Статус:** этап 7 — ported, принято аудитом 2026-10-29 (сессия 54): свои прогоны 25/25 повторно сняты с эталона, дифференциал 25 кейсов 0 расхождений, M1/M6 и подложка `import pathlib` красные, файл восстановлен побайтово (`4F7366C418DD`, 761 B).
**Обновлено:** 2026-10-29

## Цель

Отдельный read-only инструмент `connections` с входом `{path}`: существующие
связи сигнала в порядке файла, включая дубли и неполные записи. Не исправляет
сцену и не проверяет существование функций в привязанных скриптах.
Выбранная явно названная проекция: `{connections, text}`. `connections` —
буквальный третий компонент `scene_deps.parse_scene`; `text` — только строки
отображения связей из `project_tools.describe_scene`, включая `<root>`.
Два представления могут отличаться на неполных/экранированных атрибутах: это
разные уже принятые format-views, не унификация поведения.

## Старый код

| Файл | Настоящая сигнатура / возврат | Как делим |
|---|---|---|
| `scene_deps.py:120-172` | `parse_scene(text)` → `(ext:dict, nodes:list, connections:list)`; связь `{signal,from,to,method}`; отсутствующие атрибуты — `""` | только существующий `formats/tscn.fields`, без копии parser |
| `scene_deps.py:102/111` | `_parse_attrs(head)` → dict, `_attr_id(raw)` → str/null | уже в `tscn.py`, не дублировать |
| `project_tools.py:1269-1367`, особенно `1320-1328` | `describe_scene(project_root,godot_path,max_chars=12000)` → string; непустые `signal`/`method` и присутствующие `from`/`to`; пустой/`.` endpoint отображает `<root>` | дополнительный источник M1 и display; существующий `tscn.rows`, не чужой domain |
| `scene_deps.py:271/362`, `main.py:1904/1930` | scene analysis → `(new_text,added,notes)`; script analysis → `notes`; старый main меняет action/ставит заметки | относится к другому листу; не выполняем write-обогащение |

Frozen commit `ba0535d4dec43c32750e601a6ca86e377abc6af3`, scene_deps
19866B/SHA256 `dbd502afeca7fa2fe97d49a995438c551d313d1713e6591865ab2bf3b053067b`.
Нового standalone API `connections` в эталоне нет. В `parse_scene` **нет** ни
подстановки `<root>`, ни фильтра существования method-функции. Display в
`describe_scene` фильтрует только атрибуты, не читает скрипты.

## Старые тесты

| Источник | Семейство | Судьба | Что берём |
|---|---|---|---|
| `docs/tests-map.md:56-130`, владельцы node_rename/symbol_rename | unit/flow/live/repro | сохранённые corpus/replaced/deferred | только идеи иерархий/связей; не переатрибутируем тесты и не копируем код |

Все 168 строк и приложение остаются неизменными. Своей legacy-строки этой новой
карточки нет; новые тесты учитываются в этом листе и PROGRESS.

## Корпус

До кода сняты 25 случаев/23 input файла в `fixtures/corpus/scene_model/connections/`:
нет/одна/несколько связей, root endpoints `.`/пустые, дубли, имя несуществующей
функции (сохраняется), отсутствующий/пустой атрибут method (raw сохраняется,
display пропускает), flags, escaped quotes, BOM/CRLF/loneCR, `.tres`, missing
file, не-сцена/пустой файл. Один общий temporary capture для обоих корпусов
вызывает настоящие old functions; manifest пиннит дату/commit/hashes/bytes и
названную проекцию. Script удаляется до реализации.

## Спецификация

- Только `{path}`, без node-filter: эталон такого фильтра не предлагает.
- `effects=read`, `idempotent=True`, `cost=cheap`, strict schema, errors
  invalid_input/not_found/denied. ToolSpec и `contract/capabilities/connections.json` объявлены.
- RawReader Protocol в собственном `ports.py`; existing fs/read_raw,
  READ_TEXT_MAX_BYTES; runtime/bootstrap не меняется.
- `tscn.fields` и `tscn.rows` — единственные scene views; domain без IO/re.
- Display — проекция строк связей, не вся карточка scene и без truncation.
- Никаких принятых corpus/schema/cards/editor/verbs и чужих domains.

## Решения по ходу

| Дата | Решение | Причина |
|---|---|---|
| 2026-10-29 | Предложено raw `{connections}` + literal display `{text}`, без node argument | сохраняет parse_scene и наблюдаемую M1; не выдаёт новый script validator за паритет |
| 2026-10-29 | Пользователь подтвердил M2 как снятие display gate отсутствующего/пустого атрибута method; raw сохраняется, существование func не проверяем | actual reference вместо нового validator; M1 root display остаётся |
| 2026-10-29 | Пользователь разрешил C.5-only composition: context001 tools count11→13/names/effects/hash и пять inventories (functions/usages/gd_lint/scene/node) | только новые имена+count, обязательный reverse byte/SHA proof; прежнее поведение не менять |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-29 | 1. чтение/лист | обязательное чтение и actual reference выполнены; лист до corpus/tests/code |
| 2026-10-29 | 2. корпус | actual-old25cases/23inputs, parse_scene + traced describe_scene display; manifest pins, script удалён до тестов/кода |
| 2026-10-29 | 3. спецификация + red tests | общий набор459tests:446failed/13passed/0errors,exit1 до production; selfcheck connections79failed/2passed,corpus25fail — native verdictfail |
| 2026-10-29 | 4. код | pure fields+rows, own RawReader, existing fs; initial459/459green, native108unit/25corpus — verdictok |
| 2026-10-29 | 5. двойной прогон/мутации | old25→new25/25; M1 16/25, M2 2/25, P1 1/1+stale card, P2 2/25, P3 1/1+lintfail; все restore byte/SHA/EOL identical |
| 2026-10-29 | 6. живая проверка | native args-file/default fs: many/missing-method/empty-file parity, byte/SHA проекта неизменны; полный1519non-live+3live, exactIDs,0failures/errors/skips |

## Проверки

Baseline независимый:1200files,25prompts,13mechanicsheets,debris0;
448+295+253+60=1056 non-live, exact collected/executed IDs равны (53files),
live3passed21.69с. Formats135 внутри main-a. Contract12, snapshot244/0,
layers/limits460/0, securityok, accepted node selfcheck247/corpus65 — ok.
Frozen tscnF535566EF2FE/9550B/228lines, treeDB7164485858, nodeC974A7BD50A3.
Baseline inventories в approved TEMP `scene-deps-c5-{baseline,old-baseline}.json`;
old working-tree inventory622 tracked+untracked (без .git database), HEAD
ba0535d4; ровно два чужих ??log, diffempty. Первое old path измерение испорчено
PowerShell pipe encoding (пустой inventory), исправлено до edit; попытка hash
включая .git упёрлась в30с и не считается успешной, scope заменён working tree.
Native `python -B tools/selfcheck.py scene_model.connections` → exit2,
`вердикт: blocked`: module not_implemented (нет MODULE), unit not_implemented
(нет тестов), corpus not_implemented (нет корпуса); layers/limits460/0,
contract12 и securityok. Это ожидаемая стадия1, не готовность механики.
Полный stdout/stderr в TEMP `scene-deps-c5-scene_model-connections-stage1.*`;
native report `reports/selfcheck/scene_model.connections.json`.

Final: native selfcheck **108passed,corpus25/0,вердикт ok**; contract14/0,
snapshot309/0=244accepted+25connections+40deps, layers/limits467/0, securityok.
Disjoint598+543+318+60=1519 non-live/62files; live3/24.619с, total1522/64files;
collect/executed uniqueIDs1519=1519, missing/extra0. Formats314/0 (135accepted
+179C.5facts), native CLI proofs8/8 на обеих механиках.
Первый final main-a дал2failures в accepted tests закрытого `tscn.__all__`;
исправлена только собственная extension-line, closed operations сохранены,
старые tests не менялись; повтор main-a543/0. Три сгруппированных selfcheck
превысили30с: не считаются финальным evidence; повтор каждого отдельным
command≤30с дал ok. Evidence `<TEMP>/scene-deps-c5-*-final.*`, test-ids/probes
proof JSON; native report `reports/selfcheck/scene_model.connections.json`.

Final scope:1200→1429files (+229,0deletions),25prompts/15sheets,debris0.
Новых corpusfiles211=49connections+162deps; прочие18 — sheets2/reports2/cards2/
Python12. Семь composition reversals byte/SHA/EOL identical; старые9550B tscn
и707B gdscript API prefixes, accepted tree/node/schema/runtime/editor/bridge,
12 прежних cards, tools/tests-map/parsing corpora unchanged. Old622working-tree
files SHA identical, HEAD ba0535d4, ровно прежние2??log/diffempty.
Original WORKLOG prefix до session53 byte/SHA identical, егоCRLF и PROGRESS LF
сохранены. Native reports четырёх accepted mechanics обновлены только самими
selfcheck. Scope evidence `<TEMP>/scene-deps-c5-final-{inventory,scope-proof}.json`;
7scope+7mutation byte backups вне repo доступны аудитору; disposable scripts удалены.
`docs/porting/README.md`, handoff, acceptance headers аудитора не менялись.

## Следующее действие

Независимый аудит C.5: повторить actual reference25/40, M1–M4/P1–P3 и native gates;
проверить M2 attribute-only и семь composition reversals, затем оформить принятие.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Нет; M2/scope сняты решениями пользователя 2026-10-29 | — |
