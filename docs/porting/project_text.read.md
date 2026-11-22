# project_text.read — чтение файла проекта (C.25)

**Статус:** исходный этап `0`, назначенный аудитором (см. `docs/PROGRESS.md`); preflight, не приёмка.
**Обновлено:** `2026-11-03`

## Цель

Прочитать разрешённый политикой файл проекта без изменения байтов на диске,
с буквальными отказами, BOM/EOL и ограничением выдачи эталона. Публичное имя
и форма типизированного результата определяются после настоящих MCP-проб §9.

## Старый код

| Файл | Что делает | Как делим |
|---|---|---|
| `godot_tools/project_tools.py:778–786` | `read_project_file`: текст, усечение, флаг | pure преобразование и существующий FS-порт; код пока не написан |
| `project_tools.py:1370–1376`, `:760–763`, `:197–446` | policy boundary, resolved identity и разрешение чтения | module-owned policy orchestration без ослабления общих guards |
| `tools/godot_agent_mcp.py:271–274`, `tools/agent_bridge.py:365–398` | native MCP `read` и CLI-перевод | предмет genuine `list_tools` / `call_tool`, не предположение по атрибуту |

Эталон `D:/vajno/Godot/random-game/addons/godot_agent/python/godot_tools/project_tools.py`:
102471 B / SHA256 `79e9b035bd211f4a44623573d64f88f5bf47a049725c18dc90d985f47c6a7877`.

## Старые тесты

| Файл | Семейство | Судьба | Что взяли |
|---|---|---|---|
| `test_path_policy_safety.py` | unit | corpus (`tests-map.md:83`) | отбор случаев чтения выполняется в §9.5; код теста не копируется и не запускается |

Также отобраны read-подслучаи `test_scan_policy_cost.py` (строка 169),
`test_agent_bridge.py` (136) и `test_godot_agent_mcp.py` (156).
Полный AST-only триаж обоих листов: 26 старых test-method sources из пяти файлов,
не число новых карточек; `old-test-triage.json` содержит имена, строки, судьбу и
исключённые write/search/context-подслучаи. Старые тесты не импортировались и не запускались.

## Корпус

| Что снято | Откуда | Файл |
|---|---|---|
| 57 настоящих вызовов native read helpers, включая четыре NTFS junction | исходный `project_tools.py`, изолированный проект | external `native-r2/`, `source-excerpts.txt` с номерами строк |
| initialize + list_tools + 24 call_tool на профиль | настоящий SDK stdio, byte-exact копия native source в изолированном проекте | external `mcp-r2/`; user 14 / agent-dev 24, `read` успешно вызван |
| 6 настоящих CLI-вызовов границ чтения | исходный bridge из той же копии | external `bridge/`, stdout/stderr/exit code |

Production, собственные тесты и `fixtures/corpus/project_text/read/` до ответа пользователя не меняются.

## Спецификация

`ToolSpec` пока не записан. Предъявляемые ограничения: `effects="read"`,
`idempotent=True`, строгая схема, без публичных absolute/raw; контракт 27/28
и публичный периметр решает пользователь по §9, не портер.

Факты §9.1–9.3: native helper возвращает tuple `(content, truncated)`;
UTF-8-sig/errors=replace, BOM снимается, CRLF/lone-CR/mixed нормализуются в LF,
последний LF сохраняется в helper. Бинарь читается с U+FFFD/NUL, не отвергается.
Файл 4194305 B читается целиком перед усечением по символам; exact quota не усечена.
Публичный `read`: default 50000, CLI-границы 1..200000; MCP отдаёт TextContent,
`structuredContent=null`, с path/access/truncated/header, `.strip()` и внешним
clip до 60000 (head + marker + tail), а не JSON `{path, content, truncated}`.
Типизированная проекция и её бюджет требуют ответа пользователя, а не молчаливого отклонения.

Read noise != access ban: `.godot`/`.import`, `project.godot`, root `plugin.cfg`
читаются; history/outside запрещены до is_file. Addons/ADDONS casefold + resolved
identity, независимые allow_addons/allow_self_edit и validated trusted agent root.
Safe `res://src/../plain.txt` разрешён native; публичный абсолютный путь отклонён CLI.
Четыре настоящих junction показали outside/addon/agent denial и project success;
file/dir symlink создать нельзя (WinError 1314), mock-green не заявляется.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-11-03 | пользователь подтвердил 3828/833/83, 44 промпта, 17 ADR; baseline STOP снят | изменение только пользовательского промпта, ADR-0017 остаётся proposed |
| 2026-11-03 | сначала MCP §9.1, затем §9.2–9.5; production запрещён до ответа | прямой порядок пользователя |
| 2026-11-03 | §9 пробы завершены; предложено 27→28: публичный read, tree без публичного имени | genuine list/call в обоих профилях; это предложение, решение ещё не дано |

