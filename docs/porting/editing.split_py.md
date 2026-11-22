# editing.split_py — C.17, read-only `split_scan`

**Статус:** этап 7 — **C.17 половина 1 (`split_scan`) принята аудитом 2026-11-01 (сессия 73), C.18 половина 2 (`split_plan`) принята аудитом 2026-11-01 (сессия 75)**; F4 — отдельный срез C.19, запись (create/delete в воронке) — C.20.
**Обновлено:** 2026-11-01.

## Цель

Карта ссылок на `.py` внутри ближайшего аддона с `plugin.cfg`: импорты,
патчи, чтение исходника, упоминания, доки; только чтение, идемпотентно.
C.18 — план/AST/фасад; C.19 — только F4; C.20 — запись с отдельным ADR. Принятый split_gd,
другие модули, shared, editor и гейты заморожены. Приёмку делает аудитор.
Основание: `_start-prompt.split_py_scan.md`, 51571 B / 513 CRLF / без BOM,
SHA256 `39bd4d66fe69206fc445a380d479c037ab51b48feea4baf8178e413721c7714a`.

## Старый код

Эталон: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/python/`.
`godot_tools/split_refactor.py`: 44114 B / 872 CRLF, SHA256
`87cb4d5209c070f2f65ad45c16086e7c99b561ce677c6f8b1d1fd57b545526e7`.

| Файл / строки | Что делает | Граница |
|---|---|---|
| split_refactor.py:38–62,66–73,91–124 | константы, нормализация, декодирование, обход, импорты | read-only примитивы, _CODING_RE не используется |
| split_refactor.py:127–199 | scan_refs | пять категорий, native приоритет, counts полные, occurrences1000/text200 |
| split_refactor.py:270–656,718 | inventory/plan/render/apply | вне C.17: C.18/C.19 |
| tools/agent_bridge.py:914–954 | _split_target и scan cmd_split | права/расширение; transport не переносится |
| tools/godot_agent_mcp.py:440–458 | split_scan/split_plan | реальные якоря444/451, не устаревшие464/471 промпта |

Прочитаны AGENTS/RULES/architecture/PORTING/parity/tests-map/PROGRESS/NOTES,
template, весь лист split_gd (включая приёмки), оба scan-промпта,
ADR-0004/0006/0009/0010/0011/0012, security invariants, WORKLOG69–71.
DiskFileSystem.is_file/read_raw/list_files достаточны; существующий sorted walk
после фильтра совпадает с native. Новые методы/порты/импортные швы не нужны.

## Старые тесты

| Файл | Семейство / судьба | Что берём |
|---|---|---|
| test_split_refactor.py:105–167 | unit / corpus, tests-map126 | import/aliases/false positives/source_read/doc/mention/patch/skip; пересъёмка native |
| test_split_refactor.py:209–482 | unit / corpus | inventory/plan/apply отложены C.18/C.19 |
| test_agent_bridge.py:1939–2041 | host-bridge / replaced, tests-map136 | scan read-only, agent-dev/non-py/foreign; новый policy-контракт вместо CLI |

Старые тесты только прочитаны; не скопированы и не запущены. Историческая
coarse-строка split_gd в tests-map126 уточняется добавлением C.17, не удалением.

## Корпус

Внешний `capture_scan.py`: 47кейсов001–047, 163inputs; 34native success,
5native boundary observations (missing — SplitError; non_py/no_addon/донор>4MiB/
addons — native success, port refusal), 8schema/path boundaries без native аналога.
Raw без schema; missing message получен живьём, не сокращён. Два вызова равны,
SHA/tree неизменны. Manifest: bytes/SHA cases/inputs/native/script, отказы.
Case.fixture относительно fixtures/projects. Новых `.gd` нет. Windows
provisional reserved `nul` и collision ref.py/ref.PY исправлены в собственных
inputs до финализации: upper.PY/nul_path вместо них.

## Спецификация и инварианты

ToolSpec записан: split_scan/read/idempotent, fs-only; §2.1 дословно.
Проекция rel→donor, occurrence.rel→file; остальные поля сохраняются.
Policy до чтения; ближайший plugin.cfg; донор исключён; сосед1MiB/донор4MiB;
приоритет import→patch→source_read/doc/mention; text.strip()[:200]; counts всех
попаданий, hard/soft sorted из retained1000, допускается пересечение списков.
Свой инкрементальный utf-8-sig decoder(final=True), без чужого shared/IO в domain.

## Решения по ходу

| Дата | Решение / факт | Основание |
|---|---|---|
| 2026-11-01 | raw scan_refs НЕ содержит schema; ничего не добавлять | живой probe + явное подтверждение пользователя; неточность §2/§3 |
| 2026-11-01 | заморожены все23 прежние карточки, финал24 | пользователь подтвердил исправление старого числа22 |
| 2026-11-01 | процедурные этапы1–6 разрешены; этап7 только аудитор | пользователь снял конфликт шапки/§3 |
| 2026-11-01 | _CODING_RE не подключать, aliases не используются | фактическая native логика |
| 2026-11-01 | предсуществующий skip_dirs/__pycache__/ref.gd.uid разрешён к точечному удалению | отдельное подтверждение пользователя; ref.gd/каталог сохранить |

## База и сохранность

Свежий внешний dossier:
`C:/Users/Lich/AppData/Local/Temp/opencode/c17-split-py-scan-20261101-preflight/`.
`before.json`/`before-bytes/`: все2782 файла, каждый byte/SHA проверен;
audit-filtered2777, UID84. Это собственный полный census, не пересчёт базы §0.
До первой правки repository_unchanged=true; этот лист — первая правка.
WORKLOG527151 B/SHA `362337ed2be0c221805b029e035bc81e92ffd1144a19dbd8f64f37366fd8305f`,
исторические4479CRLF сохраняются, запись только ab. External project335B/SHA
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29` backed up.
ExtraUID20B/SHA `1191b3d4b735fc86fff0366fc9fffb4a352afd44d318e436b4d81deeaa578e49`
уже в byte backup; отдельная разрешённая уборка, не generated UID C.17.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-01 | 1. чтение, fresh backup, лист первым | shape probe дважды/5категорий/overlap/read-only; три уточнения подтверждены |
| 2026-11-01 | 2. native corpus | 47case/163inputs/39native observations; два вызова/tree/oracle unchanged; extraUID точечно удалён после разрешения |
| 2026-11-01 | 3. новые тесты | red-before-code: JUnit263/262fail/1pass/0errors/0skip, wall4.584s; production TODO ещё не заполнены |
| 2026-11-01 | 4. domain→app→ToolSpec/ModuleSpec | семь TODO заполнены in-place, own ports/text/walk/refs; sole split_scan; selfcheck ok263unit/47corpus/layers529/limits529/contract24/security ok |
| 2026-11-01 | первое выполнение | одна ошибочная unit-ожидалка import-tab: native возвращает donor; исправлен только тест после живого lexical proof; JUnit263/0/0/0, wall3.670s |
| 2026-11-01 | контракт/companions | создана только split_scan.json2823B; все23 прежние byte-identical; context count22→23/name/effects+SHA и только inventory pins семи тестов; scene_deps без правок — новых .gd нет |
| 2026-11-01 | 5. независимая пересъёмка | 39observations/78native/78port; raw и projection равны, идемпотентны; oracle/fixtures/repo unchanged |
| 2026-11-01 | широкий differential | 120fresh donors/240native/240port, seed171101; 0diff, root+tail+dot/hyphen stems/BOM/CR/LF/limits/skip, деревья неизменны |
| 2026-11-01 | мутации M1–M8 | отдельно/sequential: 31/20/4/64/28/17/2/4fail из263; errors/skips0; после каждой exact bytes/SHA и всё дерево восстановлены |
| 2026-11-01 | подложки P1–P3 | P1:263green и только gen_contract stale split_scan.json; P2/P3: lint_arch ловит os-domain/foreign-app; exact restore каждой |
| 2026-11-01 | полный non-live | JUnit3880/0fail/0errors/0skip, wall65.244s; collect3880/122distinct file paths, wall5.201s; node IDs равны, каждый выполнен один раз |
| 2026-11-01 | все snapshots | 771/0 (724+47), split_py47/47; все прежние соседние количества сохранены |
| 2026-11-01 | 6. живой прогон | три существующих live-теста, JUnit3/0/0/0, wall21.403s, без skip; project точными335B восстановлен, final83.gd.uid |
| 2026-11-01 | финальный selfcheck/probe | ok263/47, wall17.788s; все отдельные статические гейты ok; probe показывает import/doc/mention и hard/soft overlap |
| 2026-11-01 | обратная проекция | собственное дерево3004/audit-filtered2998, UID83/debris0; все23 прежние cards+template и frozen implementation byte-identical |

## Финальная проверка

Вывод `python tools/selfcheck.py editing.split_py` (stderr0):

```text
selfcheck editing.split_py
  module         ok              editing.split_py (split_scan)
  layers         ok              файлов 529, нарушений нет
  limits         ok              файлов 529, предупреждений 0
  contract       ok              артефактов 24, расхождений нет
  security       ok              нарушений нет
  unit           ok              263 passed in 2.02s
  corpus         ok              кейсов 47, расхождений нет
вердикт: ok
```

Отчёт: `reports/selfcheck/editing.split_py.json`.
Отдельно `gen_contract --check`24/0, `lint_arch`529/0,
`check_limits`529/0, `security_audit`ok; kernel/schema и сами гейты не менялись.
24артефакта/25файлов capabilities с template; context23names;
editor_verbs6/version3 и старые карточки byte-identical.

| Соседний selfcheck | unit | corpus | Вердикт |
|---|---:|---:|---|
| editing.split_gd | 625 | 102 | ok |
| verification.check | 188 | 75 | ok |
| verification.api_check | 206 | 52 | ok |
| verification.gd_lint | 126 | 37 | ok |
| verification.tscn_lint | 315 | 65 | ok |
| engine_kb.class_api | 186 | 26 | ok; исторический F4 selector overlap сохранён |

Full non-live: **3880/0fail/0errors/0skip**, wall65.244s/stderr0;
3617 принятых +263 новых. Collection3880, wall5.201s/stderr0,
122 distinct node-ID file paths; exact same node IDs и every test executed once.
Это собственная метрика путей из pytest hook; историческая аудиторская база
3617/102files/89.4s, tree2776/snapshots724 не переписывается.
Snapshot-all771/0, wall62.846s/stderr0 (724+47); сырые JUnit/logs/IDs в досье.

Probe: `python tools/probe.py split_scan --args-file <dossier>/probe-args.json
--project fixtures/projects/corpus/editing/split_py/hard_soft_overlap`:
`ok:true`, donor=donor.py, counts(import1,source_read0,patch0,mention1,doc1),
hard_files=[both.py], soft_files=[both.py,note.md], truncated=false;
полный JSON равен корпусу014, stderr0.

## Последовательные мутации и точное восстановление

Каждая строка — отдельный before.bytes/tree-before.json, мутант, тест/гейт,
finally exact restore и full-tree equality до следующей строки. Старые тесты
не запускались. M1 import удалён; M2 patch→source_read; M3 cap снят;
M4 донор включён; M5 все retained files hard; M6 skip-filter выключен;
M7 text160; M8 exact-only module; P1 required.truncated удалён;
P2 import os в domain; P3 foreign verification.shared.source_text в app.

