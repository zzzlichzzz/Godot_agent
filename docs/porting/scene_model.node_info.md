# scene_model.node_info — карточка узла сцены

**Статус:** этап 7 — ported, **принято аудитом 2026-10-29 (сессия 52)**.
**Обновлено:** 2026-10-29

## Цель

Один read-only инструмент `node` с аргументами `{path, node}`: найти узел по
буквальному алгоритму старого `find_node_in_scene`, вернуть строгую карточку
с типом, путями, скриптом, инстансом, уникальностью, родителем и прямыми детьми.
Без изменения сцены, редактора, других механик или контракта принятого `scene`.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `python/godot_tools/node_refactor.py:185-222` | `find_node_in_scene`: нормализация, `%unique`, корень, exact path, имя, буквальные отказы | чистый resolver в своём `domain/`; диапазон промпта заканчивается на 225, где уже начинается rename |
| `python/godot_tools/node_refactor.py:163-182` | `_rel_path_between`, включая общую часть пути и подъёмы `..` | чистая логика NodePath в своём `domain/` |
| `python/godot_tools/node_refactor.py:73-160` | исходные узлы и `unique_name` | уже принятой `formats/tscn.structure`, не второй парсер |

Эталон заморожен на `ba0535d4dec43c32750e601a6ca86e377abc6af3`.
Карточка — новая проекция, а не старый готовый инструмент; её координаты
зафиксированы пользователем до механического снятия ожиданий. `find_node_in_scene` возвращает
первый `%unique` и принимает пустой spec как корень. Это не исправляется молча.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| строки `docs/tests-map.md:56-130`, владельцы `node_rename`/`symbol_rename` | unit/flow/live/repro | существующее `corpus`, без переатрибуции | только идеи случаев и иерархий, не файлы тестов или старые host-импорты |

Своей старой строки `node_info` нет. Все 168 строк и приложение остаются без
изменений; новые тесты C.4 учитываются здесь и в PROGRESS.

## Корпус

Снято 65 случаев / 24 входа / 14 пар helper в
`fixtures/corpus/scene_model/node_info/`, включая `.`/пустой spec, `%unique`,
exact/короткое/неоднозначное/отсутствующее имя, backslash/trim, три уровня,
инстанс, скрипт, `.tres`, отсутствие корня/узлов, границы IO и кодировки.
Одноразовый `python -B` из старой папки вызывает настоящие `structure`,
`find_node_in_scene`, `_rel_path_between`; ожидания не строятся портом и не
редактируются вручную. Manifest: дата, commit, SHA256 эталона, входов и ответов;
скрипт удалён после успешной съёмки, до permanent tests и реализации.
Эталон node_refactor: 46881 Б, SHA256 `2D708A384177`; дополнительный уже
принятый instance-view scene_deps: 19866 Б, `DBD502AFECA7`.

## Спецификация

- Единственный ToolSpec `node`, effects `read`, идемпотентный, strict schema.
- Карточка: `name,type,parent,path,depth,script,instance,unique_name,parent_path,children`.
- Чтение только потребительским Protocol `RawReader.read_raw`, готовым `fs` и
  общим `READ_TEXT_MAX_BYTES`; никаких новых bootstrap/адаптеров/вербов.
- Разбор только `python.formats.tscn`, domain без `re` и IO. Принятые parser
  corpus и функции не меняются; расширение формата только при доказанной нужде.
- Literal lookup/refusal order сохраняется. Ошибки typed, без host-путей.
- Нельзя импортировать чужой `tree/domain`; при необходимости два простых
  правила depth/path повторяются с объяснением и equality-тестом, как допускает
  промпт. Принятый tree и его две задокументированные границы не исправляются.
