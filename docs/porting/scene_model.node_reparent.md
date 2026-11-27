# scene_model.node_reparent — read-only план переноса узла

**Статус:** этап 7 — ported, **принято аудитом 2026-10-30 (сессия 58)**: 32/32 кейса пересняты мной с
эталона `prepare_node_reparent` (`build_agent.call` против `prepare_node_reparent`, полный словарь,
Base64-байты, diff-строки, порядок файлов; 14 отказов — буквально, причём `denied` вместо
`invalid_input` у защищённой сцены совпадает с корпусом); свои прогоны 2014 non-live + 3 live
(= collect-only, 76 файлов), selfcheck 155/32, контракт 17, snapshot 404/0, layers/limits 481/0;
мутации M2 2 / M3 5 / M4 4 / M6 4 / M7 4 / M8 3 red, M1 (вставка `parent=`) и M5 (доп. пара от корня)
эквивалентны — доказано: не-корневых узлов без `parent=` нет ни в одном из 225 `.tscn` фикстур, а
дубль пары гасит дедуп; подложки P1 (20 red в контрактных) / P2 3 / P3 1, всё восстановлено побайтово.
**Обновлено:** 2026-10-30

## Цель

`node_reparent_preview({path,node,new_parent,update_scripts=true})` возвращает
полный план правок сцены и прикреплённых скриптов. Не пишет проект/WAL, не
применяет план, не вызывает мост, не меняет undo/историю. Основание — C.7,
`docs/porting/_start-prompt.node_reparent.md`.

## Старый код

Read-only reference: `тест-плагина-ии/addons/Godot_agent/godot_agent`, HEAD
`ba0535d4dec43c32750e601a6ca86e377abc6af3`. `node_refactor.py`: 46881 B,
SHA256 `2d708a384177fa0a8d4636f3f2dd373508ee316216319edf7d793255d8918a29`.

| Файл / якорь | Поведение | Новая граница |
|---|---|---|
| `node_refactor.py:542-588` | Lookup обоих узлов, root/self/descendant/current-parent/collision отказы | Единственный shared/node_path; чистый preflight |
| `:594-648`, `:652-669` | Заголовок/дети/connection/animation, обратные offsets, scene всегда первая | Append-only formats; accepted structure/patch; byte/BOM/EOL |
| `:671-729` | Script groups, moved subtree, перенос хвостов, пары, stable dedup | Чистый домен; app читает портом |
| `:732-766` | `$` кавычки для `..` и nonidentifier; quoted calls; lint refusal | Append-only gdscript/node_paths + существующий gd_lint port |
| `:768-797` | Script files/count/full result | Base64 projection; единый diff, не копия |
| `project_tools.py:1854-1917` | Structured diff | Existing C.6 implementation; законный доступ требует scope |
| `apply_prepared_node_refactor:969` | Apply/history/undo | Вне C.7 |

## Старые тесты

`tests/test_node_refactor.py` прочитан целиком; cases `:159-212` (переезд
поддерева) и `:214-246` (upward quoted `$`) берутся как входы, не как код.
Строка79 `docs/tests-map.md` исторически относится к node_rename, судьба corpus;
не переassign и не объявлять apply/rollback/live перенесёнными. Связанные строки
56/64/80/81/113/114/121/122/130 имеют судьбу corpus; C.7 закрывает только планы,
не external moves/resource actions/editor interception. Tests-map не меняется.

## Корпус

Снят actual-old `python -B` единым disposable capture: **32 cases/162 input
pins**, в `fixtures/corpus/scene_model/node_reparent/`. Capture удалён до
permanent red tests/production. Full dictionaries/Base64/diff/files order/literal
refusals; source/input/case SHA+bytes, project SHA before/after32/32 в manifest.

## Спецификация

