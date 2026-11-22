# verification.tscn_lint — read-only проверка текста сцены

**Статус:** этап 7 — принято аудитом 2026-10-30 (сессия 60): корпус переснят с эталона 65/65 и 61/61, дифференциал 234 сцены (229 совпали, 5 — граница `addons`), 2337 non-live + 3 live, `selfcheck` ok (315/65), `snapshot_diff` 469/0, `gen_contract` 18, мутации аудитора M2–M7 и подложка P1 красные.
**Обновлено:** 2026-10-30

## Цель

Инструмент `check` принимает `path`, `content`, `planned_paths` и возвращает
`{fixed, changed, problems}`. Исправленный текст — данные, не запись на диск.
Полный текст, строковые замечания, их порядок и ранние выходы сохраняются
по фактическому эталону. Агрегатор `verification.check`, API-проверка скриптов,
headless/runtime checks, action judge, WAL, undo и мост в этот срез не входят.

## Старый код

| Файл относительно старого `godot_agent/python/` | Что делает | Граница |
|---|---|---|
| `godot_tools/tscn_lint.py:1–1315` | публичный `lint_and_fix_tscn:953`, сканеры и починки | Поведение в собственном domain, синтаксические примитивы только formats |
| `main.py:1987,2038–2064` | гейт и вызов при проверке кандидата | Не переносить изменение action/запись |
| `tools/agent_bridge.py:1173–1212` | второй фактический caller: `_check_one_path` | Взять вход сцены, не транспорт и headless |
| `tools/agent_bridge.py:1835–1847` | caller `repair_scene` | Запись/ремонт на диске вне среза |
| `godot_tools/gd_api_cache.py:115–164` | наличие кэша и lookup типа узла | Нужен чистый read-only шов, не миграция/refresh |
| `godot_tools/history_manager.py:74,102–105` | даже путь чтения кэша создаёт snapshots | Эталон с project_root запускать только на временной подложке |

Весь `tscn_lint.py`, оба указанных caller-пути и API-кэш прочитаны до правок
production. Эталонный addon остаётся read-only; его текущий HEAD/status/SHA
сняты собственным инвентаризатором в approved temp.
HEAD: `ba0535d4dec43c32750e601a6ca86e377abc6af3`;
`tscn_lint.py`: 74080 B, 1315 LF / 0 CRLF,
SHA256 `118e9ddc0b776cd86974666ff42789a3b41b93ba2b404f06c78db605ca0ac3f8`.

## Старые тесты

| Файл | Семейство | Текущая судьба tests-map | Что относится к C.8 |
|---|---|---|---|
| `test_agent_bridge.py:1113–1129` | unit / host-bridge | `protocol/dispatch`, replaced | Текст сцены с load_steps=9, закрывающим тегом и поздним sub_resource; взять как corpus-вход, не код теста |
| `repro_check_{blocking,truncated,unchecked}.py` | repro / check | `verification.check`, corpus | Агрегатор/полнота проверок, не закрывается сценовым линтером |

Прямых тестов `tscn_lint`/`lint_and_fix_tscn` в legacy tests поиском не найдено.
Частичная привязка сценового input в `docs/tests-map.md` согласована и внесена
до корпуса; владелец/судьба строки сохранены, файл/агрегатор не закрыт (R-17).

## Корпус

`fixtures/corpus/verification/tscn_lint/`: **65 кейсов**, manifest с 65 case
и 18 input SHA/byte-пинами, reference_commit и source pin. Снято до permanent
tests/production реальным публичным old helper на изолированных временных
подложках; старые tests/bootstrap не запускаются, host globals не патчатся.
Повторный actual-old прогон: **65/65, расхождений 0**, все **83 пина** совпали.
Покрыты M1–M8, scanner early return, load_steps, типы sub_resource, коллизии,
vanished/fuzzy instance paths, API cached/unknown/falsy/broken, unused resources,
LF/CRLF/BOM/lone CR/no-final-newline, команды в данных. Четыре path-refusal
ожидания — граница нового контракта, не выдуманные old errors; actual helper
ответ отдельно сохранён в reference_result для каждого из 65 кейсов.
Кейс 065 буквально воспроизводит legacy input:1117–1122. В первой capture
версии пропущены две пустые строки; raw case/manifest/proof сохранены в temp,
input исправлен и ответ заново снят до тестов/кода, не отредактирован вручную.
Capture/recapture scripts только approved temp; stderr обоих прогонов 0.