### SHA до правки

Полная проекция: external `baseline.json`. Этот лист до создания `absent`.

| Файл модуля | B | SHA256 |
|---|---:|---|
| `app.py` | 467 | `3bbd0f0ebb5a491c2134d798bb9953f73d94f861317dd965ef543b4329654ed2` |
| `module.py` | 477 | `b86bb342bdc01a09f5d7745f476ed29e841c5a508e615d50e4e1f5bf97d01c7f` |
| `tools.py` | 358 | `25acffafdd59baa48a9fb00d66b19f8c8f2f97669df7c84f5a859ed1339e059d` |
| `domain/core.py` | 250 | `cd7b3f4a65d35782f0958ba1b7f5800aab715ca4b8155af2cc6a2220050929ee` |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-03 | 1. лист создан | шаблон, SHA до правки, подтверждение базы; этап не менялся |
| 2026-11-03 | preflight §9 | native read 57 / tree 27, MCP 48 call_tool, CLI 6; numbered excerpts, old-test triage; production/tests/corpus не написаны |

## Проверки

Исходный реальный `python -B -X utf8 tools/selfcheck.py project_text.read`:
exit 2, verdict `blocked`; MODULE/tests/corpus отсутствуют;
layers 563/0, limits 563/2 warnings, contract 27/0, security 0.
Вывод и fresh JSON: external `c25-baseline-stop-20261103/`;
44 canonical reports восстановлены byte-exact. Это не вердикт реализации.
Повторный реальный selfcheck в конце preflight и byte-restore: external
`selfcheck/` и `boundary-proof.json` того же нового досье; ожидаемый skeleton
verdict `blocked`, не перенос. Полная SHA-таблица закрывается последним артефактом.

## Следующее действие

Независимый аудитор: `c25-d22-20261103/HANDOFF.md` + `SHA256-final.json` и fresh44reports. Stage/приёмка остаются аудитору; ADR-0006 поправка D22 — его долг.

## Блокеры preflight (история; решения D20–D23 ниже)

| Что мешает | Кто решает |
|---|---|
| публичный read / tree-вклад, точная типизированная проекция и внешний clip | пользователь; контракт остаётся 27 до решения |
| native full-file read против существующего default 4 MiB; safe `..`, casefold/resolved identity | пользователь: module-owned порт/композиция без ослабления общих guards и бюджета чужих потребителей |
| недоступные file/dir symlink и закрытые deviations | пользователь после фактических WinError 1314; junction-проверка не выдаётся за file-symlink |

## D20 — решения пользователя, 2026-11-03 (постоянный мандат, пункт 3)

Прежние вопросы §9 закрыты решениями ниже; это не приёмка реализации и не
разрешение править неназванную общую инфраструктуру.

| Пункт | Решение |
|---|---|
| D20.1 | Контракт 27→28: публичный только `read`. Tree `TOOLS=()`, без capability/public name; `internal_services=("project_text.tree",)` и реальные entrypoints, `contributes_to` только по фактическому потребителю. Корпус/проба — `internal_call` как D17. Mapping:139 не доказательство публичного инструмента |
| D20.2 | Typed read: default 50000 Unicode-символов, max 200000; запрос выше maximum → `invalid_input`; `truncated` и фактическое число возвращённых символов. BOM снимается, CRLF/lone CR→LF, бинарь не отвергается. Это read-only проекция, байты диска неизменны. **Внешний клип 60000 — снаружи нашего периметра**, в ToolSpec не переносится |
| D20.3 | Только новые `list_entries()` в существующих `disk_fs.py` и `memory_fs.py`: файлы/каталоги, включая пустые. `list_files()` не меняется, accepted search и его пины сохранены. Junction/symlink не обходятся, запись-указатель исключается; новые substrate-файлы не разрешены |
| D20.4 | Реальный WinError1314 → `pytest.skip("symlink unsupported: WinError 1314")` и строка deviations; не green/не покрыто. Код обязан проверять тип до обхода. Созданный без admin junction обходим в новом `list_entries()` → STOP |
| D20.5 | Tree node: `path`, `type` (`file`/`dir`), `children`, `count`; native sorting/служебные exclusions, пустые каталоги; только `res://`, без absolute/raw |