- До кода нужны corpus, permanent red tests и подтверждённые координаты карточки.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-29 | Пользователь выбрал «Эталон как есть»: пустой spec/пробелы — root, `%unique` — первый match | буквальный R-08, без исправления эталона |
| 2026-10-29 | Пользователь выбрал относительный `parent_path` от выбранного узла к родителю; `children` — полные пути, через `rel(child, selected) == '..'` | M4 действительно меняет наблюдаемые карточки; отдельный корпус helper проверит подъёмы, siblings и общую часть |
| 2026-10-29 | Пользователь разрешил `179 + N` и только count/names/effects/hash context001 + node в двух contract и gd_lint/scene inventories | все прежние имена и данные сохраняются, обратные byte/SHA проверки обязательны; свой visibility test |
| 2026-10-29 | Существующих `structure` и `fields` достаточно: resolver/unique/script из structure, instance metadata из fields по name/parent и порядку повторов | никаких изменений принятого формата или второго парсера; instance сохраняет quirks уже принятой parse_scene, отсутствующий metadata/path даёт null |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-29 | 1. лист создан | обязательное чтение выполнено, resolver/helper и формат просмотрены до первой правки; исходный inventory 1102 файла, debris 0 |
| 2026-10-29 | 2. корпус | actual-old imports: 65 случаев, 24 файла, 14 `_rel_path_between`; capture exit0, script удалён; все блокеры разрешены пользователем |
| 2026-10-29 | 3. спецификация + тесты | 247 новых тестов на исходных stubs: 245 failures / 0 errors / 2 passed, exit1; XML/stdout/stderr в approved TEMP. 148 module + 99 integration; accepted formats без изменений |
| 2026-10-29 | 4. код | только свой resolver/card/Protocol/app/ToolSpec/MODULE; 148 module + 99 integration зелёные; selfcheck unit247/corpus65/0/contract12/layers-limits460/security ok; snapshot244/0 =179 old+65 own |
| 2026-10-29 | 5. дифференциал и мутации | snapshot244/0, все семь submitted-file мутаций красные и restored identical: True; первые disjoint regression groups448+295+60 зелёные |
| 2026-10-29 | 6. живая проверка | probe node native exit0/full captured answer; live3/0 (23.80с); 1056 nonlive+3live =1059 exact unique collected/executed IDs, 55files; все selfcheck зелёные, scope/byte audit ok |
| 2026-10-29 | 7. записи | своя parity строка — отдельный read `node`; PROGRESS7, WORKLOG51. Следующее — независимый аудит C.4, другие механики не начаты |

## Проверки

`selfcheck scene_model.node_info`: **ok**, финальный unit247 (2.03с), corpus65/0,
layers460/0, limits460/0, contract12/0, security ok. Отдельно integration99/0,
module148/0, snapshot244/0. Исправлена собственная ошибка объявления ToolSpec
(`input` вместо фактического `args`): native discovery не включал модуль, поэтому
селективная генерация отказала KeyError до записи. После исправления создан
только отсутствовавший node.json через native `rendered()`; прочие 11 не писались.
Авторизованный context case hash `5239A9E5571F`, только count/names/effects;
manifest только соответствующий hash. Для context и двух CRLF contract-файлов
исходные EOL восстановлены; обратные byte/SHA проверки четырёх inventories,
контекстного case/manifest воспроизводят baseline.
Baseline: module300, main295+154, guards60, live3 (22.71с). Первый параллельный
monolithic main-run упёрся в 30с и **не считается успешным**; повторные две
непересекающиеся группы295+154 прошли, лимит команды не увеличивался.
Сохранён pre-edit SHA256 inventory в approved TEMP `node-info-c4-baseline.json`.
Frozen anchors совпадают с последним аудитом; `tscn.py F535566EF2FE`,
`tree/domain/core.py DB7164485858`.
Финальная регрессия без failures/errors/skips: module448 (2.39с),
code_intel/contract/formats/kernel295 (15.09с), integration253 (10.04с),
security/tools60 (5.70с), отдельно live3 (23.80с). Сумма1059 точно равна
полным collected IDs (55 файлов: 53 nonlive+2 live). Formats135 сохранены.
Native tree128/40cases, gd_lint126/37cases, scene_ops25/corpuslive — ok;
contract12, snapshot244/0, layers/limits460/0, security ok.
Native probe node через dispatcher/default_ports/read_raw: exit0 и полная
карточка Main/Arm/End равна снятому эталону. PowerShell/recovery stderr хранится
отдельно; status взят из native subprocess, не из наличия stderr.
Scope audit: 1102→1199 файлов,97additions (91 corpus+6 инфраструктура/тесты/лист),
0deletions/debris. Frozen/tscn/tree core, прежние corpora и все 168 tests-map
строк неизменны; reverse-byte proof допускает только согласованные registry
изменения. Старый Git: только два чужих ??log, diff пустой; оба parser-reference
и оба log SHA256 совпали. JSON/XML/collect IDs — approved TEMP.