| Проверка | Файл | До: B / SHA256 | Мутант: B / SHA256 | После: B / SHA256 | Результат |
|---|---|---|---|---|---|
| M1 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1762 / `6e87735733b54a2eba0e0319a5e5042ed1475334d4c6abd41c90fa43d5eaa7ab` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 31fail/263; errors/skips0 |
| M2 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1807 / `8ce7865e0fe2b3b6c00ba0a3cfeaff45f5ffee6cb02dc4c8c1cbb8cfd0f47520` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 20fail/263; errors/skips0 |
| M3 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1771 / `f0030c85fa8bd23550b7cbe321ae554c837e64ead9f880c60a5ed8d5d7be62f0` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 4fail/263; errors/skips0 |
| M4 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1785 / `139074073beab6daf0a9e1dd2a20db32281d909a398b6fa5fb911cd15375782a` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 64fail/263; errors/skips0 |
| M5 | `domain/core.py` | 671 / `e0dc77efe26c2fb2319b0ca3c6dff9e9277fdb49f19286949e828b476a2a2284` | 620 / `0946db58815a69489ef17e93fbcdcfa024226bda912aba831a6c4c185cdc13cb` | 671 / `e0dc77efe26c2fb2319b0ca3c6dff9e9277fdb49f19286949e828b476a2a2284` | 28fail/263; errors/skips0 |
| M6 | `domain/walk.py` | 1534 / `0490a3ed648098191549b75ca42618d374b6c0f06d14925558fc52daf789ac73` | 1474 / `5169add0f9528ba67a872776adc4b4382796d68d5c176303b135ea231cd9214b` | 1534 / `0490a3ed648098191549b75ca42618d374b6c0f06d14925558fc52daf789ac73` | 17fail/263; errors/skips0 |
| M7 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1801 / `5aa9c4662f9c232c65f4242051a3f2b6a3bd082c789e013def1fe0cc99172fc8` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 2fail/263; errors/skips0 |
| M8 | `domain/walk.py` | 1534 / `0490a3ed648098191549b75ca42618d374b6c0f06d14925558fc52daf789ac73` | 1502 / `e272ac9f6488aeac7a5df7d620597653d210ce579c1ac3cc711f52eb19082882` | 1534 / `0490a3ed648098191549b75ca42618d374b6c0f06d14925558fc52daf789ac73` | 4fail/263; errors/skips0 |
| P1 | `tools.py` | 1812 / `ed392103a9bb58adcf3b2dfcd889c9adc1f56dce81eb64079f1444448f0ea428` | 1800 / `f712ae8e9dc9d2640eff942829cb380e366b9220a938b4c1bcb2beee518b93d5` | 1812 / `ed392103a9bb58adcf3b2dfcd889c9adc1f56dce81eb64079f1444448f0ea428` | 263green; gen_contract stale split_scan.json |
| P2 | `domain/refs.py` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | 1811 / `40a806630ad092192e5c9d441e24447f7a81f24b1b4a40092274b62c5a268e49` | 1801 / `4998c8a1deb08900c865a7bc9bc5d9cc21b616ee15d2b4d70eae093465fd5e9f` | lint_arch red |
| P3 | `app.py` | 3149 / `4800c2091d4b70745be0ce5fd96f0f2b83b3bdd882016b59a70a9c7d3ac99212` | 3208 / `23afec51c052218c461275fd1ed158ad6ded14917d574be5bfa9a65943560cc1` | 3149 / `4800c2091d4b70745be0ce5fd96f0f2b83b3bdd882016b59a70a9c7d3ac99212` | lint_arch red |

`mutations-summary.json`, `mutation-table.md`, mutations/<id>/proof.json,
before.bytes/mutated.bytes/tree-before.json/tests.xml/logs — во внешнем досье.

## Live и гигиена: без скрытой уборки

Ровно три существующих теста `tests/py/live/`, без изменения файлов/skip.
Внешний project.godot временно получил editor_plugins, затем восстановлен
побайтово:335B/SHA `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
Godot создал163.gd.uid и1.gdshader.uid; каждый отсутствовал в start-tree,
каждый архивирован в live/generated-uids/ и удалён ровно по его пути.
Root plugin.gd.uid восстановлен из byte backup; итог83 старых.gd.uid,
все их SHA равны pre-live. Временная probe-scene отсутствует, исходники/дерево
после уборки равны start-tree (кроме регенерируемых selfcheck reports).

Первый внешний cleanup-driver завершился assertion: фильтр .gd.uid не учёл
новый ref.gdshader.uid. Все3 live-теста уже были green; project и gdUID были
восстановлены. Единственный оставшийся shaderUID отдельно доказан как новый,
архивирован/точечно удалён; исправлен только внешний отчёт, live не повторялся.
Сырой JUnit, after-engine/source-tree-difference и восстановленная proof.json
с `initial_driver_hygiene_assertion_failed:true` сохранены. Это не скрытый PASS
первого cleanup-driver. Законные source/cache-fixture каталоги не удалялись.

## Список правок и полная обратная проекция

Ниже тот же scope, что в append-записи WORKLOG; **каждый конкретный путь**,
до/после bytes/SHA256/CRLF/LF — в `final-reverse.json` и `changed-files-sha256.md`
досье. Для новых before=null, для отдельно разрешённого удаления after=null.
Собственные SHA листа/WORKLOG измеряются снаружи после записи, без самохэша.

- Семь TODO in-place в `python/modules/editing/split_py/`: app.py,module.py,
  tools.py,__init__.py,domain/core.py,domain/__init__.py,tests/test_core.py.
- Семь новых локальных файлов там же: ports.py,domain/text.py,domain/walk.py,
  domain/refs.py,tests/test_app.py,tests/test_refs.py,tests/test_walk.py.
- Новые `tests/py/contract/test_split_scan_contract.py`,
  `tests/py/integration/test_split_scan.py` и только новая
  `contract/capabilities/split_scan.json`2823B/SHA
  `32349d44d2c546f1011f8951cd8a5bf5cbb0b5295b9f5927e377a87d79ab27bf`.
- `fixtures/corpus/editing/split_py/`:47cases+manifest; полный список и каждый
  bytes/SHA в manifest.cases. `fixtures/projects/corpus/editing/split_py/`:
 163inputs, каждый bytes/SHA в manifest.inputs. Других файлов в этих деревьях нет.
- Companion только context/gather/001-all-sections.json count22→23/name/effects
  и его SHA в manifest.json; семь inventory-only тестов:
  tests/py/contract/test_functions_contract.py,test_usages_contract.py;
  tests/py/integration/test_node.py,test_scene.py,test_verify.py,test_gd_lint.py,
  test_tscn_lint.py. Полный diff проверен; другая логика/поля не менялись.
- docs/porting/editing.split_py.md новый; только split_py строка PROGRESS/parity,
  tests-map126 append-уточнение и6новых строк; WORKLOG только ab-append.
- Автоматически регенерированные отчёты reports/selfcheck/{editing.split_py,
  editing.split_gd,verification.check,verification.api_check,
  verification.gd_lint,verification.tscn_lint,engine_kb.class_api}.json:
  обязательные selfcheck, не правка принятых реализаций.
- Единственное удаление относительно fresh-before: отдельно разрешённый
  `fixtures/projects/corpus/editing/split_gd/skip_dirs/__pycache__/ref.gd.uid`
  20B/SHA `1191b3d4b735fc86fff0366fc9fffb4a352afd44d318e436b4d81deeaa578e49`;
  источник ref.gd/каталог сохранены. Generated live UIDs отсутствовали в live
  start-tree после этой отдельно разрешённой уборки (не в fresh-before).

Собственный census: all2782→3004, audit-filtered2777→2998; итог223added,
26changed (включая append-WORKLOG),1отдельно разрешённый deleted. UID83/debris0.
Это не замена независимой принятой базы §0. Полный before/after byte backup,
final-tree/final-unchanged/final-frozen и reverse allow-list доказывают:
accepted split_gd code/cards/102cases/input-source, все23 старые cards+template,
editor_verbs/editor/kernel/substrate/runtime/protocol/channels/accepted areas,
13gates и auditor-only handoff не изменены. WORKLOG весь старый527151B-prefix
и исторические4479CRLF сохранены; ADR/RULES без правок, F4/F10 не исправлялись.

Первые запуски внешнего reverse.py поймали ошибки самого сборщика отчёта:
template ошибочно посчитан картой, cases/inputs ошибочно прочитаны как list.
Исправлен только внешний скрипт; успешная allow-list/byte-проверка выполнена
заново. Это не изменение корпуса/гейтов и не новая «база».

## Досье и воспроизведение

Все одноразовые scripts/logs/raw/JUnit/byte backups находятся вне аддона,
в указанном выше dossier. Основные файлы: capture-summary/observations,
independent-recapture/summary, wide-differential/summary, red-before-code.xml,
scan-green.xml, full-regression-summary/full-non-live.xml/full-collection.ids,
snapshot-all.stdout.txt, neighbors-summary, final-gates-summary,
live/proof.json, mutations-summary/mutation-table, final-reverse/final-tree/
final-unchanged/final-summary, changed-files-sha256.md, evidence-index.json.
Отказы на границах schema/path/policy/limits отмечены contract_refusals;
никаких новых полей raw/native, никакой C.18/C.19 логики/записи/AST.

## Блокеры

Блокеров C.17 нет. Приёмка не выполнялась; статус skeleton/этап6, не ported.

## Следующее действие

Независимый аудитор воспроизводит native corpus/differential/M1–M8/P1–P3,
полную регрессию/live/замороженные SHA по досье; только он решает приёмку C.17.
C.18/C.19 не начинать в этой задаче.

## Приёмка аудитом (сессия 73, 2026-11-01)

| Что | Результат |
| --- | --- |
| Пересъёмка корпуса живым эталоном | `reference_result` 34/34, своя проекция 34/34, порт 47/47 (13 отказов по `kind`/`expected_message`, идемпотентность, sha дерева) |
| Инварианты payload | 34/34: счётчики = гистограмма оставленных вхождений, донор вне `occurrences`, `text ≤ 200`, `hard_files`/`soft_files` = множества по видам |
| Дифференциал шире корпуса | 101 вызов (45 вариантов + 6 реальных `.py` порта): 95 побайтово, 6 границ контракта (`addons`, `.agent_history`, 4 MiB, `plugin.cfg`, 2 — база сравнения nested-аддона) |
| Свои мутации | M1 11, M2 4, M3 4, M4 64, M5 31, M6 3, M7 61, M8 2 — красные, восстановление `identical=True` |
| Подложки | P1 unit-зелёная → только `gen_contract --check` `fail: split_scan.json`; P2/P3 → `lint_arch` |
| Гейты | non-live 3880/0/0/0 (55.0 с), live 3/0skip (17.954 с), snapshot 771/0, contract 24, selfcheck 263/47, layers 529, limits 529/0, security ok |
| Сохранность | +222 / 26 изменено / 0 удалено; замороженные 13/13, карточка добавлена одна, принятые области и `editor/` без изменений |
| Гигиена | `.gd.uid` 83 → 245 → 83 (удалены ровно 162), `project.godot` восстановлен байт-в-байт, дерево 2999, debris 0 |

Границы и находки: **F11** — для отсутствующего файла вне аддона порт отвечает `invalid_input` (`plugin.cfg`), эталон — `not_found`;
порядок проверок записан как находка и кандидат микро-среза. `22-я находка F4` (селектор `selfcheck.py`) остаётся долгом.

## C.18 — вторая половина (`split_plan`), preflight 2026-11-01

Половина 1 остаётся на этапе 7 по независимой приёмке сессии 73.
C.18 выбран новым handoff сессии 74, но **остановлен до корпуса/тестов/кода
плана** по §6 его промпта: дословный контракт противоречит actual-old.
Приёмки C.18 нет; запись C.19 не начиналась. Аудиторский handoff не меняется.

| Старый код | Прочитано / назначение |
| --- | --- |
| `split_refactor.py:38–62,66–91` | константы, ошибки, нормализация, декодирование, SHA |
| `split_refactor.py:202,231–259,270–340` | patch-warning, сегменты, инвентарь, used_names |
| `split_refactor.py:349–401` | авто-группы, import, цикл, join_blocks |
| `split_refactor.py:407–655,656–716` | read-only plan и фасад |
| `arch_map.py:49–258` | карта, сегментные маски, лимиты, зоны, индекс имён |
| `tests/test_split_refactor.py:169–416` | кейсы inventory/plan; старые тесты не запускались |
| `agent_bridge.py:914–1020` | вход/отказы CLI; CLI не переносится |

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c18-split-py-plan-20261101/`.
Промпт: 42327 B / 478 CRLF, SHA256
`b3fb5b18cc4b1ef0101bb792d7036a954e70928c887c01cf41cb76f8209d7bbe`.
Перед первой правкой сделан полный свежий byte-backup (`before-bytes/`,
`before.json`), включая весь WORKLOG и внешний `project.godot`.

### Блокеры и рекомендуемые уточнения (не решения портера)

