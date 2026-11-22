# scene_model.node_delete — read-only план удаления поддерева

**Статус:** этап 7 — ported, **принято аудитом 2026-10-30 (сессия 58)**: 27/27 кейсов пересняты мной с
эталона `prepare_node_deletion` (полный словарь, `deleted_nodes` и `warnings` в порядке эталона,
Base64-байты, diff; 7 отказов — буквально); свои прогоны 2014 non-live + 3 live (= collect-only),
selfcheck 131/27, контракт 17, snapshot 404/0, layers/limits 481/0; мутации M3 5 / M4 4 / M6 4 / M7 4 red
(сканирование скриптов удаляемых узлов, съедание `\r\n`, потомки, `%Unique`), подложки P1 (20 red в
контрактных) / P2 3 / P3 1 — всё восстановлено побайтово. Замечание без блокировки: ссылки на удаляемый
узел из скриптов **других** сцен не предупреждаются — так же ведёт себя эталон.
**Обновлено:** 2026-10-30

## Цель

`node_delete_preview({path,node,cleanup_code=true})` возвращает план удаления
узлов/связей/анимаций из сцены и предупреждения о ссылках в остающихся скриптах.
Скрипты не переписываются; cleanup_code=false выключает warnings. Никаких apply,
undo/истории/моста/WAL или записи проекта. Основание — C.7.

## Старый код

Эталон read-only `node_refactor.py` 46881B/SHA256
`2d708a384177fa0a8d4636f3f2dd373508ee316216319edf7d793255d8918a29`, commit
`ba0535d4dec43c32750e601a6ca86e377abc6af3`.

| Якорь | Поведение | Новая граница |
|---|---|---|
| `prepare_node_deletion:800-833` | Lookup/root refusal/target+scene-order descendants/unique names | Единственный shared lookup, pure domain |
| `:840-866` | Header→body_end, connection span, animation full_span +following CR/LF | Append-only format operations; no reconstruction |
| `:870-887` | Reverse offsets/scene file/count/BOM | Accepted patch +single diff/Base64 |
| `:889-920` | Exclude deleted nodes before script grouping; relative target paths | Pure domain, app read port |
| `:922-953` | Nonempty/noncomment lines, literal regex facts, one warning/line | Только gdscript/node_paths facts; домен формирует messages |
| `:955-966` | Full result/deleted_nodes/files/warnings order | Exact projection only absolute/scene_res omitted |
| `apply_prepared_node_refactor:969` | Запись/undo | Вне среза |

## Старые тесты

`test_node_refactor.py` прочитан целиком: cases `:248-298` subtree +warnings,
неизменные scripts, обе стороны connections и tracks; apply/rollback вне C.7.
Tests-map строка79: corpus/historical node_rename; судьбы связанных сценовых
строк56/64/80/81/113/114/121/122/130 заданы. Не reasssign/не закрывать старый
flow/live целиком. Только cases, без legacy test imports/кода.

## Корпус

Снят actual-old prepare_node_deletion: **27 cases/137 input byte pins**, project
SHA before/after27/27. Единый capture удалён до tests/code. Leaf/subtree/root refusal,
connections/from/to, %Unique tracks/warnings, skipped deleted-script groups,
shared removed+remaining script, cleanupfalse/comments/BOM/CRLF/loneCR/missing
script/path/tres/access; сравнение full plans/Base64/ordered lists/literal messages.

## Спецификация

Read/idempotent/cheap; strict result action=delete_node,scene,target_node,
target_node_path,deleted_nodes,files,reference_count,affected_paths,warnings.
Deleted_nodes непуст, цель первая/остальные scene-order; warnings file,line≥1,
code,message. Files только сцена; scripts не меняются, count без warnings.
Base64 bytes; native structured diff; errors invalid_input/not_found/denied;
`.tscn/.scn`, READ_TEXT_MAX_BYTES4MiB. IO только app/consumer ports; domain без
IO/re/eval/exec; app≤80/tools≤150/files≤400. Новых live tests нет.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-30 | Единственный lookup/patch/diff, без копии чужого domain | R-04/R-11 и §4 |
| 2026-10-30 | Cleanup собирает warnings, не исправляет scripts | Actual889–953, без улучшений |
| 2026-10-30 | Все following CR/LF spans сохраняют native removal | M6 обязательна на permanent tests |
| 2026-10-30 | Одна warning на line, порядок scripts/lines, deleted-script exclusion | Full dictionaries/lists equality, M8/M9 |
| 2026-10-30 | Base64 и только2 исключённых host fields как C.6 | §4 |
| 2026-10-30 | Public diff facade/callable bind и5inventory+context scope требуют разрешения C.7 | Frozen private diff, C.6-only permission не переиспользуется |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-30 | 1. лист | Mandatory docs/latest54–56/actual source/legacy cases прочитаны; baseline1684 exact; production unchanged |
| 2026-10-30 | 1. native selfcheck | exit 2, verdict blocked; module/unit/corpus not_implemented, layers/limits472/0, contract15/0, securityok |
| 2026-10-30 | 1. scope | Пользователь разрешил public diff/bind и точечные inventory/context поля, без расширения accepted scope |
| 2026-10-30 | 2. корпус | Actual-old27 cases/137 input pins/27 project SHA proofs; capture удалён до tests/code |
| 2026-10-30 | 3. specs/red | Оба ToolSpec/9 новых test files:329exact IDs;243failed/86passed/0error/skip; planner/app ещё stubs |
| 2026-10-30 | 4. код + native selfcheck | exit0/ok;131passed, corpus27/0; layers/limits481/0, contracts17/0, securityok. Общий C.7 329/329 exact IDs |
| 2026-10-30 | 5. дифференциал/мутации | После восстановления native131/corpus27/0 ok; 13 killed, M5 эквивалент;14/14 byte/SHA/EOL restored. Non-live2013/2013 exact IDs,76files,0fail/error/skip |
| 2026-10-30 | 6. финальная исправленная версия | Native131/corpus27ok; snapshot404/0, CLI16/16+SHA, existing live3/3 exact; scope12/12 bytes/SHA/EOL, debris0 |
| 2026-10-30 | 7. собственный итог | ported/read-only, готово к независимому аудиту; независимое принятие не заявлено |
| 2026-10-30 | 5. fresh import correction | Permanent red1/1 → helper без обратного facade import; parser333lines прежний. Non-live2014/2014 exact/76files, C.7 330; M5/M6/M7 final byte reruns, MC1/330, restores ok |