Потребитель дерева — следующий срез, сейчас только корпус/проба. Внешний
consumer в `context.*` — долг, а не фиктивный текущий `contributes_to`.
SEC-24 уже содержит принятое C.24: пункт D20 об исключении junction/symlink
дописывается без удаления/переименования прежнего инварианта, вместе с новым
security-тестом до реализации `list_entries()`; пока новая политика не покрыта.

### STOP до production: фактические общие барьеры D20.1

`python/kernel/module_spec.py:45–47` не учитывает internal_services;
`python/runtime/bootstrap.py:142–145` отвергает реальные internal entrypoints
без `call`/contributes; `tools/selfcheck.py:131–138` объявляет такой spec fail
даже при tests/corpus. Три независимых новых red-кейса и один negative pin:
`tests/py/contract/test_project_text_tree_registration.py`.
Нельзя обходить это фиктивным `context`/`project_text` вкладом, копией
ModuleSpec или feature-exception. Production обоих модулей/FS/контракт пока
не менялся. Нужен явный узкий мандат на общие проверки, особенно selfcheck
(текущий D19 разрешает не всякую смену поведения проверяющего инструмента).

### Продолжение: actual red и STOP §6 (2026-11-03)

Новый прогон существующего собственного registration-теста: collect=executed **4**,
**3 failed / 1 passed / 0 errors / 0 skipped**. Три независимых отказа:
ModuleSpec без учёта internal_services, registration без call/contributes,
module_readiness без учёта internal_services. Truly-empty negative зелёный.
Это доказательство барьера инфраструктуры, не differential и не мутации реализации.