| # | Доказанный конфликт | Рекомендуемое уточнение аудитору |
| --- | --- | --- |
| B1 | §2.1 требует `inventory.symbols[].state: string`; native:633–636 возвращает `bool` | Публиковать native boolean, без выдуманного строкового кодирования |
| B2 | §2.1 требует `facade.reexports: string[]`; native:685 возвращает `{module, names}[]` | Сохранить объекты с module/string и names/string[] |
| B3 | M3 объявляет normalized SHA мутацией; native:621 хэширует текст после utf-8-sig и universal-newlines | Сохранить native normalized donor_sha256; инвертировать M3 на raw-byte SHA |
| B4 | Native:573 считает занятым целевой файл **и каталог**; ADR-0011 разрешает единственный production-вызов fs.exists только split_gd | Отдельно разрешить consumer-owned exists для split_py без правки substrate/старого вызова |
| B5 | Принятые scan-тесты читают все numbered JSON как scan и пиннят 47/один инструмент | Разрешить узкие фильтры по tool и multi-tool pins в существующих scan-тестах; 47 старых кейсов и SCAN не менять |

`native-shape-proof.json`: два actual-old вызова на BOM+CRLF доноре,
ответы идентичны; дерево и эталон неизменны; apply/write helpers заблокированы.
Raw donor SHA `b452df421a00c9d25043d9a7f6feacbbc8d8ef7d057946f22bae093a34c02352`,
native normalized SHA `51fb307f74da24ce2c39d6328969bd4bacaf6b1b2c1c2ad2674c9d8ed222a343`.
Это preflight evidence, **не** снятый корпус C.18 и не доказательство паритета плана.
Архитектурная карта/зоны/индекс имён не будут молча заменены пустой картой;
их потребительская read-only оркестрация тоже должна войти в уточнённый C.18.

### F11 и F4 — отдельные разрешённые исправления

**F11** найден аудитором сессии 73. fs.is_file уже вызывается первым,
но not_found-ветка стоит после `_addon_root`; отсутствующий донор без plugin.cfg
даёт invalid_input. Требуется перенос ветки до поиска корня, native отказ,
корпус и красный пин. Пока не правится: новый numbered case нарушит frozen
scan-loader/provenance-47 (B5); обходную «невидимую» для гейта папку не создаём.

**F4** найден ранее как долг гейта. Независим от B1–B5: разрешён только селектор
интеграционных unit-targets, longest known tool prefix wins. План: ADR-0013,
красные поведенческие/count пины, все 44 selfcheck до/после, P5 с byte-restore,
полная регрессия/statics/live. Corpus/contract/order checks остаются без изменений.

**Следующее действие:** выполнить отдельно разрешённый F4; C.18/F11 продолжать
только после явного уточнения B1–B5, без самовольной правки промпта/контракта/ADR-0011.

### F4 — ADR и красные пины (2026-11-01)

- Добавлен ADR-0013, только unit-selector; snapshot остаётся у api,
  поскольку api_snapshot не является известным инструментом.
- Новые 13 пинов: фактический pytest/JUnit **13 tests,4fail,0errors,0skip**
  на старом селекторе; настоящий collect_count **186 != 128**. Остальные
  9 пинов зелёные; corpus/contract/production-модули не изменены.
- Доказательства: `f4-red.stdout.txt`, `f4-red.xml`, `f4-red.summary.json`
  во внешнем досье. Все 44 baseline selfcheck запущены последовательно,
  с точным восстановлением каждого исходного report; селектор пока заморожен.
- `native-extra-proof.json`: F11 native scan/plan одинаково возвращают
  «файл не найден: missing.py», текущий scan даёт invalid_input/plugin.cfg.
  Native существующий target-каталог дважды даёт ошибку «целевой файл уже
  существует: part.py», fs.is_file false/fs.exists true. Живой map-case
  подтвердил generated-only, line-limit и core-duplicate errors; никакие
  эти ветки нельзя заменять пустыми defaults. Все fixture/oracle неизменны.

**Следующее действие F4:** дождаться baseline всех 44, изменить только селектор,
получить 13green и сравнить все 44 после; затем P5/полный регресс/статики/live.

### B6 — общий F4 конфликтует с замороженными соседними счётчиками

После завершения всех 44 baseline selfcheck диагностический селектор на
публичных именах всех загруженных ModuleSpec был проверен **без изменения
tools/selfcheck.py**: перехвачены реальные старые target-списки, построены
списки по longest-prefix и каждый изменившийся список реально собран pytest.
`selector-prediction.json` сохраняет все списки/имена и collect_count:

| Механика | Старый фактический collect | Collect предложенного target-списка | Исключаемые integration |
|---|---:|---:|---|
| engine_kb.class_api | 186 | 128 | test_api_check.py |
| scene_model.node_info | 352 | 247 | test_node_delete_preview.py, test_node_rename_preview.py, test_node_reparent_preview.py |
| scene_model.tree | 168 | 116 | test_scene_deps.py, test_scene_ops_bridge.py |

Это не таблица after selfcheck: production-селектор не изменён, after/P5
не выполнялись. Для остальных загруженных модулей списки байтово по именам
и порядку те же. Две дополнительные дельты запрещены C.18 §3.7/§6.
**F4 остановлен**; hardcoded исключение только api_check не вводилось.
Рекомендация: отдельно разрешить именно две дополнительные дельты, если
нужен общий longest-prefix. Это рекомендация, не расширение scope портером.

Красные пины сохранены внешним архивом `test_selfcheck_unit_selector.py.red`
(4301 B, SHA256 d0e12aa9b3e12bfad7784e83d7c13c500b787e2f85dfe6418da7d4cf2460d9d5,
`f4-red-pins-archive.json`). Собственный незавершённый файл удалён из active
testpaths, чтобы не оставить исходный проект красным; старые тесты неизменны,
строка tests-map сохранена с судьбой deferred. ADR-0013 явно **proposed**.

### Все 44 — фактический baseline selfcheck, до любого изменения селектора

`counts-before.json` и `counts-before/<module_id>.stdout.txt/.report.json` — реальные
последовательные `python -B -X utf8 tools/selfcheck.py <id> --json`. Для каждого
прогона исходный report восстановлен побайтово, селектор неизменен. «—» значит
unit not_implemented, а не ноль и не успешная проверка заготовки.

| Механика | unit до | Механика | unit до |
|---|---:|---|---:|
| project_text.search | 29 | editing.rollback | 24 |
| code_intel.functions | 33 | editing.paths_preview | — |
| code_intel.usages | 66 | editing.file_refactor | — |
| scene_model.node_rename | 162 | editing.symbol_rename | 15 |
| project_text.read | — | editing.scene_ops | 25 |
| project_text.tree | — | editing.resource_ops | — |
| code_intel.function_card | — | editing.split_gd | 625 |
| scene_model.tree | 168 | editing.split_py | 263 |
| scene_model.node_info | 352 | verification.check | 188 |
| scene_model.connections | 108 | verification.gd_lint | 126 |
| scene_model.scene_deps | 176 | verification.tscn_lint | 315 |
| scene_model.node_reparent | 155 | verification.api_check | 206 |
| scene_model.node_delete | 131 | verification.headless | — |
| engine_kb.engine_info | — | verification.action_judge | — |
| engine_kb.class_api | 186 | verification.runtime_checks | — |
| engine_kb.api_cache_refresh | — | context.ask | — |
| editing.write_preview | 45 | context.gather | 33 |
| editing.write_apply | 44 | context.editor_context | 28 |
| context.runtime_snapshot | — | assistant.chat | — |
| assistant.history | — | assistant.model_choice | — |
| assistant.routing | — | project_ops.settings_get | — |
| project_ops.settings_set | — | project_ops.architecture | — |

**Следующее действие:** завершить проверку сохранности (3880 non-live,
snapshot771/scan47, все статики, live3/0skip и byte-reverse), записать WORKLOG
append-only; затем только уточнение B1–B6. C.18/F11/F4 не готовы к приёмке.

### Проверка сохранности перед остановкой (2026-11-01)

| Проверка | Фактический результат | Доказательство во внешнем досье |
|---|---|---|
| selfcheck editing.split_py (только принятый scan) | verdict ok; unit «263 passed in 1.71s»; corpus «кейсов 47, расхождений нет» | counts-before/editing.split_py.report.json |
| Полный non-live / JUnit | 3880/0fail/0error/0skip, 25.002s, 122 файла | full-regression-summary.json, full-non-live.xml |
| Collection | 3880, точная последовательность ID равна execution, каждый call passed ровно один раз | full-collection.ids.json, full-non-live.ids.json |
| Все snapshots / scan | 771/0; editing/split_py47/0 | snapshot-all.stdout.txt, snapshot-scan.stdout.txt |
| layers / limits / contract / security | 529/0; 529/0; 24/0; SEC ok | statics-summary.json + отдельные stdout |
| Клиент split_scan001 | exit0, полный ответ равен исходному expect | probe-scan.stdout.txt |
| Live Godot4.6.3 | 3/0fail/0error/0skip, 16.413s | live-three.xml, live/proof.json |
| Live восстановление | внешний project.godot335B/SHA958b3a92… восстановлен; все исходные UID сохранены; всё дерево файлов до/после равно | live/proof.json, live/before.json, live/after-engine.json |

Исходный свежий baseline: raw3007 файлов, audit-filtered3000, raw84gdUID
(один легитимный `__pycache__` fixture UID), audit83gdUID. Входящий
extensions/ref.gdshader.uid существовал **до** нашей работы; ни он, ни
легитимные skip_dirs/__pycache__ файлы не удалялись. Новые witnessed `.uid`
от нашего live архивированы и удалены только по before/after; источник равен.
Исторический C.17 tree2999 не переписан: сравнение идёт с нашим свежим baseline.

Сдаётся только preflight-документация и proposed ADR, **не реализация**:
production/все tools/47scancases/SCAN capability/старые тесты/соседи неизменны.
`WORKLOG` дописывается `ab`, весь префикс 541627 B и исторические4479CRLF
сохраняются; `final-reverse.json` проверяет точное равенство всех остальных
файлов и каталогов, исходный oracle и внешний project.godot. `_audit-handoff.md`
не редактировался. C.17 stage7/принятие сохранены, C.19 не начат.

**Где остановились / следующее действие:** аудитор явно уточняет B1–B6:
native boolean state; object reexports; normalized SHA и inverse M3;
consumer-owned fs.exists + читатель map/index без изменения substrate;
узкие scan/plan compatibility filters/pins; разрешение node_info352→247 и
tree168→116 для общего F4. До этого C.18/F11/F4 остановлены и **не готовы к
независимому аудиту как выполненная задача**. После уточнения начать с native
корпуса048+, а не с бизнес-кода; архивированные F4-пины вернуть перед правкой.

## C.18 — продолжение по §10 (сессия 74, 2026-11-01)

B1–B7 сняты явным уточнением аудитора. История preflight выше остаётся
историей, C.17 половина 1 и её независимое принятие/этап7 не меняются.
C.18 в работе, приёмки нет. F4 полностью вне C.18: selfcheck.py и proposed
ADR-0013 заморожены, class_api остаётся186/26; F4 — C.19, запись — C.20.

- B1/B2: native bool state и object reexports; B3: normalized donor SHA,
  M3 теперь raw-byte hash.
- B4: второй consumer-owned fs.exists, ADR-0014, старый split_gd вызов и
  substrate неизменны; фактические file/directory target cases обязательны.
- B5: только tool-filter/multi-tool pins в scan-тестах; 47 старых JSON,
  SCAN/карточка/refs/walk/text остаются побайтово.
- B7: pure arch.py, fresh map/index каждый вызов, без global-кэшей,
  ввод-вывод только app.py; zones/limits/name checks из живого эталона.