## Проверки этапов1–3 (история)

Свои nonlive1684/67files exact-ID equality, contracts15/snapshot345/static472/
securitygreen. Old622 SHA/HEAD/diff/две чужие logs неизменны. Census1550/27prompts/
16named sheets (17 с README), debris0; подробности и SHA в соседнем reparent
листе и `%TEMP%/opencode/node-c7-*`. Own live ещё не запускался, auditor3live —
только база. `python -B tools/selfcheck.py scene_model.node_delete` → **exit 2,
blocked**: нет MODULE (R-05), тестов и корпуса; module/unit/corpus not_implemented.
Layers/limits472/0, contract15/0, securityok; это не green. Отчёт
`reports/selfcheck/scene_model.node_delete.json`, stdout/stderr
`%TEMP%/opencode/node-c7-delete-stage1.*`.

## Финальные проверки этапа6

Native на corrected format version: **exit0/verdict ok,131passed,corpus27/0**;
reparent155/corpus32ok. Non-live **2014/2014 exact IDs/76files**, C.7+formats330,
0failure/error/skip. Disjoint snapshot **404/0**, args-file CLI **16/16** full
native result/literal refusal + project SHA unchanged. Existing live **3/3
exact IDs**, JUnit22.625s, повторены после import fix.111 generated UID удалены
по exact SHA/bytes/raw-backed списку, все1931 pre-live SHA восстановлены;
8 legitimate fixture UID сохранены, debris0, project.godot прежний.
Gates17contracts/481layers/481limits/securityok. Approved scope12/12 reverse
bytes/SHA/EOL; old15 generated cards+template и остальной baseline frozen.
Proofs: `node-c7-final2-exact-proof.json`, `node-c7-final2-snapshot-proof.json`,
`node-c7-final2-probes-proof.json`, `node-c7-live-final-proof.json`,
`node-c7-live-final-clean-proof.json`, `node-c7-final-prestatus-scope.json`
в `%TEMP%/opencode/`; native stdout `node-c7-delete-final.stdout`, report
`reports/selfcheck/scene_model.node_delete.json`. Ошибки reverse wrapper quote/
spacing/template-count исправлены без правки accepted files или ослабления
raw equality. Скрипты по-прежнему не patches, warnings не входят в count.

## Следующее действие

Независимому аудитору запустить `python -B tools/selfcheck.py scene_model.node_delete` на submitted version.

## Согласованный узкий scope

Private diff reuse против R-11/frozen C.6; нужны public facade/port/default bind
и точечный C.7 состав инструментов, не разрешение «менять принятое» вообще.
Точный список файлов и полей — согласованный scope в листе
`scene_model.node_reparent.md`. Пользователь разрешил оба пункта через question
2026-10-30; accepted core/diff/settings/shared и остальная композиция заморожены.

Native этап2 **blocked/exit2**: MODULE/unit отсутствуют, корпус есть, но фильтр
без манифеста не выбирает tool cases. Этап3 **fail/exit1**: unit90failed/2passed
(92 с integration), module/corpusnot_implemented; layers fail: новые публичные
test imports ещё без requires в stub manifests, limits475/0, contract15/0,
securityok. Это red до кода, не успех; streams `node-c7-delete-stage{2,3}.*`.
Permanent red329/329 exact IDs/243failed/86passed/0errors/skip обоих C.7 +formats
записан в `node-c7-red-all-proof.json`; единый capture отсутствует.

Этап4 actual **native exit0/ok:131passed, corpus27/0**, contracts17/0,
layers/limits481/0, securityok (`node-c7-delete-stage4.stdout/.stderr`, настоящий
report). Оба+formats **329/329 exact IDs,0fail/error/skip**. Scripts остаются
неизменными, grouping/read исключают deleted owners до сканирования warnings;
cleanupfalse не читает scripts. Единственные format span operations/patch,
consumer callable diff port, без lint/writer/editor dependency.
Test-only composition injection исправила собственные cross-feature imports;
frozen lint не учитывает requires, прежняя формулировка была гипотезой, не фактом.
Authorized scope reverse12/12 bytes/SHA/EOL, старые15 contracts и остальные
baseline файлы неизменны (`node-c7-stage4-scope.json`). Детали точечного EOL
restore и timeout полного snapshot — в соседнем листе; timeout не green.