## Спецификация

- `check`: required `path`, `content`; `planned_paths` default `[]`.
- Строгие схемы; result только `fixed:string`, `changed:boolean`,
  `problems:array[string]`; `changed == (fixed != content)`.
- `effects=read`, `idempotent=True`, `cost=cheap`; существующий
  `READ_TEXT_MAX_BYTES`, типизированные `invalid_input/not_found/denied`.
- Инварианты: никакого выполнения содержимого, IO только через app/порты;
  domain без IO/re; один разбор в formats; никаких write/apply инструментов.
- ToolSpec записан после корпуса, до поведения; `check.json` сгенерирован,
  артефактов18. Первый gen_contract без --write честно fail/missing artifact;
  последующий --write ok. Принятые17 карточек не должны измениться (final audit).
- Permanent core/app/contract/real-dispatch/ports red: **231 failed,82 passed**,
  exit1/stderr0; pins/schema проходят, отсутствующие behavior/adapter/registry
  и разрешённый context update падают. Formats red отдельно **8 failed**,
  exit1/stderr0. До этих прогонов общие production/expectations не менялись.

## Решения по ходу

| Дата | Факт / предлагаемое решение | Почему |
|---|---|---|
| 2026-10-30 | `is_scene_path:155` принимает только `.tscn/.scn`, не `.res` | В §2 промпта ошибочно перечислено `.res`; сохранять фактический гейт |
| 2026-10-30 | `.tres`: helper ранний выход по отсутствию `[gd_scene`; tool refusal по path | Не расширять инструмент ради helper-кейса |
| 2026-10-30 | §2 шаги 1–8 промпта не описывают весь хвост `:1092–1315` | Сохранить весь фактический pipeline, включая финальную дедупликацию |
| 2026-10-30 | Промпт называет main единственным caller, но bridge тоже вызывает helper | Снята фактическая граница, transport/repair не переносить |
| 2026-10-30 | API cache read эталона может создавать каталог и мигрировать addon-файл | Нельзя буквально импортировать IO; требуется согласованный read-only adapter |
| 2026-10-30 | В tree/scene_deps нет публичной функции проверки существования ext_resource | Не дублировать чужую логику и не импортировать чужой domain |

Фактический порядок после проверки зависимостей: неподходящие sub_resource
типы → load_steps → дерево/инстансы/коллизии/API-кэш → битые ссылки →
неиспользуемые ресурсы → dotted properties → dedup. После изменения load_steps
последующие проверки используют прежнюю переменную text, как в эталоне.
API-кэш проверяет truthiness class record, а не только наличие ключа.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-30 | 1. лист / исследование | Лист создан первым в addon; production stubs неизменны; native blocked/exit2; собственный baseline 2014 tests + 404 corpus green |
| 2026-10-30 | 2. actual-old корпус | 65 кейсов +18 inputs; повторный reference прогон 65/65, 83 pins; boundary refusals отделены от actual helper; production/tests пока stubs |
| 2026-10-30 | 3. specification/red | ToolSpec;313 permanent tests:231 red/82 green, formats8 red; native fail/exit1:230 failed/67 passed, static gates ok, MODULE/corpus пока не выбраны |
| 2026-10-30 | 4. behavior/native | Pure core + formats144green; расширенные ports8red до общих правок; read adapters/app/module/bootstrap; inventory5red/228green до точечной правки; native315unit/65corpus ok18cards после fixture metadata correction |
| 2026-10-30 | 4. submitted mutations | M1–M8/P1–P3 все caught;8дополнительных guards +final S1F repeat:20runs/0equivalent, byte-copy restore SHA/bytes/EOL exact; post-last-mutant native ok315/65/18 |
| 2026-10-30 | 5. differential/regression | 65actual-old/core,61real-dispatch+4contractrefusals;230physical scenes/0diff;469corpus/0diff;2337nonlive exactIDs;8accepted selfchecks ok;5CLI args-file probes/read-only SHA |
| 2026-10-30 | 6. live/native | unchanged3live IDs=collect,0skip;Godot4.6.3;111ownednewUIDs byte-backed/removed,8historical preserved;marker/address cleaned. Final nativeok315/65/18,exit0/stderr0;staticgatesgreen |