Новый byte/SHA baseline **до первой правки**: raw3008/audit3001 файлов.
Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c18-split-py-plan-20261101-resume/`.
`before.json`/`before-bytes/` содержат каждый исходный файл и каталог.
Промпт52701B/596CRLF/SHA d660dca361d639e65f68cab1980624999a79863b7e8662689cbf7c5c862ef0c7;
handoff100697B/628CRLF/SHA68790c1b6d518fbc87243bf13992826e2f327bb603cf224a07027423f4a14357.
WORKLOG548909B/SHAed447bfb763ad35ed499dd4c32c33cb7889907504cdf262a874c756e5058d680,
весь prefix и4479CRLF заморожены; дальнейшая запись только binary ab.
Внешний project.godot335B/SHA958b3a92… сохранён точными байтами.

**Следующее действие:** снять fresh native missing-without-addon case048,
красный F11-пин, переставить missing-ветку до addon-root, затем корпус плана.

### C.18 продолжение: B4 уточнён, F11 red → green

Пользователь явно выбрал «Паритет эталона»: занятая цель (файл/каталог)
даёт полный `ok:true` план с `errors`, не AppError из §10/B4. Текст сохранён
из native: `целевой файл уже существует: part.py`; fs.exists/ADR-0014 остаются.
В опубликованном корпусе уже 49 новых кейсов048–096, 100 вызовов эталона;
публикация не повторяется, C.17 47 кейсов не переписываются.
F11: `f11-red.xml` — 1 failed (invalid_input вместо not_found), затем только
перестановка проверки is_file до addon-root: `f11-green.xml` — 33 passed,
включая прежние 32 app-теста; stderr0, exact native message и одна metadata-call.
Досье остаётся `c18-split-py-plan-20261101-resume/`, команды/логи там же.
Этап7/приёмка C.17 сохранены; C.18 не принято, F4 и запись вне среза.

**Следующее действие:** схемы bool-state/object-reexports; новые красные plan-тесты,
затем pure arch.py и app-IO по B7. До этого план production не реализован.

### C.18 код и контракт: проверка в работе, не сдача

- `plan-red.xml`: 459 tests, 234 failures, 0 errors/skips; новые тесты до кода.
- Добавлены чистые inventory/groups/facade/plan/arch, проекция core, consumer exists,
  вторая ветка app (80 строк), отдельные схемы scan/plan; SCAN-декларация сохранена.
  B1 state bool, B2 reexports objects, B3 normalized donor SHA; ADR-0014 записан.
- `plan-green.xml`: 564 tests без провалов до парного refs-покрытия; тексты/сводки
  всех 36 успешных native-планов совпали. `contract-write`: 25 карточек.
- `selfcheck-first`: layers fail (json в domain запрещён), corpus fail (072 hook
  не исполняется общим snapshot_diff). JSON decoding перенесён в app, gate не менялся.
- Пользователь разрешил парный 072: native без hook дважды, равные ответы и дерево;
  `paired-refs-proof.json`, script2315B/SHAf163c0c10dde787772b64bddd512f293be433a9779700e7b8c724443b40e42bb.
  Прежний raw refs:null сохранён; добавлены отдельные строгие domain/Agent pins.
  Теперь 102 native calls; общий корпус видит обычный ответ, не подменённый gate.
- 068/069: общая strict-integer схема отказывает до app. Записаны exact schema text
  `(аргументы).target_lines: ожидался integer`, прежний native bridge и app text
  сохранены отдельно. Новые ожидания не трогают 47 принятых scan-кейсов.
- Разрешённые inventory-only companions: context count23→24, split_plan/read и SHA;
  только списки имён в соседних тестах. F4/selfcheck.py/ADR-0013 не менялись.

**Следующее действие:** обычный selfcheck → двойной snapshot/native differential →
последовательные мутации с exact restore → полный nonlive/живой прогон/соседи → записи.

### C.18 проверка реализации: ordinary selfcheck и дифференциал

- `selfcheck-green`: вердикт ok, unit566/corpus96, layers544/limits0/security0,
  contract25. `snapshot-full-1` и `snapshot-full-2`: 820/0, split_py96/0.
- Полный nonlive сначала выявил четыре оставшихся inventory-only count23-пина;
  исправлены только count24 в разрешённых gd_lint/node/scene/verify companions.
  `nonlive-proof.json`: 4183/0/0/0 (40.240s), selected IDs = executed один раз.
- Дополнительная fidelity-проверка карты: native UTF-16 JSON не принимает
  (чтение utf-8-sig), а json.loads(bytes) автоматически принимал. Живая съёмка
  дважды: `utf16-map-proof.json`, дерево/oracle неизменны. Новый тест 1failed →
  1passed; app декодирует карту utf-8-sig до json.loads, остаётся 80 строк.
- `differential-proof.json`: 91 донор (85 fixture + 6 submitted .py), auto/explicit,
  target900/100, 364 сравнения, по 728 native и port calls. 344 совпали, 20 —
  явно записанные границы policy/4MiB/plugin.cfg; других расхождений нет.
  Дерево/oracle неизменны, write helpers заблокированы; восемь чистых функций
  arch имеют идентичный native AST, кроме IO/cache-адаптаций load_map/name_index.
- Последний nonlive до дополнительного UTF-16 пина; новый итог будет измерен,
  не вычислен. C.17/статус7 не меняется, C.18 ещё не сдаётся.

**Следующее действие:** последовательные M1–M8/P1–P4/exists→is_file с copyfile
backup и exact SHA/EOL restore; затем final nonlive/selfcheck, соседние счётчики,
live3 и обратная байтовая проекция, записи для независимого аудита.

### C.18 мутации и окончательный nonlive/selfcheck

- Все мутации выполнены последовательно через внешний `mutation.py`, с
  copyfile backup/restore и одинаковыми bytes/SHA/CRLF/LF после каждого прогона.
  M1 symbols→funcs: 101failed; M2 errors→raise: 48failed; M3 raw SHA: 2failed;
  M4 null→{}: 2failed; M5 без __all__: 1failed (полный текст); M6 no-cycle:
  4failed; M7 ignore-target: 2failed; M8 line_start: 3failed. Дополнительный
  strict dispatch→schema-пин дал M8-contract: 1failed, без collection errors.
- P1 required.moved_names: behavioral **568/0/0/0**, gen_contract exit1;
  P2 os-domain и P3 foreign-app: lint_arch exit1; P4 старый F11 порядок:
  3failed; exists→is_file: 2failed (каталог и grep-пин). P5/F4 не запускался.
- `nonlive-final-proof.json`: **4185/0/0/0**, 37.077s; collect IDs совпадают
  с фактически исполненными, без дублей. Новые UTF-16 и schema-пины включены.
- `selfcheck-final`: **ok**, unit568/corpus96, layers544/limits0,
  security0, contract25 без drift. Исторический scan47 остаётся неизменен.
- `tests-map.md` дополнен судьбой C.18 и фактическими числами новых файлов;
  прежние 168 строк не удалены, F4 архив по-прежнему deferred/C.19.

**Следующее действие:** завершить ordinary selfcheck 23 принятых соседей с
точным восстановлением reports, live3 без skip и byte-reverse; затем финальные
записи и передача независимому аудитору. C.18 ещё не сдаётся/не принято.

### C.18 свежая проверка сдаваемой версии (2026-11-01)

- До новых правок снят `final-verification-before/`: 3189raw/3182audit файлов,
  795каталогов, 84raw `.gd.uid`. Исходный `before.json`/`before-bytes` не
  перезаписан; все 14 mutation backups совпали с текущим production SHA/EOL,
  все 23 neighbor reports — с исходными bytes. `final-preflight-proof.json`.
- Первый live-final: 3/0/0/0, 25.620s, и nonlive-handoff: 4185/0/0/0,
  39.857s; collect=executed once. Затем узкая сверка выявила **три лишних LF**
  на изменённых строках functions/usages inventory и context manifest.
  Восстановлены только эти CRLF; `companion-eol-proof.json` содержит exact
  before/after, baseline replacement и EOL. Production не менялся.
- `narrow-scope-proof.json`/`narrow-scope.diff`: 14 файлов равны исключительно
  разрешённым replacements. C.17 test_walk без изменений; в остальных scan
  тестах только tool-фильтр, multi-tool descriptor/manifest и имя unknown.
  Пин163 **не снят**: проверяется original manifest inputs за вычетом C.18,
  все исходные163facts сохранены; всех47case bytes/SHA прежние. SCAN declaration
  и schemas перенесены **побайтово**, исключены лишь docstring и TOOLS aggregator.
  Нет удалённых каталогов; 68 новых каталогов только внутри plan fixtures.
- После EOL-коррекции `nonlive-submitted-proof.json`: **4185/0/0/0**, 39.226s,
  точное равенство collect IDs/фактически выполненных once, включая UTF-16 и
  strict dispatch→schema. `snapshot-submitted`: **820/0**, split_py96/0.
- `live-submitted-proof.json`: Godot4.6.3, **3/0/0/0**, 24.020s. Внешний
  project.godot exact-restored, все исходные UID, файлы и каталоги exact;
  probe scene отсутствует. Только новые witnessed UID архивированы и удалены.
  Root plugin.gd.uid не менялся, поэтому restoration flag false означает
  «восстановление не требовалось»; raw `.gd.uid`84→84/audit83. Входящий
  `__pycache__` fixture UID и `.gdshader.uid` не удалялись ради старого числа83.
- `selfcheck-submitted`: **ok**, unit568/corpus96, layers544/limits0,
  contract25 без drift, security0. Отдельные layers/limits/security/contract
  `*-handoff` тоже exit0/status ok, их production/gates SHA не менялись.
- `probes-proof.json`: actual CLI cases001(scan),048(F11),050(explicit),
  075(BOM/CRLF),077(occupied errors-data); ответы полностью равны expect,
  expected refusal exit1, остальные exit0, все fixture trees неизменны.

**Следующее действие:** завершить повторный ordinary selfcheck23соседей после
EOL-коррекции, затем финальная обратная byte/SHA-сверка и передача аудитору.

### C.18 сдача — готов к независимому аудиту, не принято

Повтор `neighbors-submitted-proof.json` завершён: все23 ordinary selfcheck
exit0, unit/corpus до=после, каждый report восстановлен copyfile **побайтово**.
В частности class_api186/26, node_info352/65, tree168/40, split_gd625/102,
verify188/75, api_check206/52. F4/старый selector этим не исправлялись.
Этап7 и ported остаются **только у independently accepted C.17 scan**.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c18-split-py-plan-20261101-resume/`.
`README-final.md` — индекс доказательств; `reverse-proof.json` — проекция
каждого исходного файла и after facts, `final-byte-proof.json` — дополнительная
сверка относительно свежего final-verification-before, `final-files.json` —
полный raw file/dir inventory. `sha256-changes.txt` содержит **все** добавленные
и изменённые сдаваемые файлы, `sha256-production.txt` — production/card subset.
Никаких удалённых исходных файлов/каталогов; raw3189/audit3182files,
795каталогов, raw84/audit83 `.gd.uid`, debris0. Старые24карточки,47scanJSON,
refs/walk/text, original core prefix, gates/shared/platform/prompt/handoff
сохранены. WORKLOG дописан binary ab; весь прежний префикс и4479CRLF exact.

#### SHA256 production и новой карточки

Пути `.py` ниже относительно `python/modules/editing/split_py/`;
полные пути и SHA всех тестов/фикстур/документов — в `sha256-changes.txt`.
Все12production файлов LF-only; app80строк, ни один лимит не превышен.

| Путь | SHA256 |
|---|---|
| `app.py` | `56891adf069bbcbb219735bcba1d41353b1089eb38c0c4559c70b7f67d874a63` |
| `domain/arch.py` | `26cae2a55c8a3278106ededf4988cd651b42a1ea1a08db83e3e20c51ef4d8461` |
| `domain/core.py` | `c1a2ac01fdc83d4241b4f5d5b881cfe5d9a2b386a8c97fdb7c798a4058465899` |
| `domain/facade.py` | `13ae382a6ec917d593b361c1d5ae59539411ad5ae21bf457733080437066e7fe` |
| `domain/groups.py` | `b8de9483e78d0f16c4cd67e2a8cf24ce1418741e407e20399b941bb36137a443` |
| `domain/inventory.py` | `c96e0c1286a8dd138e086769d7e8e09288aeb9ae7a514249265b8253e3e40bf6` |
| `domain/plan.py` | `d0939388fec58d0b5c861b44cdc4b5d4fa0af24fe0f05539cc08909f438e8bff` |
| `module.py` | `8cb1c975eef36dfe830357073f836c88b916b74e23411e49b8cbfd98e2506a70` |
| `ports.py` | `5b0d49b52d5c3675dd81d7665ef5e9a3fd1502dd09921199357dac54ca6b9ef2` |
| `tools.py` | `cdc5f6e6d674c211daa10aa100428c8a8bd2a295d2a8ac8cf1ad4bd477170496` |
| `tools_split_plan.py` | `0d392048be4ba07c16a538787162571d80e049e170945d54916f43fea0452eb3` |
| `tools_split_scan.py` | `22d1a3a80224ff236eee5e867969d4c148d87321479f3702459785c99c25691a` |
| `contract/capabilities/split_plan.json` (от корня плагина) | `ce5d00e742080ea98387856ad04f85e1693379c260dd7efbac19261593a02f26` |

