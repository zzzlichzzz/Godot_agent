# scene_model.scene_deps — анализ неподключённых обработчиков

**Статус:** этап 7 — ported, принято аудитом 2026-10-29 (сессия 54): свои прогоны 40/40 и дифференциал на 81 файле (эталон == порт, отказы включены), M2/M4/M5 красные, `candidates`-мутация поймана как невосстановленный дрейф и файл возвращён к `4D192DD6FDAD` (6683 B); M3 признан эквивалентным (исключение своей сцены недостижимо).
**Обновлено:** 2026-10-29

## Цель

Отдельный read-only `scene_deps({path})`: анализ текущей сцены или скрипта по
старым эвристикам неподключённых сигналов. Возвращает данные, ничего не пишет.
Явно названная проекция `{text,added,notes}`: для сцены три компонента старого
tuple; для скрипта `text=null`, `added=[]`, `notes` — буквальный старый список.
`text` — предложенный текст сцены, **не применённая правка**. Не обещает общего
ресурсного graph/cycle-validator: эталон его не реализует.

## Старый код

| Файл | Настоящая сигнатура / возврат | Как делим |
|---|---|---|
| `scene_deps.py:73-99` | `to_snake(name)` → string, Unicode/acronym/digit quirks | минимальный format fact, не regex/domain parser |
| `scene_deps.py:102/111/120` | attrs/id/parse_scene → `(ext,nodes,connections)` | существующий `formats/tscn.fields` |
| `scene_deps.py:175-176` | `extract_handlers(script_text)` → unique ordered list; regex col0/static func `_on_\w+` | новый публичный `formats/gdscript.handlers`; accepted tokenizer/parse не менять |
| `scene_deps.py:186-241` | collect gd/scenes, code method references, raw scene method needle, custom signal set | IO через declared ProjectFiles порт; script/scene facts только formats |
| `scene_deps.py:244-268` | `_find_candidates(handler,nodes,script_node)` → `(node,signal)` list с дедупом path+signal | domain + literal KNOWN_SIGNALS |
| `scene_deps.py:271-359` | `analyze_scene_action(scene_text,scene_res_path,project_root)` → `(new_text,added:list[str],notes:list[str])` | чистый domain на данных портов; не применять new_text |
| `scene_deps.py:362-412` | `analyze_script_action(script_text,script_res_path,project_root)` → `notes:list[str]` | domain; даже при нескольких candidates заметка о первом, не исправлять |
| `main.py:1898-1922`, call1904 | candidate/path/project_root; при added меняет action в create_file, notes≤4 в system-message | прочитан реальный вход, старую write orchestration **не переносим** |
| `main.py:1925-1935`, call1930 | candidate/path/project_root; notes≤4 в queue_action_note | возвращаем полный список, не системные команды/queue |

Reference scene_deps19866B/SHA256
`dbd502afeca7fa2fe97d49a995438c551d313d1713e6591865ab2bf3b053067b`;
frozen ba0535d4dec43c32750e601a6ca86e377abc6af3.
Вход не требует action/node. Результаты — не dependency edge-list и не map
файлов. Scene анализ учитывает existing methods, кодовые упоминания и другие
сцены; если нет new_lines, возвращает исходный scene_text (EOL важен).

## Старые тесты

| Источник | Семейство | Судьба | Что берём |
|---|---|---|---|
| строки docs/tests-map:56-130, owners node_rename/symbol_rename | unit/flow/live/repro | исходные fates сохранены | только идеи scene hierarchies/links, не host bootstrap/test code |

Своих legacy standalone тестов нет; все168 строк/приложение неизменны.
Новые тесты регистрируются в этом листе/PROGRESS, не переатрибутируются старым.

## Корпус