ToolSpec read/idempotent/cheap; строгие args/result без text/absolute/scene_res.
Result: action=reparent_node,scene,old_path,new_path,new_parent,target_node,
target_node_path,files,reference_count,affected_paths. Target_node — имя,
target_node_path — старый путь, new_parent — resolved path с корнем `.`.
Файлы: patch_file/path/before_hash/before_bytes/after_bytes/diff/occurrences;
байты — lossless Base64, diff native context3/max600. Типизированные
invalid_input/not_found/denied; `.tscn/.scn`, shared READ_TEXT_MAX_BYTES=4MiB.
Без scripts_only/previous_name, новых live tests и write/exec портов.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-30 | Проекция ровно C.6, исключает только scene_res/absolute | §4, lossless bytes |
| 2026-10-30 | Root-to-child не успешный кейс; M5 недостижим через native prepare | Root guard:562-563 раньше header insertion:599-601; честный эквивалент, без снятия guard |
| 2026-10-30 | Этапы собственных шагов по R-19, не независимое принятие | §1/§8 требуют этап1/7 вопреки вводной §0 |
| 2026-10-30 | Предлагается public diff reexport + callable consumer-port/default bind | Нельзя чужой domain import или копия; frozen C.6 core/diff остаются byte-identical |
| 2026-10-30 | Нужен отдельный C.7 composition scope | Только5 inventory lists +context001 count14→16/two read names/hash; C.6 разрешение не распространяется |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-30 | 1. лист | Обязательные документы, последние54–56, actual542–966 и старый unit прочитаны; production stubs неизменны |
| 2026-10-30 | 1. native selfcheck | exit 2, verdict blocked: module/unit/corpus not_implemented; layers/limits472/0, contract15/0, securityok |
| 2026-10-30 | 1. scope | Пользователь разрешил оба узких scope через question; список ниже, frozen C.6 сохраняется |
| 2026-10-30 | 2. корпус | Actual-old32 cases/162 input byte pins/32 project SHA proofs; capture удалён до tests/code |
| 2026-10-30 | 3. спецификация + red | Оба ToolSpec и9 новых test files:329 executed=329 exact collected;243failed/86passed/0error/skip. Planner/app stubs ещё неизменны |
| 2026-10-30 | 4. код + native selfcheck | exit0/ok;155passed, corpus32/0; layers/limits481/0, contracts17/0, securityok. Общий C.7 329/329 exact IDs |
| 2026-10-30 | 5. дифференциал/мутации | После восстановления native155/corpus32/0 ok; 13 killed, M5 эквивалент;14/14 byte/SHA/EOL restored. Non-live2013/2013 exact IDs,76files,0fail/error/skip |
| 2026-10-30 | 6. финальная исправленная версия | Native155/corpus32ok; snapshot404/0, CLI16/16+SHA, existing live3/3 exact; scope12/12 bytes/SHA/EOL, debris0 |
| 2026-10-30 | 7. собственный итог | ported/read-only, готово к независимому аудиту; независимое принятие не заявлено |
| 2026-10-30 | 5. fresh import correction | Permanent red1/1 → удалён обратный format import, sole attribute rewrite передаётся фасадом; accepted333lines неизменны. Non-live2014/2014 exact/76files, C.7 330; M5/M6/M7 повторены на final bytes, MC1/330, restores ok |

## Проверки этапов1–3 (история)

Независимая база: nonlive **1684=exact collected1684/67files**, 680+588+356+60,
no fail/error/skip; contracts15/snapshots345/0/static472/0/securityok. Old622 SHA,
HEADba0535d4, diffempty, ровно2 прежних чужих logs. Own live baseline не запускался;
аудитная база3live из WORKLOG56, в финале будут свои3 существующих smoke tests.
Tree1550/debris0, **27 prompts**,16named sheets (17 с README); prompt ошибочно
пишет26 и называет17 листами механик. После двух новых named sheets18,
19 вместе с README; методику не подгонять. Node_paths hash совпал, строк21, не19.
Все §0 SHA совпали. Evidence `%TEMP%/opencode/node-c7-*`.

`python -B tools/selfcheck.py scene_model.node_reparent` → **exit 2, blocked**.
Module: «нет MODULE (R-05)»; unit: «тестов модуля нет»; corpus: «нет корпуса
механики», все три not_implemented. Layers/limits472/0, contract15/0, securityok.
Это реальный вердикт заготовки, не успех. Отчёт
`reports/selfcheck/scene_model.node_reparent.json`, stdout/stderr
`%TEMP%/opencode/node-c7-reparent-stage1.*`.

## Финальные проверки этапа6

После fresh-import correction: native `scene_model.node_reparent` **exit0,
verdict ok,155passed,corpus32/0**; delete131/corpus27ok. Non-live **2014/2014
exact IDs/76files**, C.7 включая formats330; failures/errors/skips0. Native
snapshot **404/0**,15 owners/16 leaf folders; CLI **16/16** full native oracle
либо literal refusals, только args-file, project SHA unchanged16/16.
Три прежних live IDs повторены на исправленных bytes:3/3 exact, JUnit22.625s;
добавились только111 UID, byte-backed exact cleanup вернул все1931 pre-live
SHA/bytes. Прежние8 fixture UID сохранены, мусор0.

Final gates: contracts17/0, layers/limits481/0, securityok. Scope **12/12
reverse bytes/SHA/EOL**, accepted parser333lines, C.6 core/diff/settings и
остальной baseline прежние;15 generated cards + static template неизменны.
Неудачные final scope wrappers неверно предположили indentation/quote/spacing
и включили static template в generated count; это read-only verifier ошибки,
не source drift. Исправленный reverser требует raw equality каждого backup.
Proofs в `%TEMP%/opencode/`: `node-c7-final-prestatus-scope.json`,
`node-c7-final2-exact-proof.json`, `node-c7-final2-snapshot-proof.json`,
`node-c7-final2-probes-proof.json`, `node-c7-live-final-proof.json`,
`node-c7-live-final-clean-proof.json`, `node-c7-final-mutation-proof.json`.
Actual stdout native: `node-c7-reparent-final.stdout`; report:
`reports/selfcheck/scene_model.node_reparent.json`.

## Следующее действие