#### Намеренные границы сдачи

1. **F4 полностью вне C.18**: `tools/selfcheck.py` frozen, ADR-0013 proposed,
   13diagnostic pins только во внешнем `.red` архиве. C.19 отдельно, соседние
   186/26,352/65,168/40 не пересчитаны. P5 не выполнялся.
2. **Только read-only plan**: создание/удаление, WAL/preview/apply/rollback
   split-плана — C.20. Никакой записи проекта этим инструментом, C.20 не начат.
3. **arch без audit-подсистемы**: pure domain, map IO через app/fs utf-8-sig,
   свежие map/index на каждый вызов, никакого глобального кэша.
4. **Schema/path/safety boundaries явные**: cases068/069 strict integer schema
   отказывает до app; native bridge/app тексты сохранены отдельно. PathPolicy,
   4MiB и plugin.cfg дают20документированных differential boundaries из364,
   не объявлены совпадением. Остальные344equal, включая6submitted `.py`.
5. **072 hooked refs:null**: исходный raw не переписан, отдельные строгие
   domain/Agent pins; generic snapshot сравнивает разрешённую обычную native
   пару. Null не превращён в `{}` ради схемы или зелёного корпуса.
6. **Native, не улучшения**: bool state, object reexports/native order,
   SHA нормализованного utf-8-sig/universal-newlines текста; занятый файл или
   каталог добавляет errors полного ok:true, не AppError (ADR-0014).
7. **Не самостоятельная приёмка**: `_audit-handoff.md` не менялся;
   F4/C.19 и запись/C.20 не начаты, C.18 ещё не принят.

**Следующее действие:** независимому аудитору проверить C.18 по этому листу
и досье; приёмку и дальнейший срез определяет аудитор/пользователь.

## C.19 — F4 (сессия 75): preflight, нужны два уточнения

Пользователь принял C.18 своими прогонами и поставил отдельный долг F4.
Предыдущие записи C.18 сохранены как история; C.19 самостоятельно не принят,
новый этап не назначается. Запись split-плана остаётся C.20.
Постановка: `docs/porting/_start-prompt.selfcheck_f4.md`, §0–§9.

До первой repository-правки сохранён свежий полный byte-backup:
`C:/Users/Lich/AppData/Local/Temp/opencode/c19-selfcheck-f4-20261101-preflight/`:
`before.json`, `before-bytes/`, `project.godot.before`.
Raw3190/audit3183 files, raw84/audit83 `.gd.uid`; дополнительный относительно
аудиторской базы C.18 файл — новый C.19 prompt. Исходные файлы/UID не удалялись.
Весь WORKLOG555894B/4479CRLF сохраняется, записи только binary `ab`.

SHA256 до правки:
- `tools/selfcheck.py`:16267B/334CRLF/334LF,
  `36fa1c097b24afbeffe7078b1a4ddf32b748ebc56ae503c8bbfe23d2d436959b`;
- `docs/adr/0013-selfcheck-unit-selector.md`:4406B/54LF,
  `8dfaadb6bceb470f397b411d497d799715d5fe1523cdd543f0e2010936c40bb5`;
- C.19 prompt:10394B/134CRLF,
  `123da9f93202e9f792c59a1eac7f4a304b514f3775722628d03b0231f85e5974`;
- `_audit-handoff.md`:101858B/630CRLF,
  `d076d633911c6153aeb0a1849bb27f623d87e864d8b54859a00e2091da171fd4`.

### Блокер 1: буквальный §2 расходится с §1/§4

Read-only внешний `predict.py` перехватил настоящие targets `check_unit`
всех44механик и вызвал настоящую `collect_count` для изменяющихся списков.
`prediction-proof.json` сохраняет все списки, состав/порядок/кратность и числа:

| Механика | До | Буквальный §2 | Longest-prefix / разрешено |
|---|---|---|---|
| `engine_kb.class_api` | 186 | 128 | 128 |
| `scene_model.node_info` | 352 | 247 | 247 |
| `scene_model.tree` | 168 | 128 | 116 |

`stem in tools` не узнаёт владельца `test_scene_ops_bridge.py`: публичное
имя — `scene_ops`, не `scene_ops_bridge`. Кроме того, буквальный §2 меняет
кратность targets у четырёх неизменяемых соседей: `editing.split_gd`,
`scene_model.node_delete`, `scene_model.node_rename`, `scene_model.node_reparent`.
Числа625/131/162/155 остаются прежними, но требование41неизменных списков
нарушается. Полный longest-prefix сохраняет остальные41список и даёт116.
Рекомендация: разрешить настоящий longest-prefix с сохранением прежних
feature-масок, sorted/порядка/кратности и ≤10добавленных строк в одном месте.

### Блокер 2: byte-equality свежих reports

Сам `selfcheck` включает время pytest в `checks.unit.detail`. Существующие
доказательства повторных прогонов показывают, например, functions33passed
в0.67s против0.69s: reports не равны байтами при неизменном счётчике.
В некоторых baseline-reports также исторический layers450, свежий544.
Это не новая находка в production, а конфликт буквальной byte-equality
§5/§6 с обязательным повтором44selfcheck и запретом ручной правки JSON.
Рекомендация: архивировать каждый настоящий свежий report, проверить числа
и targets, затем copyfile exact-restore baseline у41неизменённой механики
(для исходно отсутствовавших reports восстановить отсутствие), без редактирования
JSON. У трёх разрешённых дельт оставить свежие отчёты.

Production/ADR/prompt/handoff/corpus/cards/reports не менялись; новые пины,
red/green, мутации и44after ещё не запускались. Read-only прогноз проверил
полное SHA-дерево до/после и подтвердил его неизменность.

**Следующее действие:** получить решение пользователя по longest-prefix
вместо буквального §2 и archive/copyfile-restore41reports перед red-пинами.

### C.19 продолжение — §10/B1/B2 разрешены (сессия 76)

Пользователь снял оба противоречия в §10 постановки. В силе: настоящий
longest-prefix с границей `_` и exact-match; прежнее поведение non-tool
feature-масок (§2), sorted/порядок/кратность41списка; только128/247/116;
никаких хардкодов, все изменения selfcheck только внутри `check_unit`, ≤10строк.
Reports:44процесса по одному, stdout/fresh JSON/SHA во внешнем архиве,
41baseline exact-copyfile-restore, у3дельт fresh JSON; duration не нормализуется.
ADR будет активирован только как уже разрешённое аудитором решение, а не
как самостоятельная приёмка реализации C.19.

Свежее досье до новых правок:
`C:/Users/Lich/AppData/Local/Temp/opencode/c19-selfcheck-f4-20261101-resume/`.
`before.json`/`before-bytes` сохраняют все3190raw/3183audit файлов, 84raw/83audit
UID и целый WORKLOG559230B/4479CRLF. Prompt16275B/181CRLF/SHA
`0a8de27acf028c808410aa96d649e897220d234a326e72a60b8b149bdc4cd498`;
handoff102499B/630CRLF/SHA
`61c4510182c4d21e9a2817694da1473fbcf48f8b78a01fb39c8d95c9da356046`.
Оба файла заморожены; external project335B/SHA958b3a92… сохранён exact.
Исходный selector16267B/334CRLF/SHA36fa1c09… не изменён.
Сохранены настоящие44old-target lists (`targets-before.json`).

Прежний `counts-before.json` снят ещё до C.18 и содержит split_py263/47,
а двадцать текущих report-файлов отсутствуют. Чтобы получить честные44
baseline SHA с текущим принятым568/96, запущены свежие44before selfcheck
на неизменном старом селекторе. Это собственная сверка C.19, не переписывание
аудиторской базы §0. `counts-before/*.report.json` сохранят все44полных
настоящих reports, исходные24report-файла отдельно остаются в `before-bytes`.
Создан активный новый пин-файл (64кейса): исходные13диагностических кейсов
проверяют тот же клиентский `check_unit`, добавлены два real counts,
matrix44полных списков, exact/boundary/scene_ops и non-tool multiplicity.
Старый агент/старые тесты не копировались и не запускались.

**Следующее действие:** снять `f4-red.xml`, дождаться44before, затем изменить
только selector внутри `check_unit` и получить green64 перед мутациями.

Red получен до правки selector: `f4-red.xml`64/10failures/0errors/0skipped,
54passed,5.916s,stderr0. Три real counts186/352/168 вместо128/247/116,
три matrix-листа и foreign/longest/scene_ops пины красные; остальные41
legacy-target lists сохранены. Файл selfcheck всё ещё SHA36fa1c09…;
ADR proposed. **Следующее действие:** завершить44before, затем7строк
внутри check_unit и green64, после него последовательные мутации.

44before завершены отдельными процессами на SHA36fa1c09…:
24ok/20blocked (заготовки не PASS),split_py568/96,split_gd625/102,
class_api186/26,node_info352/65,tree168/40. Все44canonical before reports
и stdout/SHA сохраняются в counts-before; исходные24bytes тоже сохранены.
В check_unit добавлено7строк: `_owner` из `_catalogue()[0]`, exact/longest
по `_`, owner-фильтр только публичной mask. `selector-bytes-proof.json`:
16647B/341CRLF/341LF/SHA
`4cc9a63f79e2d9e8fa401ecf5bb4345f3d54d0e8c1ccc57588f00d511d1fd82b`,
всё вне единственного фрагмента byte-exact, исходные CRLF сохранены.
Green64/0failures/0errors/0skip,5.174s,stderr0. `target-matrix-proof.json`:
три real after128/247/116, ровно3изменённых списка;41byte-equivalent
список по составу/порядку/кратности. ADR-0013 принят как решение аудитора
75–76/§10; реализация C.19 не принята. tests-map дописан без изменения168строк.

**Следующее действие:** последовательныеM1old/M2api-only/M3ignore-tools/P1,
затем полный регресс/гейты/live3 и44after с точным протоколом reportsB2.

Сдаваемая версия прошла последовательныеM1/M2/M3/P1:10/7/10/31failures,
везде errors/skips0 и exact-copyfile-restore bytes/SHA/341CRLF.
M2api-only оставляет class_api128 зелёным, но реальные node_info/tree красные.
Полный `nonlive-final`:4249/0/0/0,35.609s,stderr0,collect/executed IDs once;
snapshot820/0,8.046s,contract25/no drift,layers544/limits0/securityok.
Godot4.6.3/live-final:3/0/0/0,21.703s,no skip; externalproject335B exact,
все pre-livefiles/dirs/UID exact,raw84gdUID/83audit/root unchanged,
probe-scene отсутствует. Только новые witnessedUID архивированы и удалены;
pre-existingfixture__pycache__UID/gdshaderUID сохранены.
Запущены44after отдельными последовательными процессами; fresh/SHA наружу,
41copyfile-restore canonicalbaseline и3fresh reports согласноB2.

**Следующее действие:** завершить44after, опубликовать обе44SHA-таблицы,
binaryabWORKLOG/4479CRLF и финальное byte-досье; затем передать аудитору.

### C.19 готов к независимому аудиту, не принято

44after завершены отдельными последовательными процессами:
class_api128/26/ok,node_info247/65/ok,tree116/40/ok; остальные41unit counts,
состав/порядок/кратность targets и весь corpus неизменны. Всего24ok/20blocked;
заготовки не PASS. `counts-after.json`/`fresh/<id>.json|.stdout.txt` сохраняют
настоящие fresh reports/SHA;41финальный report побайтово совпадает с
canonicalbefore из44свежих before (§10/B2),3reports остаются свежими.
Исходные24reports тоже сохранены вbefore-bytes, старыйC.18архив263/47 не
подменяется; JSON/длительности не редактировались, backups не удалены.
Таблица44файлов ниже идентична `report-matrix.md` и append-WORKLOG.

