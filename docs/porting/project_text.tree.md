# project_text.tree — дерево файлов проекта (C.25)

**Статус:** исходный этап `0`, назначенный аудитором (см. `docs/PROGRESS.md`); preflight, не приёмка.
**Обновлено:** `2026-11-03`

## Цель

Показать дерево разрешённых файлов и каталогов проекта с буквальными сортировкой,
глубиной, счётом файлов, фильтрами и усечением native, не меняя проект.
Есть ли публичный инструмент или только внутренний вклад, определяет пользователь
по настоящим MCP-пробам §9; имя функции не доказывает регистрацию инструмента.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `godot_tools/project_tools.py:142–194` | `build_project_tree`: текстовое дерево, filters/depth/count/truncation | pure tree producer на существующем scanner; production пока не написан |
| `project_tools.py:126–138`, `:683–740` | sidecar/no-op exclusion, request-scoped policy filtering | чистые фильтры + module-owned policy orchestration |
| `project_tools.py:1449–1520` | `build_project_overview`: дерево или компактная сводка | только источник поведения; расширение среза не подразумевается |

Эталон `D:/vajno/Godot/random-game/addons/godot_agent/python/godot_tools/project_tools.py`:
102471 B / SHA256 `79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877`.
`begin_case_only_dir_casing` создаёт транзакцию переименования: только read-only
чтение источника, исполнение этой write-функции в C.25 не разрешено.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_path_policy_safety.py` | unit | corpus (`tests-map.md:83`) | точные tree-policy сценарии будут отобраны в §9.5 |
| `test_scan_policy_cost.py` | unit | replaced (`tests-map.md:169`), часть corpus поиска | read-only триаж содержательных случаев, без переноса старого test-code |

`test_tree_excludes_addon.py` содержит две tree-policy проверки, хотя историческая
строка `tests-map.md:130` адресует scene_model.node_rename и `.tscn`.
Это finding для явной case cross-reference, не разрешение переписать чужую судьбу.
Всего в триаже обоих листов 26 old test-method sources из пяти файлов;
`old-test-triage.json` содержит точные имена, строки, подслучаи и исключения.
Это не число будущих карточек. Строки tests-map сохранены, старые тесты не запускались.

## Корпус

| Что снято | Откуда | Файл |
|---|---|---|
| 27 настоящих tree-вызовов | исходный native `project_tools.py`, depth/count/ext/subdir/policy/junction | external `native-r2/`, numbered `source-excerpts.txt` |
| genuine list/call обоих профилей | user 14 / agent-dev 24; tree/files_list/list_files отсутствуют | external `mcp-r2/`, каждый absent call isError=true/Unknown tool |
| сравнение existing FS с настоящими NTFS junction | исходные `DiskFileSystem` и `ReadOnlyFileSystem`, без patches | external `fs-r2/`, `native-r2/link-probes.json` |

`fixtures/corpus/project_text/tree/`, production и новые тесты до ответа пользователя не меняются.

## Спецификация

`ToolSpec` / `contributes_to` пока не записаны. Read-only, идемпотентность,
strict result и отсутствие absolute/raw — обязательные ограничения.
Свой `os.walk` запрещён. `file_index.py` сейчас TODO; достаточность существующего
`fs.list_files` и пустые каталоги проверяются как вопрос §9.4, а не исправляются молча.

Native tree — одна строка с LF между строками и без final LF, не entries JSON;
файлы текущего каталога перед обходом sorted dirs, каталоги/файлы sorted отдельно.
Root header отсутствует, directory suffix `/`, шаг отступа два пробела, files
на один шаг глубже directory. Пустые каталоги выводятся; max_depth default 8;
max_entries считает только файлы, при следующем подходящем файле добавляет
буквальное `... (список обрезан; используй действие list_files для полного дерева)`.
only_exts сравнивает lower(file extension) с literal supplied values; пустой
массив выбирает ноль файлов (каталоги сохраняются), None не фильтрует.
`.godot`/`.import`/history, dot dirs, native noise names,
`.DS_Store` и casefold `.uid` исключены при общем обходе. Явный `.godot` subdir
при этом читается native; history/outside subdir отвергаются, addon subdir без
доступа даёт пустую строку. Это разница обхода и access policy, не новый запрет.

§9.4: существующий `list_files()` теряет пустые каталоги. На настоящем NTFS
junction он перечисляет `link-out/secret.txt` вне корня, хотя read_text затем
даёт PermissionError; native tree этот alias не показывает. `file_index.py`
содержит только TODO (206 B / SHA256 `002ef1e8156ca62d3f2ea83ead0fc752f51bbbf34093253547c6b71ce41d8a21`).
Без минимального расширения существующего scanner-port полный паритет пустых
каталогов недостижим; новый os.walk или substrate-файл не предлагается.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-11-03 | пользователь подтвердил 3828/833/83, 44 промпта, 17 ADR; STOP базы снят | прирост только файла постановки; стадии и ADR не меняются |
| 2026-11-03 | сначала настоящий MCP §9.1, затем native §9.2–9.5 | контракт 27/28 требует отдельного решения пользователя |
| 2026-11-03 | предложен tool-less вклад/internal service дерева, не новый tree ToolSpec | genuine MCP не публикует ни одно tree/list alias; consumer/entrypoints ещё решает пользователь |

### SHA до правки

Полная проекция: external `baseline.json`. Этот лист до создания `absent`.

| Файл модуля | B | SHA256 |
|---|---:|---|
| `app.py` | 447 | `4ce34300b13e8c3ccef821bcf345cca7c0a33365c987a874b4ee825aa2112404` |
| `module.py` | 540 | `73546a80a62fad1c32594ab84f4f99603c16b55f1da0ba601231524b4133d97e` |
| `tools.py` | 338 | `c3b0018c442ce4bcecbe2341dab8aaadc985adc97749b54260e73d726994b0f8` |
| `domain/core.py` | 230 | `3d7db43e06bc61428afb307969bac07d5c5227992f84958ff3e3d7c4d62cf73f` |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-03 | 1. лист создан | template и исходные SHA; stage0 остаётся назначенным аудитором |
| 2026-11-03 | §9 probes complete | native read 57 / tree 27, MCP 48 call_tool, CLI 6; FS insufficiency доказана, production не начат |

## Проверки

Реальный исходный `python -B -X utf8 tools/selfcheck.py project_text.tree`:
exit 2 / `blocked`, нет MODULE/tests/corpus; layers 563/0, limits 563/2 warnings,
contract 27/0, security 0. Raw вывод и fresh JSON: external
`c25-baseline-stop-20261103/`; 44 canonical reports восстановлены побайтово.
Это проверка скелета, не паритет и не успешный перенос.
Повторный actual selfcheck preflight с canonical byte-restore сохраняется в
external `selfcheck/` и `boundary-proof.json`; SHA-таблица — последний артефакт.

## Следующее действие

Независимый аудитор: `c25-d22-20261103/HANDOFF.md` + `SHA256-final.json` и fresh44reports. Stage/приёмка остаются аудитору; internal consumer — следующий срез.

## Блокеры preflight (история; решения D20–D23 ниже)

| Что мешает | Кто решает |
|---|---|
| tool-less tree consumer, internal entrypoints и форма результата | пользователь; новый публичный tree не подтверждён native |
| пустые каталоги не представлены в existing fs.list_files | пользователь: узкая опция существующего scanner, без нового обхода/файла substrate, default search неизменён |
| casefold/resolved guards и safe `..`; junction vs недоступный symlink | пользователь; общие kernel/search guards не меняются, WinError 1314 остаётся диагностикой |
| tests-map:130 чужой owner/prose для реальных tree-exclusion cases | пользователь: явная own case cross-reference без переписывания чужой судьбы |

## D20 — пользователь ответил на §9, 2026-11-03

Полный мандат D20.1–D20.5 записан в `project_text.read.md` → раздел D20.
Дерево: `TOOLS=()`, capability отсутствует, публичных aliases нет;
`internal_services=("project_text.tree",)` и реальные entrypoints.
Потребитель — следующий срез, сейчас только корпус/проба; `context.*` остаётся
долгом. Сейчас нет фактического consumer, поэтому `contributes_to=()`;
несуществующий инструмент/вклад ради прохождения guards не объявляется.

Разрешён новый `list_entries()` существующих disk/memory adapters, не правка
`list_files()`; пустые dir сохраняются. Junction/symlink не обходятся и сам
указатель не выдаётся (новый пункт SEC-24 до FS-кода с security-тестом).
WinError1314 — явный skip `symlink unsupported: WinError 1314`, не coverage.
Узел: path/type/children/count, native сортировка/служебные фильтры, res:// only.

### STOP до production

Текущие ModuleSpec, bootstrap и selfcheck отвергают именно internal-only
манифест. Новые независимые проверки —
`tests/py/contract/test_project_text_tree_registration.py`; production/FS,
TOOLS/contract, accepted search/ADR/statuses/stages неизменны.
Результат actual red и SHA будут в новом external `c25-d20-stop-20261103/`,
закрытое preflight-досье остаётся byte-exact. Требуется только узкий мандат
на общие проверки internal_services, без исключения для одного module_id.

### Продолжение: actual red и STOP §6 (2026-11-03)

Повторный независимый прогон registration-пинов: collect=executed **4**,
**3 failed / 1 passed / 0 errors / 0 skipped**. ModuleSpec, bootstrap registration
и selfcheck readiness независимо отвергают internal-only metadata; empty negative
остаётся зелёным. Новый direct pytest JUnit и `tools/run_tests.py` verdict `fail`
сохранены в external `c25-d20-resume-20261103/`, прежние partial artifacts не тронуты.

Actual `python -B -X utf8 tools/selfcheck.py project_text.tree`: exit **2**,
`вердикт: blocked`; module/unit/corpus `not_implemented`, layers **563 / 0**,
limits **563 / 2 warnings**, contract **27 / 0**, security **0**.
Fresh report архивирован; все 44 canonical reports восстановлены copyfile/byte-exact.
Production/native/project.godot и дерево после команд неизменны.

JUnit 3993 B, SHA256 `8115cb63830dc0d9c742c0b791ca9d459b56de33a77af520297798d20048160d`.
Полные results/мандат описаны в `project_text.read.md` → «Продолжение: actual red».
Запрошены только три общие проверки; selector/corpus, общие FS guards, accepted
search, пределы, ADR/statuses/stages не меняются. Дерево по D20 остаётся внутренним
сервисом с `TOOLS=()` и без фиктивного contributes_to. После разрешения —
red→минимальная правка→green, затем corpus/tests/code и SEC-24 до list_entries.

### C.25 production checkpoint, 2026-11-03

Private MODULE имеет только internal_services и реальный entrypoint build;
TOOLS/provides_tools/contributes_to/capabilities пусты. Native corpus22;
manifest SHA256 ebc04c6942679368c0e358a06ab6a1ff125304dfb04a1c9cc5878e21683537f8.
Typed tree — res:// nodes, файлы до каталогов, native noise, depth8,
file-only quota; empty only_exts выбирает ноль файлов в исправленной native
проекции (native direct [] выбирает ноль файлов; прежняя подмена на None
была ошибкой recorder, исправлена после actual red1→green1).
Новый list_entries сохраняет empty dirs и исключает reparse/link до обхода;
все4 настоящих junction созданы и green. Два реальных symlink creation
получили WinError1314, точные skip сохранены, покрытия symlink не заявляем.
Corpus client повторяет каждый read/tree и сверяет raw files + directories;
snapshot routing объявлен case field, прежний resource whole-answer сохранён.
Гейты/живая проверка/мутации ещё не завершены; этап и приёмка прежние.

### D21 — продолжение без нового STOP (2026-11-03)

Узкое разрешение пользователя получено: три общие проверки internal-only,
пустой manifest и public-without-call по-прежнему отвергаются. Red16:
11 failed/5 passed; original green4:4 passed. Полный текст/досье и EOL-proof
в `project_text.read.md` → D21; внешний путь `c25-d21-20261103/`.
Первый expanded green15/16 выявил неверный container type в новом security
assertion ([] вместо реального ()), не расширение production-периметра.
SEC-24/deviations дополнены до FS-кода. Стадии/приёмка неизменны.

### Новый STOP §6 — loader, 2026-11-03

`load_one` отвергает этот реальный private MODULE при TOOLS=()/contributes_to=():
`RuntimeError: python.modules.project_text.tree.module: нет TOOLS (ADR-0006)`.
Это четвёртая общая проверка, не входящая в D21; production loader не тронут.
Устаревшее допущение о tool/contribution опровергнуто actual discover и
build_agent: два новых пина red2/2, errors/skips0. Direct _register corpus/probe
этот путь обходил; он не доказательство регистрации целым runtime.
Selfcheck tree exit2/blocked, module not_implemented; остальные шесть green:
layers568,limits568/2warnings,contract28,security0,unit23,corpus22.
Fresh report вне repo; canonical44 byte-exact restored. Подробности D22 и
конкретное следующее действие в листе read → «Новый STOP §6».
Full non-live×2/snapshot/44/live/M–P не выполнены; stages/приёмка прежние.

Последний собственный focused93:89passed/2loaderfailed/2true1314skip, errors0.
Новые junction проверки также проходят client policy: outside/vendor/agent
aliases denied, safe alias канонизирован, pointer не показан/не пройден деревом.

Второй STOP §6:169 новых чужих fixtureUID появились между boundary сверками;
auditUID252 вместо83. Godot editor PID25824 для agent-rebuild наблюдался;
preexisting UID exact, новые не удалены (live агентом не запускался).
Точные witnessed bytes/timestamps/SHA и процесс во внешнем unexpected-UID-proof.json;
владение не предположено. Нужна отдельная команда по этим169 файлам, не broad cleanup.

### D22 — разрешённый loader и точечная уборка (2026-11-03)

Actual discover/build_agent red2→green2; новый empty negativegreen сохраняет
`python.modules.private.worker.module: нет TOOLS (ADR-0006)` дословно.
Only guard replacement proof2749B SHA
a3a217d7bcecf5d303b2d8490cdd9b4a0edbd3cb5757af83aa51962d5bbb4ffe;
финальная пустая строка восстановлена после patch. TOOLS=(),publicsurface не вырос.
D21expanded16/C19pins64green; actual selfcheck tree exit0/ok23unit/22corpus,
read exit0/ok38unit/35corpus.169UID аудитор признал мусором прогонов: deleted only
saved paths after bytes/SHA/mtime/ctime checks,auditUID83,dirs854,raw3934/audit3899.
После каждого прогона own UID witness/cleanup, без broad deletes.
Два trueWinError1314skip приняты D20.4/D22 и записаны в deviations с причиной;
pointer type check существует,4genuinejunction без skip. ADR-0006 не изменён,
поправка за аудитором. Следующее — весь non-live→snapshot→44→live→M/P маршрут;
stage0/приёмка прежние,c25-d22-20261103/.

D23: auditor approved only context/gather001 public inventory26→27+read/effect,
manifest onlySHA001; tree не входит в inventory, context consumer не перенесён.
Actual nonlive5225 red7 и snapshot1237 difference1 сохранены; те же7 пинов green.
Следующее — два полных nonlive green, snapshot1237,44checks/gates/live/M/P.

### Исправление собственного recorder: exact only_exts=[]

Initial native tree-only-empty.json уже показывал только каталоги; ошибочная
строка «empty array no filter» не была решением аудитора. Recorder неправильно
вызывал None. Actual повтор native helper с [] и тем же fixture: count0,
каталоги сохранены, bytes/dirs unchanged. Own007 recaptured; only native_result/
expect и SHA007 в own manifest изменены. Red1(count12 вместо0)→green1.
Tree manifest now87155d69b7e31ffe30d12ec706a16edb721f4f9f3d6cb19376f7038c6177b4ad.
Corpus остаётся22/unit23; ни foreign-кейс, ни публичный периметр не изменён.
Own probe теперь проверяет каждый JSON path на res://; Windows escaping не
может скрыть absolute path. File400lines, R-06 gate не ослаблен.
Следующее: полный повтор non-live×2/snapshot/44/gates/live/M/P на final bytes.

### Final C.25 — готов к независимому аудиту, не принято

Actual final tree selfcheck exit0/ok23unit/22corpus,read exit0/ok38/35. Publictree
не появился: TOOLS/provides_tools/contributes_to/capabilities пусты,realbuild.
Native007 exact[]→0files/dirs retained,own recorder repaired red1→green1; final
fullroute повторён. Два5225collect=executed прогона:5223pass/2actual1314skip each,
errors/fail0; snapshot1237 allmatched;44fresh29ok/15existingblocked,neighbors exact.
Gates568=563+3prod+2moduletests,contract28,0violations/2existingwarnings. Live3
no skips,335→419→335 restoreexact. M1/M2/M3 actualred1/restoredgreen1/SHA/EOL;
P1P2 byte/non-effect exact; P3audit3899files/835dirs/UID83/debris0. Fouractual
junctions green; two1314 skips documented, symlinkcoverage не заявляется.
169UID точечно удалены по savedbytes/SHA/timestamps; every later run cleanup
своих witnessed UID в том же шаге. Native947/foreign27contracts/oldFSmethods
exact;acceptedADR0006/stages/parity untouched. Next independent audit HANDOFF/
SHA-last; ADR поправка за аудитором, context consumer остаётся следующим срезом.

Closing parallel auditor-next prompt отсутствовал в baseline,появился послеP3,
не писался/не откатывался портером. OwnC25audit3899;actual3900 включает1prompt,
dirs835/UID83/debris0 unchanged; baseline absence/observedSHA в externalwitness.

### C.25 — принят аудитом 2026-11-03 (сессия 77)

Приёмка — только моими прогонами:

- `selfcheck project_text.tree` ×2 с бэкапом всех 44 отчётов и возвратом
  байт-в-байт: verdict ok — module = internal-only, unit 23, corpus 22/0,
  layers 568/0, limits 568/2, contract 28/0, security ok.
- Полный non-live 5225 (5223/2 genuine 1314 skips); `snapshot_diff` ×2 —
  «кейсов 1237, расхождений нет» (`project_text/tree 22/22`); live 3/3,
  project.godot 335→419→335 exact (SHA `958b3a92…`).
- Периметр internal-only подтверждён по коду: `module.py` —
  `provides_tools=()`, `internal_services=("project_text.tree",)`,
  `entrypoints={"build": build}`, артефакта контракта нет (контракт 28 —
  только `read`).
- Поправка ADR-0006 (D22) внесена аудитором в этой же сессии: internal-only
  сервис без публичного инструмента и без фиктивного `contributes_to` —
  валидная форма модуля; guards принимают по форме spec, исключение по
  `module_id` запрещено.

Записи аудитора: строка `project_text.tree` 0→7, `parity.md` → `ported`,
блок C.25 в `PROGRESS.md`, WORKLOG append CRLF. Следующий срез —
consumer дерева (context.ask), средняя сложность.