Независимому аудитору запустить `python -B tools/selfcheck.py scene_model.node_reparent` на submitted version.

## Согласованный узкий scope (разрешён пользователем 2026-10-30)

Единственный diff в private node_rename/domain; нужны public facade и callable
bind либо другое разрешённое решение без копирования и обхода R-11.

Запрашиваемые изменения вне собственных C.7 модулей и append-only formats:
public reexport в `python/modules/scene_model/node_rename/__init__.py`;
import/bind callable diff в `python/runtime/bootstrap.py` (как gd_lint).
Заморожены C.6 core/diff/settings, shared lookup и остальной bootstrap.
Composition только names/count/effects в `tests/py/contract/test_functions_contract.py`,
`tests/py/contract/test_usages_contract.py`, `tests/py/integration/test_gd_lint.py`,
`tests/py/integration/test_scene.py`, `tests/py/integration/test_node.py`;
в `fixtures/corpus/context/gather/001-all-sections.json` только tools count14→16,
два новых read names/effects; в соседнем manifest только hash этой case.
Байтовые бэкапы, reverse SHA и EOL proof обязательны. Пользователь через question
разрешил оба пункта; это не разрешение менять остальное принятое. Следующий
шаг — единый disposable actual-old capture обоих корпусов до permanent red
tests/code. Planning production ещё не реализован. Этап2 native blocked: корпус
есть, но без MODULE штатный фильтр не выбирает cases. Этап3 native **exit1/fail**:
unit109failed/2passed (111 с integration), module/corpus not_implemented; layers
fail по отсутствующим requires публичных lint/diff, limits475/0, contract15/0,
securityok. Requires будут описаны в новых ModuleSpec. Streams
`%TEMP%/opencode/node-c7-*-stage{2,3}.*`. Red exact proof
`node-c7-red-all-proof.json`/JUnit329/329; первая collect-команда дала file counts
из двойного -q; corrected addopts= rerun дал точные IDs.

Этап4: sole diff доступен через обычный public module facade и default callable
bind; consumer ports, pure planner и app без writer/editor. Formats append-only,
accepted star exports закрыты. **Native exit0/ok: unit155, corpus32/0**, contract17,
layers/limits481/0, securityok; `node-c7-reparent-stage4.stdout/.stderr` и настоящий
report. Общий permanent набор **329/329 exact IDs,0fail/error/skip**, proof
`node-c7-stage4-green-proof.json`. Исправлены только свои тесты: effects берутся
из context, реальные callable ports инъецирует новый test-only composition fixture.
Ранее requires ошибочно назывались решением lint: frozen checker не учитывает
requires; direct provider imports из module-tests убраны, checker не менялся.
Первый facade ImportFrom давал coarse package-cycle; обычный module import+alias
его устранил без dynamic imports/копий. Core/diff/settings C.6 неизменны.
Reverse **12/12 byte/SHA/EOL**, прежние15 cards byte-identical, все прочие
baseline SHA неизменны (`node-c7-stage4-scope.json`). Patch изменил EOL только
своих строк: восстановлены CRLF context001[20,21,29–32], manifest16, inventory
143/157 и единственный terminal LF bootstrap. Новый зависимый case SHA
`285d0ac939c66f575ed170a702a332538081c5972cf8e9be6e647bc6c8d97142`.
Полный snapshot достиг timeout27s; не считается green. Будет штатный disjoint
прогон по module_id без изменения checker, чтобы каждая команда была ≤30s.

Этап5: submitted M1–M9/P1–P3 по одной, original byte-copy backups до patch,
finally restore после каждого. Failed/329: M1=8, M2=52, M3=4, M4=4, M5=0,
M6=82, M7=78, M8=54, M9=59; P1R=1, P1D=1, P2=4, P3pathlib=1, P3re=1.
Все exact329 IDs/errors0/skips0; **14/14 raw bytes/SHA/EOL restored**.
M5 эквивалентен: missing-parent insertion недостижима через native prepare при
сохранённом root guard; успешный root-to-child и red не выдуманы. Native P1
gen_contract --check fail отдельно по каждой карте; P2 oracle warning corruption
ловят full parity и manifest pins. P3 AST ловит pathlib/re; frozen lint ловит
pathlib, но честно не ловит re. Первый дополнительный P3 selfcheck timeout9s —
не вердикт, finally restore успешен; повторена та же мутация с адресным lint.
Временный mutation verifier удалён, original bytes/SHA сохранены вне проекта.
Proof `node-c7-mutation-proof.json`, все failed IDs/JUnit/streams сохранены.
После восстановления native **exit0/ok:155/corpus32/0**, contracts17/static481/
securityok (`node-c7-reparent-stage5.*`). Финальный non-live прогон четырьмя
disjoint группами816+714+423+60=**2013/0**, independent collect **2013 exact IDs,
76 files,0error/skip**: `node-c7-final-exact-proof.json`/JUnit/streams. Свои live
ещё не запускались; полный snapshot и probes следующие, принятие не заявлено.