На финальном64-case наборе дополнительный redundant exact-кейс заменён
public-mask unknown-owner `test_apix.py`: теперь None-guard проверяется
при `name in tools`, а не только через legacy mask. Все13исходных
диагностических кейсов сохранены. Код selfcheck не менялся.
Green-submitted64/0/0/0,7.931s; nonlive-submitted4249/0/0/0,47.838s,stderr0,
collect=executed once,4185старых IDs/порядок сохранены и64новых.
Последовательные submittedM1/M2/M3/P1:10/7/10/30failed; дополнительный
P2unknown-guard/P3underscore-boundary:1/2failed. Везде errors/skips0,
copyfile-restore bytes/SHA/341CRLF точное. Первые31failed/P1 и35.609s
nonlive сохранены как промежуточные, не выданы за финальную версию.
Live-submittedGodot4.6.3:3/0/0/0,26.222s,no skip; externalproject335B/SHA
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`,
все files/dirs/originalUID exact,raw84/audit83,rootUID unchanged,
probe-scene absent; удалены только новые witnessedUID с byte-архивом.
Snapshot820/0,contract25/0,layers544/0,limits544/warnings0,securityok.
CLIprobes001/048/050/075/077 exactexpect/treeunchanged, ожидаемый F11exit1.

После записей проверяется `final-byte-proof.json`/`final-files.json`:
3211raw/3204auditfiles,795dirs,21added (1pin+20canonical skeletonreports),
30changed,0deleted,no new/deleted dirs,debris0. Всё вне разрешённых
7nonreportpaths и44reportpaths byte-exact; все moduleproduction,
corpora/cards/shared/platform/editor/прочиеtools/prompt/handoff заморожены.
WORKLOGbinaryab/fullprefix/4479CRLF; PROGRESS строкаsplit_py и168старых
tests-map строк не менялись. ADR принят как решение аудитора75–76/§10,
но реализация C.19 не принята и новый этап7/ported себе не назначается.

SHA сдаваемого selector/пина/ADR:

| Файл | SHA256 |
|---|---|
| `tools/selfcheck.py` | `4cc9a63f79e2d9e8fa401ecf5bb4345f3d54d0e8c1ccc57588f00d511d1fd82b` |
| `tests/py/tools/test_selfcheck_unit_selector.py` | `c498a8933d0e2d9e238c4dfca27091f8922a9bf767d1a8c84fe5a2d7fcca0f75` |
| `docs/adr/0013-selfcheck-unit-selector.md` | `ad8fa7cb2803b619e61da63a9ca902246b6d78acb602e16b7fe379d835812b4e` |

Полные SHA: `sha256-delivery.txt` (7nonreportpaths),
`sha256-changes.txt` (51paths) в `c19-selfcheck-f4-20261101-resume/`;
индекс `README-final.md` связывает snapshot/оба44прогона/JUnit/IDs/live/
mutations/byteproof и исходные backups. Намеренные границы: только F4,
non-tool masks сохранены, неизвестный owner остаётся, duration не контракт;
20skeleton blocked не засчитываются как ported. C.20/create-delete/write не начат.

#### C.19 —44файла: было/стало/дельта и baselineSHA→finalSHA

| Report-файл | Unit было | Unit стало | Дельта | Baseline SHA256 | Финальный SHA256 |
|---|---:|---:|---:|---|---|
| `reports/selfcheck/assistant.chat.json` | — (not_implemented) | — (not_implemented) | — | `9cf7fb1798d270165eccf6a4e2efa819de59bf6c7520e5eeb6e25eb078dea9ac` | `9cf7fb1798d270165eccf6a4e2efa819de59bf6c7520e5eeb6e25eb078dea9ac` |
| `reports/selfcheck/assistant.history.json` | — (not_implemented) | — (not_implemented) | — | `cc9af7f2dd5d300a5cfc2f681b5f86d333be6d5176591147a1ddcf64da0f9e33` | `cc9af7f2dd5d300a5cfc2f681b5f86d333be6d5176591147a1ddcf64da0f9e33` |
| `reports/selfcheck/assistant.model_choice.json` | — (not_implemented) | — (not_implemented) | — | `2839bc23d174c25c8f3148479d42ff484a6cae1efcfa0ad205c50ced5d15df8a` | `2839bc23d174c25c8f3148479d42ff484a6cae1efcfa0ad205c50ced5d15df8a` |
| `reports/selfcheck/assistant.routing.json` | — (not_implemented) | — (not_implemented) | — | `c78203cb79414c43f0b27eecd7f9f1320b945f9725d9103cb1ee1122d904d552` | `c78203cb79414c43f0b27eecd7f9f1320b945f9725d9103cb1ee1122d904d552` |
| `reports/selfcheck/code_intel.function_card.json` | — (not_implemented) | — (not_implemented) | — | `3faea5ae2db71b8477ead9a016c9ae67ec181b10fac5d7e065649c270608a7b7` | `3faea5ae2db71b8477ead9a016c9ae67ec181b10fac5d7e065649c270608a7b7` |
| `reports/selfcheck/code_intel.functions.json` | 33 | 33 | 0 | `e67152b57ab0fbca7c422c8176a0c5be2538c8b868a58ca004b8f9e7b27643c2` | `e67152b57ab0fbca7c422c8176a0c5be2538c8b868a58ca004b8f9e7b27643c2` |
| `reports/selfcheck/code_intel.usages.json` | 66 | 66 | 0 | `6ac32b662248cd561e256e698a32e7c725493b0a73a3d226d132f914d6de3ccf` | `6ac32b662248cd561e256e698a32e7c725493b0a73a3d226d132f914d6de3ccf` |
| `reports/selfcheck/context.ask.json` | — (not_implemented) | — (not_implemented) | — | `c75d85f4fe55d120f6d28a5b5674bb91bceb23d0ef9daf4cf10e23a9c2b5d032` | `c75d85f4fe55d120f6d28a5b5674bb91bceb23d0ef9daf4cf10e23a9c2b5d032` |
| `reports/selfcheck/context.editor_context.json` | 28 | 28 | 0 | `79500370c66f6f0a84e543194145f1b0b07965a6b7038d88fb5cc269b0749219` | `79500370c66f6f0a84e543194145f1b0b07965a6b7038d88fb5cc269b0749219` |
| `reports/selfcheck/context.gather.json` | 33 | 33 | 0 | `d0a7cb3d1732ce8ce8df09b1ab5dbf00fd97b3028db85a99c2706d7950bd58f0` | `d0a7cb3d1732ce8ce8df09b1ab5dbf00fd97b3028db85a99c2706d7950bd58f0` |
| `reports/selfcheck/context.runtime_snapshot.json` | — (not_implemented) | — (not_implemented) | — | `da65a7e3c5dfec25567aecbcf2ce0f954cd77ec4f4bd1dca1f81bc00b1341ebd` | `da65a7e3c5dfec25567aecbcf2ce0f954cd77ec4f4bd1dca1f81bc00b1341ebd` |
| `reports/selfcheck/editing.file_refactor.json` | — (not_implemented) | — (not_implemented) | — | `f40458b5a9e8520ba4fe1d0c9fdd512026ca5cb5352579ee168c5ea1dd68f184` | `f40458b5a9e8520ba4fe1d0c9fdd512026ca5cb5352579ee168c5ea1dd68f184` |
| `reports/selfcheck/editing.paths_preview.json` | — (not_implemented) | — (not_implemented) | — | `88bd91a4a699ef8f19b44c9111624d7456cf7aab92cce34faa0384afad767460` | `88bd91a4a699ef8f19b44c9111624d7456cf7aab92cce34faa0384afad767460` |
| `reports/selfcheck/editing.resource_ops.json` | — (not_implemented) | — (not_implemented) | — | `900ce0236cb51c1ce14caa3d8588c8d364831b70e14398ffb26609f78e1614c4` | `900ce0236cb51c1ce14caa3d8588c8d364831b70e14398ffb26609f78e1614c4` |
| `reports/selfcheck/editing.rollback.json` | 24 | 24 | 0 | `89ff7e648184512acc3742f8feb5ae2951689c5046ef8d194bbcc8b75e37f9d6` | `89ff7e648184512acc3742f8feb5ae2951689c5046ef8d194bbcc8b75e37f9d6` |
| `reports/selfcheck/editing.scene_ops.json` | 25 | 25 | 0 | `d744ee853a8d8a4b52942643d9a1aac9f97d029a291251562a16b44e04df85b6` | `d744ee853a8d8a4b52942643d9a1aac9f97d029a291251562a16b44e04df85b6` |
| `reports/selfcheck/editing.split_gd.json` | 625 | 625 | 0 | `934e1e8475ca50ce07af3b12426b8a0fe5376ff49d3428c91a295630455680e5` | `934e1e8475ca50ce07af3b12426b8a0fe5376ff49d3428c91a295630455680e5` |
| `reports/selfcheck/editing.split_py.json` | 568 | 568 | 0 | `29bdad5897280d2901ee6cdabd5f3101dcf620c4055fcae8d7d4a9782aca9d0b` | `29bdad5897280d2901ee6cdabd5f3101dcf620c4055fcae8d7d4a9782aca9d0b` |
| `reports/selfcheck/editing.symbol_rename.json` | 15 | 15 | 0 | `6d871241fdfe659890f5618b29ae542af5088cc8576f877396687f6368ce2301` | `6d871241fdfe659890f5618b29ae542af5088cc8576f877396687f6368ce2301` |
| `reports/selfcheck/editing.write_apply.json` | 44 | 44 | 0 | `356fcb7ef4402aa15bdf28100811aa0380e1863de3c4fd2bce17af17ad7820b8` | `356fcb7ef4402aa15bdf28100811aa0380e1863de3c4fd2bce17af17ad7820b8` |
| `reports/selfcheck/editing.write_preview.json` | 45 | 45 | 0 | `44f31d81c7015f3591efd9c51a4b60fcf112aba03130774d4b37dbf49c878383` | `44f31d81c7015f3591efd9c51a4b60fcf112aba03130774d4b37dbf49c878383` |
| `reports/selfcheck/engine_kb.api_cache_refresh.json` | — (not_implemented) | — (not_implemented) | — | `e070cb29c120ffeb3dc479d1116657926d98909328eb5319309e4e16ac018021` | `e070cb29c120ffeb3dc479d1116657926d98909328eb5319309e4e16ac018021` |
| `reports/selfcheck/engine_kb.class_api.json` | 186 | 128 | -58 | `43899d33bbbe92ac47dc36de159f2374d59df5dfbcef86d6f548b2199d527b0d` | `5550799fae333808767b47af29ea47151dc28cc4a154c863d5526577a51cd9b5` |
| `reports/selfcheck/engine_kb.engine_info.json` | — (not_implemented) | — (not_implemented) | — | `75e7cf53021f28abd7e41964b4175a3fdd09e6bbd9afb0a72e374e1453ac9046` | `75e7cf53021f28abd7e41964b4175a3fdd09e6bbd9afb0a72e374e1453ac9046` |
| `reports/selfcheck/project_ops.architecture.json` | — (not_implemented) | — (not_implemented) | — | `c961556ebc4fc44e309df3c55b3297e6d7d4442103081113b901b1e1dedeae64` | `c961556ebc4fc44e309df3c55b3297e6d7d4442103081113b901b1e1dedeae64` |
| `reports/selfcheck/project_ops.settings_get.json` | — (not_implemented) | — (not_implemented) | — | `7e5c4f12fa0adb32390fb7bad87d27eba6df6bda7bb7c9e5a82c9bd1bd0aacd3` | `7e5c4f12fa0adb32390fb7bad87d27eba6df6bda7bb7c9e5a82c9bd1bd0aacd3` |
| `reports/selfcheck/project_ops.settings_set.json` | — (not_implemented) | — (not_implemented) | — | `392db9207a61774583bc51dcb3e134a22b61df373facc6f6db6cf88e3598983a` | `392db9207a61774583bc51dcb3e134a22b61df373facc6f6db6cf88e3598983a` |
| `reports/selfcheck/project_text.read.json` | — (not_implemented) | — (not_implemented) | — | `3fedd16a486ce9130c6dbe206548f67c8de9834f9fd1dc688f0b87e5d77a32f6` | `3fedd16a486ce9130c6dbe206548f67c8de9834f9fd1dc688f0b87e5d77a32f6` |
| `reports/selfcheck/project_text.search.json` | 29 | 29 | 0 | `54604a465d45c3e02b35de8a0cf7f48920602ed7b40f1754a1ac27cf2536b5e7` | `54604a465d45c3e02b35de8a0cf7f48920602ed7b40f1754a1ac27cf2536b5e7` |
| `reports/selfcheck/project_text.tree.json` | — (not_implemented) | — (not_implemented) | — | `0c1b9359baa824fc87425d1bff1c450ab2139968a9c95259608ce3a0a22cfcce` | `0c1b9359baa824fc87425d1bff1c450ab2139968a9c95259608ce3a0a22cfcce` |
| `reports/selfcheck/scene_model.connections.json` | 108 | 108 | 0 | `707182352c2a8ae401f8d51e1a9a8dbfa4d916791363e4b5b5613157cc5e4b33` | `707182352c2a8ae401f8d51e1a9a8dbfa4d916791363e4b5b5613157cc5e4b33` |
| `reports/selfcheck/scene_model.node_delete.json` | 131 | 131 | 0 | `ba81aa09e2ecda87203f5d44b406c06bc68d5a7d8d7770859b3261f22c1aa3c0` | `ba81aa09e2ecda87203f5d44b406c06bc68d5a7d8d7770859b3261f22c1aa3c0` |
| `reports/selfcheck/scene_model.node_info.json` | 352 | 247 | -105 | `26864f522e3357abb835003817a7e184321a1cebd76007319b9c1aac4b02e57d` | `5123d6d8d77480306dfa286daaf54b563aed7623f152358d6c991be0357de8fa` |
| `reports/selfcheck/scene_model.node_rename.json` | 162 | 162 | 0 | `38e4404cc04895d28a4a46d921be3e8a42647229681cba5edc6fac32a496eecd` | `38e4404cc04895d28a4a46d921be3e8a42647229681cba5edc6fac32a496eecd` |
| `reports/selfcheck/scene_model.node_reparent.json` | 155 | 155 | 0 | `5567d5bb8011d5f62584a43cbadc2688b856c60871ac017caffcfa11a3061386` | `5567d5bb8011d5f62584a43cbadc2688b856c60871ac017caffcfa11a3061386` |
| `reports/selfcheck/scene_model.scene_deps.json` | 176 | 176 | 0 | `090b360efd5d5b572de49ecb95180621172b91d43126dd1a0985865ae3a1ed88` | `090b360efd5d5b572de49ecb95180621172b91d43126dd1a0985865ae3a1ed88` |
| `reports/selfcheck/scene_model.tree.json` | 168 | 116 | -52 | `07822c0c20b8d5aafa524188c506e91703f8ed602e9e8340e8561108068db112` | `ecb3e957a31b13440caec2c81a17f8a7b898cd197826549a9336653c2a359feb` |
| `reports/selfcheck/verification.action_judge.json` | — (not_implemented) | — (not_implemented) | — | `0c2ccb9c4d4750e5685789a76169a70563fb10bb22cafd0605c3df19b594551d` | `0c2ccb9c4d4750e5685789a76169a70563fb10bb22cafd0605c3df19b594551d` |
| `reports/selfcheck/verification.api_check.json` | 206 | 206 | 0 | `37c3833af0201b653e0a5e1fa6a5b22cbf1f5a5f70fd6776057a6beeb8ab1a38` | `37c3833af0201b653e0a5e1fa6a5b22cbf1f5a5f70fd6776057a6beeb8ab1a38` |
| `reports/selfcheck/verification.check.json` | 188 | 188 | 0 | `1315b0000774056470e9ddd58a65821aae3bfd053547239e476378a1c74fd3bc` | `1315b0000774056470e9ddd58a65821aae3bfd053547239e476378a1c74fd3bc` |
| `reports/selfcheck/verification.gd_lint.json` | 126 | 126 | 0 | `03f20fa1d750b981dac1f5cf76dfe9cfda8921ecbb73482a60450e1a6c9282db` | `03f20fa1d750b981dac1f5cf76dfe9cfda8921ecbb73482a60450e1a6c9282db` |
| `reports/selfcheck/verification.headless.json` | — (not_implemented) | — (not_implemented) | — | `3f5ae37a535dff0a958725c33fbbffc3d96ccbd7db9f9405fde32a3344bad258` | `3f5ae37a535dff0a958725c33fbbffc3d96ccbd7db9f9405fde32a3344bad258` |
| `reports/selfcheck/verification.runtime_checks.json` | — (not_implemented) | — (not_implemented) | — | `b791ea972cd307d076d6aaf3d18415502beab21242672000fa6fbda600c284b8` | `b791ea972cd307d076d6aaf3d18415502beab21242672000fa6fbda600c284b8` |
| `reports/selfcheck/verification.tscn_lint.json` | 315 | 315 | 0 | `2daad412acb1040284d020658eb447cc11aa72dc46f1b572922b0601e98e52ad` | `2daad412acb1040284d020658eb447cc11aa72dc46f1b572922b0601e98e52ad` |

**Следующее действие:** независимый аудитор проверяет C.19/§10 и принимает
или возвращает findings; C.20 не начинать.

### C.19 принят аудитом 2026-11-01 (сессия 76)

Решение аудитора из постановки C.20: selector pins 64/0/0/0; non-live
4249/0/0/0; snapshot 820/0; contract 25; layers/limits 544/0; security ok.
Приняты ровно три дельты 186→128 (`engine_kb.class_api`), 352→247
(`scene_model.node_info`), 168→116 (`scene_model.tree`); остальные 41
механика неизменны. 44 отчёта равны опубликованным SHA кроме трёх
изменённых; M1 и подложка ловятся. Это закрывает F4, но не меняет принятый
этап 7 `split_scan/plan` и не означает приёмку записи C.20.

**Следующее действие:** начать C.20 по
`docs/porting/_start-prompt.split_py_apply.md`: сначала зафиксировать базис,
лист и proposed ADR-0015, затем снять корпус 097+ и получить red-пины.

### C.20 — запись (сессия 76)

Срез начат после записанной выше независимой приёмки C.19. Полная побайтовая
проекция снята **до первой правки репозитория** во внешний файл
`%LOCALAPPDATA%/Temp/opencode/c20-pre-tree.json`: 3212 raw-файлов,
795 каталогов, 84 raw `.gd.uid`; JSON 679407 B, sha256
`03cf2de84a73b92ba8261219a0e634f6aa1d9f7520989068b58a829aef468912`.
Отличие raw от аудит-счёта постановки — семь файлов `reports/` и один
корневой `.gd.uid`; база постановки после появления prompt — 3205/789/83.

Выбранная стратегия — перенос по спецификации с literal-паритетом
`apply_prepared_split:718-767` и safety-надстройкой ADR-0005. Старый плагин
только читается; его файл 44114 B имеет sha256
`87cb4d5209c070f2f65ad45c16086e7c99b561ce677c6f8b1d1fd57b545526e7`.

#### Базис SHA до правки C.20

Полная таблица находится во внешней проекции; ниже все существующие файлы,
которые разрешено менять в срезе. Новый путь до создания помечается `absent`.

| Файл | bytes | SHA256 до C.20 |
|---|---:|---|
| `docs/parity.md` | 18011 | `f45b5329e7ed2db680044f972245f360900c2869e98b672aab68979819eb77cf` |
| `docs/PROGRESS.md` | 57837 | `92caa2e7f3ceb561e27da76fb742d7af538476e8b06927469cc777a17f59393d` |
| `docs/porting/editing.split_py.md` | 85524 | `cec93a975576c4d91c280e655d138242b6e2bfbd8a5ac28edd038a0754a53718` |
| `docs/WORKLOG.md` | 578555 | `b13329ed0a67cc00be0e1d480a3a4d01134d610c42b79cad9c41db320e3330f2` |
| `docs/tests-map.md` | 61778 | `589b93d81196ae83e9add881fe5aa1aaf818bcd8c905daaf2a932927479614cf` |
| `docs/security/invariants.md` | 6585 | `9d2cf2193656d7321f9cbcfab594edc83cd510ffe100a2872a3f2e8b2c2c9752` |
| `fixtures/corpus/editing/split_py/manifest.json` | 85368 | `28a7820a36ed91a64ea1ec412060f524ed6ad23d46eaab44579c5fd67ecd5f03` |
| `python/substrate/fs/disk_fs.py` | 3987 | `4224f2d041759db10e9a662900202feb718c5ad2d422a2e0fe6cc58306425f20` |
| `python/substrate/fs/memory_fs.py` | 1120 | `887b37721ae93c72fa838fa2d408efe4f1b87ae046d208d6d1a88c87cc85d66b` |
| `python/substrate/fs/atomic_write.py` | 2814 | `6bee3cc1a23998916022e943a719168279ae59e20d088b01697ac794d326d6d0` |
| `python/modules/editing/shared/script_edits.py` | 2789 | `834b3dd3b2f311a9ca0db8cdedb71572ae93b76f4f271c1d59cda89dfcc9bc7f` |
| `python/modules/editing/shared/funnel.py` | 4386 | `dffa207086cd57e089e70180d3f1ce6eaabc86a6416aa448ce5c2cf8139c0711` |
| `python/modules/editing/write_apply/app.py` | 3830 | `254922e3e2f0bc0b9f1f687576fd0694b410620ba9594a5ff7081c8324a68fda` |
| `python/modules/editing/rollback/app.py` | 3642 | `bdc0ed1ec70363ee627eb89bf1773174f038b4353ec10fde625780b0879bd66f` |
| `python/modules/editing/rollback/recovery.py` | 4047 | `6bdb4605c2ba7b1593d4dbba385920808c0faa6b0526eff67d847cd456701da2` |
| `python/modules/editing/split_py/app.py` | 3773 | `56891adf069bbcbb219735bcba1d41353b1089eb38c0c4559c70b7f67d874a63` |
| `python/modules/editing/split_py/module.py` | 465 | `8cb1c975eef36dfe830357073f836c88b916b74e23411e49b8cbfd98e2506a70` |
| `python/modules/editing/split_py/ports.py` | 357 | `5b0d49b52d5c3675dd81d7665ef5e9a3fd1502dd09921199357dac54ca6b9ef2` |
| `python/modules/editing/split_py/tools.py` | 235 | `cdc5f6e6d674c211daa10aa100428c8a8bd2a295d2a8ac8cf1ad4bd477170496` |
| ADR-0015, `domain/apply.py`, `tools_split_apply.py`, apply-flow и новые C.20 tests/corpus/card | — | `absent` |

#### Что и куда пишет

| Действие | Step | Исполнитель | Компенсация |
|---|---|---|---|
| новый `.py`-модуль | `create`, `expected_hash=""` | только `editing.write_apply` под lock после `APPLYING` | `compensates="delete"`, удаление в обратном порядке |
| фасад вместо донора | существующий `script_edit` с полной заменой текста | тот же `write_apply` после всех preflight-проверок | сырой backup из `store/backups.py` |
| общий delete-шаг | `delete`, точный raw `expected_hash` | тот же `write_apply`; только файл | восстановление сырого backup |
| rollback/recovery | по durable receipt | общий `funnel.restore` | created-файл удаляется, заменённый/удалённый восстанавливается побайтово |

Прямых `open(..., "w")`/`os.remove` из `split_py` нет. `scene_ops` и
`project_ops` новых операций не получают. Если потребуется ещё один
существующий путь, его pre-SHA сначала добавляется сюда; иначе действует
стоп-условие C.20.

**Следующее действие:** добавить invariant/test SEC-21, снять actual-native
корпус 097+ и зафиксировать красные тесты до production-реализации.

#### C.20 corpus и red до production

Старый `apply_prepared_split:718-767` запущен на изолированных копиях:
9 actual-native сценариев 097–105; внешний capture 31701 B, sha256
`921c9184c83a9c338a5364cf32a2660b0d924268e300aa3147c9c462be6b378d`.
Добавлены boundary-сценарии 106–108: сбой второго эффекта с reverse rollback,
отказ delete каталога, non-`res://`. Cases 001–096 и их manifest hashes не
менялись. Зафиксировано native-расхождение, которое постановка явно закрывает:
старый код проверял facade после создания модулей, а C.20 требует полный
preflight и нулевой частичный эффект; BOM/CRLF donor в порте сохраняются.