## Проверки

Baseline inventory: `C:/Users/Lich/AppData/Local/Temp/opencode/tscn-c8-baseline-inventory.json`.
Собственный collect: **2014 test IDs / 76 файлов**, stderr 0, exit 0.
Четыре disjoint pytest-группы: **584 + 389 + 604 + 437 = 2014 passed**,
fail/error/skip 0, stderr 0, exit 0; exact ID equality collect ↔ JUnit проверена.
Полный существующий corpus: **404/404**, 16 leaf / 15 вызовов snapshot_diff,
расхождений 0, stderr 0, exit 0. Контракт 17; layers/limits 481/0; security ok.
Первый collect ошибочно снял pytest addopts без явного importlib и дал 48
collection errors; исправлен только одноразовый driver, повторный collect выше.
Это ошибка запуска, не дефект принятого кода; первый raw stream сохранён.

Baseline native: `module/unit/corpus not_implemented`, static ok;
**blocked/exit2/stderr0**, raw `tscn-c8-baseline-selfcheck.*` в approved temp.
Текущий native `python -B tools/selfcheck.py verification.tscn_lint`:
**ok/exit0/stderr0**, unit315passed/9.43s, corpus65/0, layers/limits492/0,
contract18/0,securityok; `reports/selfcheck/verification.tscn_lint.json`, raw
`tscn-c8-stage4-selfcheck-corrected.*`. Это исторический stage4; текущие доказательства ниже.
Corpus proof: `C:/Users/Lich/AppData/Local/Temp/opencode/tscn-c8-recapture-proof.json`;
actual-old **65/65**, differences0,83pins,stderr0 до кода. После сборки первый
native имел315green unit, но9corpus mismatches: capture fixture был относительно
fixtures, frozen runner разрешает относительно fixtures/projects. Исправлены
только ../ prefix в65 fixture fields и own-test base; ожидания неизменны,
повторный actual-old65/65,0diff. Прежние65raw/manifest сохранены byte-copy;
reverse bytes точны (`tscn-c8-fixture-recapture-proof.json`). Runner не изменён.
Inventory5red/228green до правки (`tscn-c8-accepted-inventory-red.*`);
7 разрешённых files имеют exact reverse check/read/count/hash projection,
SHA/bytes/EOL proof `tscn-c8-inventory-repair-proof.json` и
`tscn-c8-inventory-verify-proof.json`. Patch EOL на4files восстановлен по
byte-copy backups; прочие expectations/manifest cases не менялись.