Actual `python -B -X utf8 tools/selfcheck.py project_text.read`: exit **2**,
`вердикт: blocked`; module/unit/corpus `not_implemented`, layers **563 / 0**,
limits **563 / 2 warnings**, contract **27 / 0**, security **0**. MODULE, тесты
модуля и корпус пока отсутствуют; зелёный перенос не заявляется.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c25-d20-resume-20261103/`:
`results.json`, raw stdout/stderr, fresh selfcheck JSON, `red.junit.xml`
(3993 B, SHA256 `8115cb63830dc0d9c742c0b791ca9d459b56de33a77af520297798d20048160d`).
Старое незавершённое red-досье не переписано. Все 44 canonical reports
восстановлены `copyfile` побайтово; production, native, project.godot и дерево
после проверок равны исходным. После записей — boundary proof и SHA-таблица последней.

**Нужный мандат:** только `python/kernel/module_spec.py::__post_init__`,
`python/runtime/bootstrap.py::_register`, `tools/selfcheck.py::module_readiness`
для настоящего internal-only модуля с рабочими entrypoints. Не вводить фиктивный
consumer/capability или исключение по module_id; сохранить отказы empty,
no-entrypoint/no-tests и все остальные guards. До разрешения production не менять.
Решения D20.1–D20.5 не переоткрываются; стадии/приёмка остаются за аудитором.

### C.25 production checkpoint, 2026-11-03

Original4 и expanded16 green; C19 selector64 green. Native helper вызван до кода:
read35/tree22 карточки, неизменность raw bytes. Production red74: 72 failed,
2 genuine WinError1314 skip; итоговый собственный прогон90: 88 passed/2 skip.
Первый probe не передавал обязательный пустой contributions; следующий прогон
выявил неверный порядок аргументов native identity helper в моём recorder.
Оба провала сохранены; native повторён с корректным порядком, не подменён новыми ответами.
Read manifest SHA256 2657dc8ea121013832c2c2b1ecc140f631d6bd3a9bdf7b02f134ded276ab314c.
Схема read — ToolSpec, public contract28; внешняя обрезка60000 не переносится.
Устаревший public count26 в test_verify дал actual AssertionError27!=26;
по D19 изменено только число27, тот же тест green, вклад verify неизменен.
Этап/приёмка не выставлялись; общее доказательство ещё выполняется.

### D21 — разрешённый ремонт трёх проверок (2026-11-03)

Пользователь разрешил только __post_init__, _register и module_readiness:
internal-only идентичность без публичного инструмента, прежние errors/пустой
manifest/порты/profile изолированы; selector/семь проверок не меняются.
Исходный red 3 failed/1 passed дословно скопирован и SHA-сверен в
external `c25-d21-20261103/d21-original-red/`. Expanded red: 16 collected/executed,
11 failed/5 passed/0 errors/skips. Те же исходные четыре после production:
4 passed/0/0/0. Первый expanded green: 15 passed/1 failed — **дефект нового
теста**, Registry.contributions возвращает (), не []; исправлен ожидаемый
container type, запрет отсутствия public/contributions не ослаблен.
`d21-mandate-proof.json` доказывает ровно три sanctioned replacements и
сохранение остального byte/EOL; selfcheck содержит исходные четыре LF.
Это не успешный перенос C.25 и не приёмка; прежний STOP снят D21.

### Новый STOP §6: четвёртая проверка вне D21 (2026-11-03)

Устаревшее допущение `load_one`: каждый модуль с TOOLS=() обязан иметь
contributes_to. Фактическое опровержение — D21-valid MODULE project_text.tree
с internal_services и build; actual discover и build_agent отвергают его:
`RuntimeError: python.modules.project_text.tree.module: нет TOOLS (ADR-0006)`.
Два собственных пина actual red2/2, ошибки/skips0, raw/JUnit сохранены.
Direct _register в corpus/probe обходил loader: прежний green90 не доказывает
полный lifecycle; ложной общей готовности не заявляем.
Module loader production не изменена и не входит в закрытый D21 список.
Fresh selfcheck read exit0/ok: module/layers568/limits568(2warnings)/contract28/
security/unit38/corpus35 green; tree exit2/blocked при unit23/corpus22green.
Оба fresh отчёта вынесены в external c25-d21-20261103/, canonical44 восстановлены
побайтово. Full non-live×2/snapshot/44/live/M–P ещё не выполнены.
Требуемый D22: ослабить только obsolete TOOLS/contribution guard для объявленных
internal_services/entrypoints; пустой spec и прочие проверки/ошибки, имя/порядок
tools и реальные contribution остаются прежними; без module_id hardcode.
После разрешения own probe должен идти через load_one, не через обход guard.
Этапы/приёмка прежние; C.25 **не готов к независимому аудиту**.

Последний focused на сдаваемых bytes: collect=executed93, **89 passed/2 failed/
2 skipped**, errors0; failures только два loader-пина, skips только реальные
WinError1314. Root-directory pin и расширенные настоящие junction client
checks green. Raw/XML/proof `c25-stop-focused.*` во внешнем досье.

### Второй STOP §6 — неожиданные foreign UID

После первой финальной сверки появились169 новых .gd.uid в чужих fixtures;
preexisting UID не изменены, audit UID83→252 (raw84→253). Наблюдаемый Godot
editor PID25824, project agent-rebuild; timestamps новых файлов UTC
2026-11-02T23:21:17.*, процесс создан23:21:10.663. Происхождение/владение не
присвоены агентом: live не запускался, новые UID не удалены/не переписаны.
Точный список/bytes/SHA/timestamps/process сохранён в unexpected-UID-proof.json
и unexpected-new-UID/ вне repo. Нельзя заявлять83UID/zero debris или стирать
неизвестные изменения по рецепту live-cleanup. Требуется решение пользователя
по этим169 путям; остальные frozen/canonical проверки остаются отдельными.

### D22 — разрешён, оба STOP сняты (2026-11-03)

Только load_one guard: reject если одновременно пусты provides_tools,
internal_services,entrypoints; прежний error text, discover/R03 и остальной файл
побайтово сохранены. Actual red2 плюс exact empty-negative1→green3.
Первый mandate collector обнаружил потерянную финальную пустую строку patch tool;
она восстановлена, exact replacement proof:2749B SHA
a3a217d7bcecf5d303b2d8490cdd9b4a0edbd3cb5757af83aa51962d5bbb4ffe.
Expanded16/C19pins64green. Probe использует настоящий load_one перед _register.
Selfcheck read exit0/ok38unit/35corpus,tree exit0/ok23unit/22corpus;
contract28,layers568=563+3 production files+2 own corpus test files/0,
limits2warnings,security0; ни counter, ни limit не ослаблены.
Ровно169 UID признаны аудитором мусором наших прогонов и удалены по saved
bytes/SHA/mtime/ctime:raw3934/audit3899,dirs854,auditUID83. Новый контроль и точечная
уборка выполняются после каждого прогона. ADR-0006 не редактирован; поправка — долг
аудитора, точная строка решения в deviations. Стадия0/приёмка прежние.
Активное досье c25-d22-20261103/, старые closing SHA-досье read-only.

### D23 — inventory-only corpus разрешён, 7 пинов green

Actual non-live5225:7 inventory failures/5216passed/2true1314skip; snapshot1237:
1236matched/1difference (context tools26 vs27). Аудитор явно разрешил only
context/gather001 tools.count/names/effects.read и только SHA001 в manifest.
7 corresponding D19 inventory-pins теперь collect=executed7,7passed; другие
assertions/foreign fields/cases/native reference побайтово прежние.
001 now SHA c25232cdfec9de71a1941970c642b7c74968a071a0f07c7479d1de4f8af12491;
точный before/after/EOL proof во внешнем d19-d23-inventory-proof.json.
Следующее: два полных green non-live→snapshot1237→44→gates→live→M/P→records/SHA.

Final-byte correction own tree007: recorder []→None был несогласованной ошибкой,
native [] сохраняет каталоги и выбирает0files. Actual recapture/red1→green1;
own corpus22/unit23 unchanged. Probe path invariant усилен на JSON path values
(Windows escaping больше не обходит проверку),400lines. Теперь повторяется весь
маршрут на final bytes; read38/35 и publicread28 периметр прежние.

### Final C.25 — готов к независимому аудиту, не принято

Actual final selfcheck exit0/ok: unit38passed, corpus35matched. Два полных
nonlive final collect=executed5225 each:5223passed/2genuine1314skips/0failed/errors;
snapshot1237=1180+35+22 all matched. Fresh44:29ok/15existing skeleton blocked;
resource503/271,file_refactor124/52,split_py583/107,split_gd625/102 и C19counts
128/26,247/65,116/40 неизменны. Common gates568=563+3prod+2ownmoduletests,0violations,
2existingwarnings;contract28 (onlyread),security0. Standalone gates тоже exit0.
Final live3passed/no skips:335→419→335 exact,project958b3a92…;UID cleanup per-step.
M1policy/M2absolute path/M3noise: каждый actualred1→copyfile restoredgreen1,
SHA+EOL exact; M2 теперь ловится ownres:// pin. P1 BOM/EOL/Unicode exactraw,
P2repeatresponsesbyteexact,P3 audit3899=3828+71files/835=833+2dirs/UID83/debris0.
Native947/foreign27artifacts/parity/stages/ADRs exact; old FS methods byteexact,
onlylist_entries added. WORKLOG binaryCRLFprefix exact. Tree remains private;
не менялись stage0/ported/acceptance. Следующее: независимый аудитор handoff/SHA.

Closing base drift после P3: параллельно появился защищённый auditor-next prompt,
не записанный портером. Source сохранён, отсутствовал в baseline; witnessSHA/
timestamps в досье. Дельта C25 остаётся71auditfiles (3899); actual3900=3899+1
externalprompt,dirs835/UID83/debris0 прежние. Это не расширение мандата среза.

### C.25 — принят аудитом 2026-11-03 (сессия 77)

Приёмка — только моими прогонами:

- `selfcheck project_text.read` ×2 с бэкапом всех 44 отчётов и возвратом
  байт-в-байт: verdict ok — unit 38, corpus 35/0, layers 568/0, limits 568/2,
  contract 28/0, security ok.
- Полный non-live: 5225 collect=executed (5223 passed, 2 genuine 1314 skips);
  `snapshot_diff` ×2 — «кейсов 1237, расхождений нет» (`project_text/read 35/35`).
- Гейты отдельно: contract 28/0, lint_arch 568/0, check_limits ok/2, security ok.
- Live 3/3 passed, project.godot 335→419→335 побайтно, SHA `958b3a92…` точен,
  новые `.gd.uid` удалены, `__pycache__` в `python/` 0.
- Своя мутация: `truncated: len(text) > max_chars` → `False` в `domain/core.py`
  красит ровно `test_native_character_projection[я🐉-2]` — пин, что truncation
  считается в символах, не в байтах; восстановлено байт-в-байт, после 3/3 green.
- Периметр: публичный инструмент `read` (`provides_tools=("read",)`,
  `requires_ports=("project_text_fs",)`), артефакт `contract/capabilities/read.json`
  — 28-й артефакт контракта.

Записи аудитора: строка `project_text.read` 0→7, `parity.md` → `ported`,
блок C.25 в `PROGRESS.md`, WORKLOG append CRLF.