Red-команда новых C.20-пинов: 25 tests, 22 failed, 0 errors, 0 skipped,
3 passed; JUnit `%LOCALAPPDATA%/Temp/opencode/c20-red.xml`, 27611 B,
sha256 `e4b5621054d85bc1479b0daef0bcc1d21bb920edf42fde5af9ec9f4b93f13198`.
Красные причины отдельно доказывают отсутствующие memory/disk операции,
явный op-dispatch, create/delete funnel+recovery, ToolSpec/registry,
`split_apply`, protected `plugin.cfg` и unknown-op refusal.

**Следующее действие:** минимальная production-реализация адаптеров и общего
funnel, затем `domain/apply.py` + apply orchestration; после каждого блока
старые write-тесты и новые пины должны быть зелёными без правки старых тестов.

#### C.20 production и focused green

Реализованы три явных файловых op в общей воронке: прежний `script_edit`,
exclusive `create` с absent-sentinel `expected_hash=""` и file-only `delete`
с точным raw SHA. Disk/memory adapters и atomic writer получили именованные
операции; WAL пишет receipt после каждого эффекта, reverse rollback/recovery
удаляет только неизменённый compensated create и восстанавливает delete из
сырого backup. Collision recovery не перезаписывает внешнее изменение.

`split_apply` принимает строго `{path, plan}`, заново строит скрытые тексты,
до WAL компилирует все модули и facade, сравнивает public projection и
нормализованный donor hash, проверяет отсутствие всех create targets, затем
пишет `PREPARED` и вызывает только общий `write_apply`. Публичный успех имеет
ровно native-поля `donor/written/moved/facade_lines` плюс `receipts`; donor
BOM/CRLF сохраняются. Corpus 097–108 приведён к форме
`prepare split_plan → split_apply(path, $prepare.result)`.