Own proof: `C:/Users/Lich/AppData/Local/Temp/opencode/tscn-c8-baseline-proof.json`.
В исходном inventory была ошибка фильтра: исключён fixture каталог `.git`.
Он дополнительно прочитан и сверен с C.7 SHA, не удалён; raw исходник сохранён
как `tscn-c8-baseline-inventory-filtered-original.json`. Итог до правок: **1932
файла**, prompts `_start-prompt*.md` **28**, debris 0, прежних fixture UID 8.
Старый addon: 622 tracked + foreign-files совпадают с C.7 SHA; raw whole-addon
inventory 971 включает 349 ignored, не путать эти две области подсчёта.
Frozen pins из промпта совпали; исторические изменения документов/report C.7
принадлежат аудитору и не откатываются; потерянных файлов нет.
Патч добавления WORKLOG изменил два CRLF в прежнем хвосте; обратный CRLF-патч
не помог. Восстановлены только эти окончания по byte-copy backup: исторический
prefix 381172 B / SHA `71fb33c0e424a6685ec84ccd5959962be0d030abcc804f7befed310ff8ec510e`
точен; 4416/4416 CRLF сохранены. Scope audit ok: изменены только PROGRESS:57 и
append WORKLOG59; добавлены лист и свой selfcheck report, удалений/debris 0;
остальные 1930 baseline-файлов и весь старый addon точны по SHA/bytes/EOL.
Proof: `C:/Users/Lich/AppData/Local/Temp/opencode/tscn-c8-stage1-audit.json` и
`tscn-c8-worklog-eol-repair.json`. Это не переоформление прежнего журнала.

## Следующее действие

Независимому аудитору выполнить `python -B tools/selfcheck.py verification.tscn_lint` со своей базой и воспроизвести evidence; до его вердикта не ставить stage7/ported.

## Разрешение пользователя (2026-10-30)

Оба вопроса scope подтверждены явно: metadata-only fs.is_file, read-only
API-cache adapter, consumer ports C.8 и bootstrap binding; пять inventory tests
и context case/manifest только check/read/count/hash; частичная legacy-аннотация
без reassignment/закрытия агрегатора. Общие production/expectation правки только
после red-case и с последующими мутациями. Refresh/миграция/запись, принятые
механики, WAL/мост/API-check и frozen инструменты не разрешены.
tests-map аннотирован до корпуса; число/владелец/судьба строки сохранены.

## Блокеры

| Что мешает | Кто решает |
|---|---|
| Read-only API-cache/consumer ports/default binding | Реализованы после8red; no migration/write tests проходят |
| Metadata-only fs.is_file | Реализован после red; большой ресурс не читается, containment сохранён |
| Новое check меняет принятые full inventory assertions и context corpus | Только разрешённые check/read/count/hash после5red; reverse SHA/bytes/EOL proof точен |
| Нет явной C.8 судьбы legacy кейса (R-17) | Согласованная частичная аннотация внесена; владелец/судьба сохранены, агрегатор не закрыт |

Точный предлагаемый inventory scope: `tests/py/contract/test_functions_contract.py`,
`tests/py/contract/test_usages_contract.py`, `tests/py/integration/test_gd_lint.py`,
`tests/py/integration/test_scene.py`, `tests/py/integration/test_node.py`,
`fixtures/corpus/context/gather/001-all-sections.json` и её запись SHA/bytes в
`fixtures/corpus/context/gather/manifest.json`: только `check`, `read`, count
16→17. Иные поля/ожидания/SHA/EOL и принятые production/formats сохраняются.
Новые formats-примитивы разрешены промптом лишь append-only с red-case/мутацией.

### Стратегия файлов до реализации

Behavior — спецификационный порт с literal решениями/сообщениями/порядком
эталона, не импорт/wrapper старого модуля. Формат выдаёт нейтральные tokens,
spans и синтаксические events; не выдаёт problems и не знает project/cache/IO.
Синтаксические balance/property state machines находятся в formats, отображение
events в literal problems — domain. Header-fix кандидаты — format data,
решение удалить/заменить/остановиться — domain. Остальные rule groups: fixes,
semantics/cycles, tree/NodePath и pipeline; app только preflight/сбор read data.
API-cache — только snapshot read; исключены old migration/refresh/history mkdir.

## Submitted mutation proof (2026-10-30)