## Следующее действие

Независимая пересъёмка/мутации C.4 по `docs/porting/_start-prompt.node_info.md`;
после принятия — следующие scene_model.* только отдельным поставленным промптом.

## Доказательства мутаций сдаваемой версии

Каждая применялась отдельно к сдаваемому файлу; backup и restore через
`shutil.copyfile` в approved TEMP, SHA256/bytes/lines/LF/CRLF до и после совпали,
`restored identical: True`. Не было совместных мутаций или engine-run в их ходе.

| Mode | Подмена | Реальный красный результат, exit1 |
|---|---|---|
| M1 | убрать backslash-normalization | 6/144: card + resolver для 010/011-hierarchy и 058-crlf |
| M2 | отключить `%unique` | 22/144: 11 card + те же resolver; unique/nonunique/missing, duplicate-first, sections, Unicode |
| M3 | вернуть первый неоднозначный match | 4/144: card+resolver 020-ambiguous, 027-duplicate_unique |
| M4 | убрать `ups = ['..'] * up_count` | 57/144: 47 карточек (родитель/прямые дети) и 10 helper-пар; настоящий подъём, не искусственная assertion |
| P1 | optional result-field в tools без card regeneration | native gen_contract: stale node.json; отдельно 1/1 discovery-card equality |
| P2 | изменить только result.name одного 001-hierarchy expectation | ровно 2/64: только этот card-parity и manifest SHA pin |
| P3 | import pathlib в domain | AST guard 1/1 и отдельно native lint_arch exit1 |

Full failed-node lists/XML/stdout/stderr: `node-info-c4-{M1,M2,M3,M4,P1,P2,P3}.*`
в approved TEMP, JSON содержит commands/exit/failed и before/mutated/after stats.
Сдаваемые/восстановленные hashes: core
`c974a7bd50a3c4ad7e74bc66f92a6a362536a3de3ae81197c8d3b8f66d1f0155`
(3455B,81 lines/LF81/CRLF0); tools
`80e9ee1af6b21c72851c0143293ca1c065037d6b821473a0eac342ce3842bd90`
(1411B,19 lines/LF19/CRLF0); 001 case
`00e426d3742c68c03b9138413b95c24a185d6151f8c267336dbd03248edb252d`
(785B,44 lines/LF44/CRLF0). После финального аудита byte-backups и собственные
capture/mutation/audit TEMP scripts удалены; диагностические JSON/XML/collect/
stdout/stderr сохранены в approved TEMP. Original WORKLOG prefix SHA/EOL сохранён.

## Границы результата

Это port resolver/helper и новая явно согласованная карточка, не новый вариант
старого rename-сценария. Строки `%unique`, ambiguity и root failures сохранены;
empty/whitespace spec разрешён, duplicate unique выбирает первый. `parent_path`
от выбранного узла к raw parent (null у root), children — full paths, file order.
Instance metadata берётся из отдельного принятого fields-view по name/parent и
duplicate order; его quirks не унифицированы со structure. BOM/CRLF/loneCR и
invalid-UTF8 fallback именно как old `_read_file_text`, без global EOL cleanup.
Два простых правила depth/path повторены с объяснением и шестью equality-тестами
через публичный scene, не private import. Отказы IO/расширения — read-policy нового
инструмента, не перенос старой write-policy `_normalize_scene_path`.
Нет binary Godot loader, editor state, записи/планов/ResourceSaver/новых verbs.
Не изменены accepted tree extension/loneCR границы, tscn patch-overlap, старый
wiring109 и будущие rename/reparent/delete/connections/deps/lint механики.
Generator проверяет ToolSpec/card, не динамические domain-returns; отдельный
strict-result тест проверяет все десять fields и запрет uncontracted property.
Auditor-owned README/prompt/header/handoff остаются неизменными.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| противоречие empty-root / первый unique | разрешено пользователем: буквальный эталон |
| координаты parent_path / M4 | разрешено пользователем: относительный parent, children через rel(child, selected) |
| registry/snapshot scope | разрешено пользователем: только перечисленные composition-изменения, 179 + N |