Focused C.20 green: 30 passed; JUnit
`%LOCALAPPDATA%/Temp/opencode/c20-green-focused.xml`, 4301 B, sha256
`1561ea4ab602d511573353f0a42e1ce2be845f6d7365eae2dbf31c3a797669af`.
Совместный новый+старый write-прогон: 76 passed. `lint_arch`: 547 green;
`check_limits`: 547 green, только ожидаемое предупреждение о 11 элементах
`editing/split_py` (ни один файл/`app.py` лимит не нарушает).

**Следующее действие:** сгенерировать и проверить 26-й capability artifact,
затем full non-live/snapshots/selfcheck/security/live и финальная фиксация docs.

#### C.20 final verification (готово к аудиту, не принято)

Финальный прогон после collision-hardening `create` recovery:

- red: 25 tests, 22 failed / 3 passed, JUnit 27611 B,
  sha256 `e4b5621054d85bc1479b0daef0bcc1d21bb920edf42fde5af9ec9f4b93f13198`;
- focused green: 30/30, JUnit 4301 B,
  sha256 `1561ea4ab602d511573353f0a42e1ce2be845f6d7365eae2dbf31c3a797669af`;
- полный non-live: **4281 passed**, 0 failed/errors/skipped (+32 к C.19),
  JUnit 627211 B,
  sha256 `f97f615c1f1752e688a31760b5efe376cac060464b865d186be7b1ae30d0e078`;
- snapshots: **832/832** = прежние 820 + 12 новых C.20;
  `editing.split_py` отдельно 108/108;
- `selfcheck editing.split_py`: verdict ok, unit **583**, corpus **107**;
  107 здесь ожидаемы: card 107 проверяет общий `write_apply`, а полный
  split_py-directory snapshot исполняет все 108;
- все 44 selfcheck: прежняя матрица **24 ok + 20 blocked**; сохранены
  `split_gd 625/102`, `class_api 128/26`, `node_info 247/65`, `tree 116/40`;
- contract **26**, layers **547**, limits **547** (одно информационное
  предупреждение: в split_py 11 элементов), security green включая SEC-20/21;
- Godot live: **3 passed**, 0 skipped/failures; JUnit 640 B,
  sha256 `3a8beb7b464a105cb8f5fc1a01858d0f95a44bd32b07297c4af9b59c426a0174`.

Mutation/projection-пины закрыты: M1 occupied create, M2 отсутствующий donor
hash, M3 отдельная prevalidation второго module и facade, M4 create/delete
reverse compensation и injected second-effect failure. P1 occupied target не
трогает donor; P2 повторный apply не меняет дерево; P3 финальное дерево без
temp/UID/report debris.

Live восстановлен точно: внешний `project.godot` снова 335 B, sha256
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`;
удалены ровно 162 созданных Godot UID, итог 84 `.gd.uid`; baseline addon-файлы
и каталоги совпали побайтово. Все 44 `reports/selfcheck/*.json` возвращены к
pre-C.20 SHA. От внешнего baseline `03cf2de8…8912`: 3238 файлов, 796 каталогов,
84 UID; +26 ожидаемых файлов, 33 разрешённых изменения, 0 удалений; corpus
001–096, `tools/selfcheck.py`, `editor/**` и `_audit-handoff.md` не менялись.
WORKLOG до каждого binary append сохранён как точный prefix, исторических CRLF
по-прежнему 4479.

Финальные production SHA-256:

| path | bytes | sha256 |
|---|---:|---|
| `contract/capabilities/split_apply.json` | 6605 | `6d6a1c77d0b03367c1b83d7961f7acec4a70056b821a13a13113809ed179fa9a` |
| `python/modules/editing/split_py/app.py` | 3874 | `0a26482ae7315e81505b0ed252ba548b9a0b96477ac3ed7210e34960fb350de8` |
| `python/modules/editing/split_py/apply_flow.py` | 3657 | `cbf2d3e6fc4d650d922d711473e23708eacd9f8bf93ce5885ab26a1b3d29cb05` |
| `python/modules/editing/split_py/domain/apply.py` | 3868 | `f3c20cf6cdc431df0d96b1622d8783c6674ff75ae7a842a5653727f8f958288b` |
| `python/modules/editing/split_py/module.py` | 535 | `ce45918882ac157b13afe780370a3b3bb086f1dcc08ef98811f6499cce4005b0` |
| `python/modules/editing/split_py/ports.py` | 481 | `87f6a281956022eec907841254da04b04d77fe8f7def98942fd60a17cc650328` |
| `python/modules/editing/split_py/tools.py` | 302 | `428062d718c77c1cf3eaa46bc7a6faa9d54b11b1d9a6871c546f0d1dbe96b309` |
| `python/modules/editing/split_py/tools_split_apply.py` | 1672 | `1d54eb37d292a3bd109f9614563d1a59c595d1465e14b33092753d5e2ea2b957` |
| `python/modules/editing/shared/funnel.py` | 8331 | `60f597a414bd0759d6c24aee1e77bdbdddfcebfeea0b8e02d60517aa735e9f78` |
| `python/modules/editing/shared/script_edits.py` | 3698 | `0edc1b3fb9bc4342c976b4c7313dad1fdf9b0ce110d231aa24063473c448206c` |
| `python/modules/editing/write_apply/app.py` | 3038 | `d615c3d744b60ae01be60aa37c46dad48f745c0a5a48aee12e7f3a2b07e80878` |
| `python/modules/editing/rollback/app.py` | 3921 | `eb96056618310abf3329715c869331787ef6b67f4f3b2e320539c42f36ede85a` |
| `python/modules/editing/rollback/recovery.py` | 4102 | `88e0ef976ac30f38d5b4bcf24fd1a0efa46847640ba97c508e4ecd60f3ae3810` |
| `python/substrate/fs/atomic_write.py` | 4075 | `85dc6c184c5f37ee094e7850c3e7a21641a9d2ea7ea0d257c835cdd54f5d9a51` |
| `python/substrate/fs/disk_fs.py` | 5021 | `e973bd522c40a4fd2e3728bd21e1cff7c3e1b194e7f1f40f14a560d2edcc7903` |
| `python/substrate/fs/memory_fs.py` | 1798 | `2a9f8203562738a734bea4f783276d9fa4c0c3b5e38bdf0f83ca41f896cb14f6` |

ADR-0015 остаётся `proposed`: принять её и C.20 может только независимый
аудитор. Stage `editing.split_py` остаётся 7 и статус принятого C.17/C.18 не
использован для самопринятия нового write-среза.

**Следующее действие:** независимый аудит C.20 по red/green, corpus097–108,
production SHA, WAL/rollback/recovery и live-restoration; до вердикта не менять
ADR-0015 на accepted и не помечать C.20 принятым/ported.

### C.20 принят аудитом 2026-11-01 (сессия 76)

Аудитор перепроверил независимо: non-live 4281/0/0/0 (своя junit), selector
64/0/0/0, snapshot 832/0, selfcheck этой механики 583 unit + 107 corpus (verdict
ok; отчёт возвращён байт-в-байт к сданному SHA), contract 26, layers 547,
limits 547 с одним информационным предупреждением, security ok (SEC-21), live 3
passed за 38.0 s при временно включённом `[editor_plugins]` с возвратом
`project.godot` (335 B, `958b3a92…`) и уборкой ровно 162 созданных `.gd.uid`;
дерево до и после — 3231/790/83, corpus 001–096 байт-в-байт, `tools/selfcheck.py`
не менялся.

Транзакционная часть проверена не тестами портера, а отдельным probe на портах
воронки: abort после create → созданное удалено, донор не тронут, WAL
`PREPARED→APPLYING→RECEIPT→ROLLING_BACK→RESTORED→ROLLED_BACK`; recovery после
«падения» откатывает созданное; чужая правка созданного файла →
`conflict/post_state_mismatch`, файл не удаляется; forward `delete`
восстанавливается байт-в-байт (файл с CRLF); `create` с непустым `expected_hash`
и неизвестный `op` → `invalid_input`; удаление каталога запрещено. Мутации
«снять `verify_absent`» и «`create` заменить на `write_raw`» дают по 1 красному
из 21, `funnel.py` возвращён байт-в-байт (`60f597a4…`).

Замечания к записи (код принят, ADR-0015 активирован):

1. **F1.** Сданный `reports/selfcheck/editing.split_py.json` — до-C.20
   (`module: editing.split_py (split_scan, split_plan)`, `layers 544`, unit 568,
   corpus 96). Машинный вердикт среза существует только в этом листе. Либо
   сдавать свежий отчёт этой механики, либо одной строкой в чеклисте объявить
   «отчёты — canonical pre-slice».
2. **F2.** `docs/tests-map.md` не пополнен: нет строк для
   `tests/py/contract/test_split_apply_contract.py`,
   `tests/py/integration/test_create_delete_funnel.py`,
   `tests/py/integration/test_split_apply.py`,
   `tests/py/security/test_split_apply_write.py`,
   `tests/py/formats/test_file_system_create_delete.py`,
   `tests/py/formats/test_script_edit_ops.py`,
   `tests/py/tools/test_snapshot_diff_split_apply.py`.
3. **F3.** `fixtures/corpus/context/gather/001-all-sections.json` переформатирован
   (компакт → pretty-print, 56 → 94 строки, sha кейса в manifest изменился) —
   правка чужого корпуса вне среза, хоть и семантически верная (`count 24→25`,
   `split_apply` в списке).

Строка `editing.split_py` и этап 7 не менялись; C.21 не назначен.

### F1–F3: исправления записи в preflight C.21 (2026-11-02)

Приёмка C.20/этап7 и accepted ADR-0015 не переоцениваются. Досье:
`%LOCALAPPDATA%/Temp/opencode/c21-paths-preview-20261101/`.

- **F1:** настоящий `python -B tools/selfcheck.py editing.split_py`, verdict ok,
  split_scan/split_plan/split_apply,583 unit/107 corpus/layers547,
  contract26/security0/limits547+1. Свежий canonical report SHA256
  `ced9dc3457bf8d08954ef9cc4dcaa64b1d7238e21092b9918ce165e34c554d00`;
  остальные43reports byte-exact, длительности JSON не редактировались.
- **F2:** append-only семь строк test-файлов в tests-map. Реальный collect32
  =executed32=passed32,0fail/error/skip; счётчики3/6/12/3/3/3/2 в порядке
  списка замечания. JUnit `f2-tests.xml` SHA256
  `aa05bb69fe6fc2e941ce8a58987af8f29bc949988f2dd4ae026dc23d4cecfb02`.
- **F3:** compact layout восстановлен по внешнему исходному byte-backup C.18,
  сохранены count25/split_apply/effects write и все JSON-данные C.20.
  Теперь57LF строк вместо pretty94: прежний compact56 плюс эффект split_apply.
  Case SHA256 `2345bffa85f5650c3547d69f8b0bd85f6e7e0a3852ae8f43f9f7fc6a7ef06013`,
  изменён только его SHA в manifest. Snapshot832/0, contract26/0,
  layers547/0, limits547/1 (прежнее информационное), security0.

Следующее действие C.21 — ответ пользователя на семь actual-native пунктов
в листе paths_preview; read-only preview пока skeleton/stage0, production
не начат. Этот шаг не объявляется новой приёмкой или завершением C.21.