`tscn-c8-final-mutation-proof.json` в approved temp: **20runs** —11required,
8additional unique и повтор S1F после exact shared EOF/EOL repair. Каждый
submitted файл применён отдельно patch tool и восстановлен byte-copy;
before/restored SHA256/bytes/LF/CRLF/loneCR точны. Эквивалентов нет.

| Mutant | Red count |
|---|---:|
| M1 angle fix | 4 |
| M2 closing removal | 4 |
| M3 parent ordering | 2 |
| M4 missing ext existence | 2 |
| M5 fixes after scanner problems | 26 |
| M6 dict problems | 73 |
| M7 planned ignored | 4 |
| M8 ctor conversion | 8 |
| P1 extra RESULT field | 2 +gen_contract --check fail |
| P2 expected corruption | 3 (core/app/pin) |
| P3 pathlib / additional P3R re | 1 /1 AST guard |
| F1 token closing / F2 section splitting | 6 /10 |
| S1 metadata /S1F final metadata repeat | 2 /2 |
| S2 cache /S3 default binding | 4 /1 |
| I1 check owner removed /C1 context count corrupt | 5 /1 |

Before S3 restored only own fs/api binding indentation and historical shared
EOF/EOL; first repair driver omitted old trailing blank and failed before
writing. Corrected script cryptographically matched original accepted bytes:
reverse fs4added lines/bootstrap2added lines exact baselineSHA/bytes/EOL
(`tscn-c8-shared-byte-proof.json`). S3 unused backup refreshed before mutation,
oldstage4bytes retained; S1 rerun on final bytes asS1F. Current shared pins:
fs `8d2eec86bc9c`,bootstrap `75a1f6aba31d`.

Native after **last** P3R: **ok/exit0/stderr0**,315passed/8.62s,65corpus/0,
492layers/limits0,contract18/0,securityok (`tscn-c8-post-last-mutation-selfcheck.*`).

## Этап 5 — полный differential и regression

Aggregate `C:/Users/Lich/AppData/Local/Temp/opencode/tscn-c8-phase5-proof.json`
проверен по raw proofs: **2337 collected =2337 passed**,82файла, группы
652/612/582/491, exact test-ID equality, fail/error/skip0. Все **469кейсов**,
17leaf corpora/16module snapshot calls, differences0. Прямой actual-old/core
**65/65**; real build_agent dispatch **61/61**, четыре явно отделённых
contract refusals. Все **230physical fixtures/**/*.tscn**, batches58/58/57/57:
literal fixed и ordered string problems совпали, original scene SHA unchanged.

Принятые selfchecks, unit/corpus: gd_lint126/37,tree168/40,node_info352/65,
connections108/25,scene_deps176/40,node_rename162/36,reparent155/32,delete131/27;
все verdictok/exit0/stderr0. Пять реальных CLI `tools/probe.py check --args-file`
по cases001/002/024/061/059 совпали с ожиданием (включая два типизированных
отказа), полный project SHA до/после одинаков; `tscn-c8-cli-proof.json`.

Ошибка disposable snapshot driver раскрыта: первая group0 использовала
несуществующие symbols/project_query IDs и пропустила13analyze_rename cases.
Raw partial сохранён; исправлен только temp driver, module.py existence guard;
итог469 включает все17leafs. Frozen snapshot tooling не изменено.

Scope census обнаружил внешние изменения `_audit-handoff.md` и C.8 start-prompt
относительно own baseline. Пользователь **явно подтвердил сохранить** обновления
аудитора/пользователя (2026-10-30). Портер их не правит/не откатывает; независимые
byte-copy/SHA/bytes/EOL pins в `tscn-c8-confirmed-external-docs.json`, они не
выдаются за own changes или frozen byte-equality с начальной базой.

## Этап 6 — живая проверка и финальные гейты

Preflight проверил отсутствие чужой `zz_editor_branch_probe.tscn` и bridge
address; реальный `Godot_v4.6.3-stable_win64_console.exe` найден. Неизменённые
live-файлы выполнены последовательно: bridge **1passed/2.21s**, editor
**2passed/13.20s**; ровно три executed IDs=collect, fail/error/skip0:

- `tests/py/live/test_bridge_live.py::test_bridge_answers_three_verbs_from_real_godot`
- `tests/py/live/test_editor_branch_live.py::test_editor_branch_answers_and_cleans_up`
- `tests/py/live/test_editor_branch_live.py::test_scene_undo_refuses_empty_history_and_foreign_revision`

Это regression существующих bridge/editor/scene_ops, не перенос этих механик
в C.8. Собственный `check` через реальный CLI уже доказан пятью args-file probes;
его `fixed` никогда не записывается и не исполняется. Ровно **111новых**
fixture `.gd.uid`, созданных live: source existed/SHAunchanged, UID syntax,
byte-copy backup, SHA/bytes/EOL; удалены только эти owned exact files.
Полный addon before-live inventory восстановлен, прежние8UID byte-exact,
probe и bridge address отсутствуют. Proof `tscn-c8-live-proof.json`.

Первый temp live-proof driver не добавил ROOT в sys.path при дополнительной
проверке address cleanup: `ModuleNotFoundError: No module named 'python'` до
копирования/удаления artifacts. Исправлен только temp driver; повторный proof
успешен, тесты/production не менялись. Первый final native **ok/exit0**, но
stderr392B:8сообщений существующего recovery об expired plans; strict wrapper
честно отказал, raw `tscn-c8-final-native.{stdout,stderr,json}` сохранён.
Runtime планы не удалялись/не подавлялись. Последовательный повтор:

```text
selfcheck verification.tscn_lint
  module         ok              verification.tscn_lint (check)
  layers         ok              файлов 492, нарушений нет
  limits         ok              файлов 492, предупреждений 0
  contract       ok              артефактов 18, расхождений нет
  security       ok              нарушений нет
  unit           ok              315 passed in 9.13s
  corpus         ok              кейсов 65, расхождений нет
вердикт: ok
```

Report `reports/selfcheck/verification.tscn_lint.json`: `module=verification.tscn_lint`,
`verdict=ok`,all7checksok; exit0/stderr0, raw `tscn-c8-final-native-rerun.*`.
Отдельные final security/layers/limits/contract также exit0/stderr0:
securityok,492files/0violations,492files/0warnings,18cards/0differences.
Финальная проверка scope **ok/exit0/stderr0**: changed-row EOL, весь tests-map
owner/fate, approved reverse projections и отдельные external-document pins сверены.
Приёмка независимого аудитора, `ported` и stage7 **не заявлены**.

## Финальный scope/seal

`tscn-c8-sealed-proof.json`: 1932 baseline →2034 submitted files,102added,
30modified, из них2user-confirmed externaldocs и28own; deletions/debris0.
Old addon целиком SHA/bytes/EOL и Git HEAD/status/diff/staged точны;
frozen/принятый production вне разрешённых общих швов и прежние17cards точны.
PROGRESS только57, tests-map только136 (вся owner/fate колонка неизменна),
parity только67, README только42; прочие bytes и changed-row EOL точны.
WORKLOG historical prefix381172B/SHA71fb33c0…/4416CRLF сохранён.
Seven inventory/context reverse projections, fs/bootstrap reverse exact,
83owncorpus pins,8historicalUIDs и оба confirmed external-document pins сверены.

Первый strengthened seal поймал потерю CRLF в собственной tests-map:136
аннотации: восстановлено только EOL, note/owner/fate сохранены; byte-copy/proof
`tscn-c8-testsmap-eol-repair-proof.json`. Второй driver искал отсутствующую
temp baseline byte-copy parity; использована phase6 copy **до её правки**,
с SHA/bytes/EOL equality исходному inventory pin. Ошибочные raw seal outputs
сохранены; исправлен только disposable driver, следующий seal green.