40 independent cases/82 source inputs в `fixtures/corpus/scene_model/scene_deps/` до реализации:
scene без scripts, однозначные/self/ambiguous/unknown handlers, custom signals,
existing method (даже несуществующая функция не валидируется), connect/Callable/
quoted references, другие сцены/подпапки, instance type unknown, ExtResource,
cycle (не graph validation), rigidbody note, broken/empty/BOM/CRLF script,
512KiB scan boundary и attached script исключение, invalid path/.tres/notfound.
Один общий temporary capture ordinary-imports actual old functions и сохраняет
оба корпуса + hashes/bytes/date/commit/projection/copied_source, затем удаляется.
Handlers differential: все .gd в editor/**, fixtures/projects/** и обоих новых
корпусах; не только _on_-positive files. Formats fact corpus включает regex
quirks col0/static/multiline/duplicates/Unicode/comments/literals.

## Спецификация

- `{path}`; по extension `.tscn`/textual `.scn` → scene branch, `.gd` → script;
  строгая named projection `{text:string|null,added:string[],notes:string[]}`.
- read/idempotent/heavy, invalid_input/not_found/denied; без truncate/новой quota.
- Primary/read_raw limit READ_TEXT_MAX_BYTES. Reference512KiB — **только** scan
  `.gd`/`.tscn`, не primary candidate и не direct attached script read. Attached
  reader в reference без лимита; новый fs имеет общий cap, границу документировать.
- Reference skipdirs: `.godot,.git,.import,__pycache__`; scan case-sensitive
  extensions. IO exceptions skip scan/attached, но primary errors typed.
- Consumer Protocol ProjectFiles `{list_files,read_raw}` и RawReader в своём
  ports.py, existing fs structurally implements оба, composition не меняется.
- App PathPolicy применяется к primary, scan и attached files; не читать addon/
  history/outside пути. Domain получает bytes/texts/facts, без IO/re/oswalk.
- Форматное расширение: handlers/custom_signals/code_reference в gdscript;
  to_snake/raw method-reference/raw path-reference в tscn при доказанной нужде.
  Факты доступны явными вызовами `tscn.*`; закрытый `tscn.__all__` не расширяется.
  Последние coarse facts сохраняют literal reference (даже comments), а не
  улучшают semantic parser. Existing format prefix/corpora неизменны.
- Domain только KNOWN_SIGNALS/candidates/решения/сборка текста, никаких eval/exec/
  shell/data→commands. Результат text не исполняется и не сохраняется.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-29 | Названа projection tuple→{text,added,notes}; script→{null,[],notes} | §4 разрешает явную projection, сохраняет literal lists и не утаивает read-only suggested text |
| 2026-10-29 | Не добавлять action/node или graph/cycle recursion | их нет в actual reference/main calls |
| 2026-10-29 | Existing list_files/read_raw достаточно; runtime не менять | narrow consumer protocol без новой композиции |
| 2026-10-29 | Minimal format extensions, old parser unchanged | для сохранения anchored handler/code-reference quirks нужен facts API, не второй domain regex |
| 2026-10-29 | Пользователь разрешил только C.5 registry-composition scope: context001 tools/count/effects/hash, пять inventories names/count | прошлое C.4 разрешение не переносилось; новое получено явно, reverse byte/SHA proof обязателен |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-29 | 1. чтение/лист | все anchors и реальные main calls/return shape до ToolSpec; production stubs не тронуты |
| 2026-10-29 | 2. корпус | actual-old40cases/82inputs; handlers differential133real `.gd` +19quirks,18snake/8scene needles; script удалён до тестов/кода |
| 2026-10-29 | 3. спецификация + tests | общий набор459tests:446failed/13passed/0errors,exit1 до production; selfcheck deps128failed/2passed,corpus40fail — native verdictfail |
| 2026-10-29 | 4. код | pure scene/script report, own fs seams, format facts; initial459/459green +4pathguards (2red/2passed до fix); native176unit/40corpus — verdictok |
| 2026-10-29 | 5. differential/mutations | old40→new40/40; M3 root-only10/49, M4 local-handler-regex2/45 (AST+delegation), P3 pathlib1/1+lintfail; смежные M/P и все restore byte/SHA/EOL identical |
| 2026-10-29 | 6. живая проверка | native args-file/default recursive fs: unique/nested/ambiguous scene, nested script note, outside refusal — literal parity; project SHA unchanged; final1519nonlive+3live/0 |

## Проверки

Baseline1200files/25prompts/13sheets/debris0; disjoint448+295+253+60=1056
nonlive/0failures/errors/skips, exact collected/executed IDs1056/53files;
live3/21.69с, formats135. Contract12, snapshot244/0, layers/limits460/0,
securityok, accepted node selfcheck247/corpus65 ok. Frozen tscn/tree/node hashes
совпали. Pre-edit rebuild inventory и old622working-tree SHA в approved TEMP;
oldHEAD ba0535d4/status ровно два чужих ??log/diffempty.
Native `python -B tools/selfcheck.py scene_model.scene_deps` → exit2,
`вердикт: blocked`: module not_implemented (нет MODULE), unit not_implemented
(нет тестов), corpus not_implemented (нет корпуса); layers/limits460/0,
contract12/securityok. Готовность не заявлена. Stdout/stderr в TEMP
`scene-deps-c5-scene_model-scene_deps-stage1.*`;
native report `reports/selfcheck/scene_model.scene_deps.json`.

Final native selfcheck **176passed,corpus40/0,вердикт ok**; contract14/0,
snapshot309/0, layers/limits467/0, securityok. Полный disjoint regression:
598modules+543main-a+318integration+60guards=1519nonlive/62files, live3/24.619с;
total1522/64files,0failures/errors/skips, exact collected/executed IDs1519/1519.
Formats314/0 включает133real `.gd` differential +19quirks/18snake/8scene needles
и coverage-set pin. Accepted node247/65, tree168/40, gd_lint126/37, scene_ops25
selfchecks ok; tree168=прежние128+40 новых integration `test_scene_deps*`,
которые native selfcheck выбирает по своему существующему prefix, не новые tree tests.
Accepted `tscn.__all__` восстановлен после2red старых format tests без их правки;
main-a rerun543/0. Сгруппированный selfcheck timeout30с отброшен, отдельные
native runs≤30с зелёные. Evidence `<TEMP>/scene-deps-c5-*-final.*` и
test-ids/probes proofs; report `reports/selfcheck/scene_model.scene_deps.json`.

Final scope1200→1429/+229/0deleted,25prompts/15sheets/debris0. Corpusdeps162files:
40cases+manifest+82sourceinputs+39minimal project.godot seed configs (не analyzer
inputs); connections49files. Другие18newfiles: sheets2/reports2/cards2/Python12.
Семь authorized composition reversals и семь M/P restores byte/SHA/EOL identical;
tscn old9550B и gdscript old707B prefixes unchanged, `tscn.__all__` прежний.
Frozen accepted node/tree/schema/runtime/editor/bridge/tools/12cards/tests-map/
old corpora unchanged кроме разрешённого context composition/hash; native accepted
reports обновлены проверками. Old622working-tree SHA unchanged, HEAD ba0535d4,
status ровно2чужих??logs, diffempty. WORKLOG original prefix before session53
byte/SHA identical/CRLF preserved; PROGRESS LF preserved. Scope evidence
`<TEMP>/scene-deps-c5-final-{inventory,scope-proof}.json`, backups доступны аудитору
в TEMP, scripts удалены. Auditor-only README/handoff/acceptance headers untouched.

## Следующее действие

Независимый аудит C.5: повторить reference25/40 и133gd differential, mutations,
native gates иscope proofs; отдельно проверить scan512KiB/direct4MiB и script-first quirks.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Нет; connections M2 и точечный composition scope подтверждены пользователем | — |

## T1 additive fact registration (2026-11-22, ADR0088)

Existing module/semantics/status remain unchanged. Required-GD coverage genuinely
RED on36 new editor scripts; native original source exact frozen SHA/19866bytes,
actual handlers/custom-signals/code-reference functions×2. New sibling format
corpus t1_script_facts; original scene_deps manifest110763bytes/SHA1b8780f63d0433c5cd246da92d4f65059add772c8b29fd1606163d3100cd3ab5 unchanged.
One in-memory test composition line, exact original-test reconstruction and all
old assertions/facts/order;36 additional differential cases +one scope/pin case
paired GREEN. Next current mutation/fresh full+native selfcheck through T1-editor;
this is input coverage, not a new public tool or independent acceptance.

T1 supplementary closure:36 actual native facts×2 equal, all36 additive format
IDs plus scope test GREEN×2; old110763-byte manifest and all old assertions/order
unchanged/exact reconstruction. Final8281pass+2historical gaps×2 and actual
scene_model.scene_deps selfcheck×2 ok/exit0. No new public tool or semantic change.
