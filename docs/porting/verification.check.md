# verification.check — C.9, агрегатор `verify`

**Статус:** этап 7 — принято аудитом 2026-10-30 (сессия 61); **C.13 (вклад `api_check`, F2/F3) принят аудитом 2026-10-31 (сессия 65).**
**Обновлено:** 2026-10-30.

## Цель

Read-only проверка одного пути инструментом `verify`: пять текстовых видов
`gd`, `tscn`, `py`, `json`, `cfg`, фактически выполненные `kinds`, честные
`checked` и `unavailable`. Основание: `_start-prompt.verification_check.md`.
Имя `check` принадлежит принятому C.8; его карточка не переименовывается.

## Старый код

Эталон: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/`,
HEAD `ba0535d4dec43c32750e601a6ca86e377abc6af3`, подтверждён `git rev-parse HEAD`.

| Файл | Что делает | Граница |
|---|---|---|
| `python/tools/agent_bridge.py:1173–1264` | `_check_one_path`: текстовые проверки и headless-отчёт | эталон одиночного пути, съёмка с `validation: off` |
| `python/tools/agent_bridge.py:1267–1279` | `_unchecked_reason` | дословные причины отсутствия проверки |
| `python/tools/agent_bridge.py:1301–1343` | `cmd_check`, единственный прочитанный caller | CLI, batch-счётчики и rc вне среза |
| `python/godot_tools/gd_lint.py`, `tscn_lint.py` | принятые линтеры | переиспользовать; принятые `domain/` неизменны |

## Старые тесты

Строки `docs/tests-map.md` имеют судьбу `corpus`; сами старые тесты не запускались.
Корпус C.9 снят; закрытие целых CLI/headless-строк не заявляется.

| Файл | Семейство | Судьба | Наблюдения и граница |
|---|---|---|---|
| `repro_check_unchecked.py` | repro | corpus | неподдерживаемые расширения, headless-only, `checked`/reason; batch/rc отдельно |
| `repro_check_truncated.py` | repro | corpus | кейсы036/037, дефект хвоста и согласованная граница 2 Ми символов / 4 МиБ; CLI/timing отдельно |
| `repro_check_blocking.py` | repro | corpus | `off` относится к срезу; required/auto, blocking и rc исключены промптом |

Остальные строки агрегатора (answer_judge, action_disclosure, headless,
runtime и live) не объявляются покрытыми текстовым срезом.

## Корпус

Сняты **38 кейсов / 34 входных файла** в
`fixtures/corpus/verification/check/`, сырой `reference_result` от
`_check_one_path` на временных копиях, отдельно `expect.result` и отказы
контракта. `fixture_base: fixtures/projects`; входы внутри `check/project/`.
Одноразовый съёмщик и логи — только в одобренном temp.

Факт съёмки: `c9-resume-20261030/capture.py`, exit0/stderr0B. 35 сырых
`reference_result`, 2 действительных исключения (missing/addons) в
`reference_error`, без выдуманного dict; пути исключений нормализованы в
`<PROJECT>`. Пять отказов контракта. Кейс037 хранит и старую частичную проверку,
и результат старого `gd_lint` на полном тексте (одобренная граница размера).
Кейсы001–017 — пять видов/порядок/unsupported;018–022 — фильтр/отказы;
023–029 — кодировка/CRLF/пустота/без исполнения/shader/case;
030–035 — выбор видов/instance/отсутствующая зависимость;036–037 — размеры.

При финальной сверке покрытия обнаружено: кейс006 (незакрытая кавычка при
наличии `]`) — **слепая зона эталона**, а не диагностика заголовка. Его сырые
данные сохранены без изменений. Дополнительно снят кейс038 через тот же
настоящий `_check_one_path`: отсутствующий `]`, дословная проблема
«заголовок секции … не закрыт …», auto_fixable=false. Скрипт
`capture_header.py` и его SHA/bytes записаны в supplemental_capture манифеста.
Итого36сырыхdict+2исключения,5отказов. Первоначальные37записей остаются
побайтово прежними; production-код не менялся. После дополнения повторены
полный nonlive/collect/snapshot, весь mutation-scope, selfcheck и live3.

## Спецификация

- Источник контракта: §2 стартового промпта и согласованные B1–B5; `tools.py:VERIFY`.
- Имя `verify`, `effects=read`, идемпотентность; вход `path` и необязательный `kinds`.
- Результат: `path`, `problems`, `checked`, `auto_fixable`, `kinds`, `unavailable`;
  `unchecked_reason` только при отсутствии фактической проверки.
- Лимит: переиспользовать `kernel/limits.py:READ_TEXT_MAX_BYTES`, 4 МиБ.
- `.scn` не текстовая проверка; API/headless не выдавать за выполненные.
- Один владелец, вклады через `ctx.registry.contributions('verify')`.

## Решения по ходу

| Дата | Решение | Почему |
|---|---|---|
| 2026-10-30 | использовать `verify`, скелетное TODO `check` устарело | дублирование имени отключает обоих владельцев |
| 2026-10-30 | до согласования противоречий реализацию и корпус не начинать | стоп-условия §6; нельзя менять принятый код для подгонки под промпт |
| 2026-10-30 | пользователь разрешил B1–B5: gd-вклад вызывает собственный чистый `lint_gdscript(text)`, tscn-вклад — собственный `app.call` с существующими зависимостями/fs/api_cache | подтверждено двумя ответами инструмента question; принятые domain/app/card не меняются |
| 2026-10-30 | baseline gd126/37; разрешены SHA context manifest и имя интеграционного теста `test_verify.py` | прямое подтверждение пользователя |
| 2026-10-30 | >2 Ми символов при ≤4 МиБ проверяются целиком; >4 МиБ — invalid_input; blocking/CLI repro не закрываются текстовым срезом | пользователь подтвердил явную границу паритета и честную неполноту старых repro |

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-10-30 | восстановление контекста | лист отсутствовал; модуль остался скелетом, предыдущего кода C.9 нет |
| 2026-10-30 | чтение эталона, трёх repro и принятых приложений | выявлены противоречия интерфейсов и исходных чисел |
| 2026-10-30 | байтовая база до правок | 2035 файлов, 83 `.gd.uid`; копии и SHA в temp `c9-resume-20261030/before/` и `before.json` |
| 2026-10-30 | этап 1 | лист создан; требуется решение пользователя по блокерам |
| 2026-10-30 | этап 2 | actual-old capture37/33inputs, exit0/stderr0B |
| 2026-10-30 | этап 3 | ToolSpec записан; 78failed/1passed (пин манифеста) +11failed contract до кода; raw logs/red.xml в temp |
| 2026-10-30 | этап 4 | 90 новых тестов зелёные; первый selfcheck поймал запрещённый import json в domain; декодер json.loads передаётся из app чистой функцией, гейт не менялся |
| 2026-10-30 | этап 5 | selfcheck exit0/stderr0B: module/layers495/limits495/contract19/security/unit90/corpus37 все ok; обратная проекция11 разрешённых файлов совпала по SHA |
| 2026-10-30 | полная регрессия | 2427passed/0failed/0skipped; collect2427, XML2427, все node IDs совпали в порядке;86файлов; snapshot506/0, включая C.9 37/0 |
| 2026-10-30 | принятые соседи | gd126/37 и tscn315/65, оба selfcheck ok/exit0/stderr0B |
| 2026-10-30 | мутации | M1–M8/P2 красные, P1 contract и P3 lint_arch красные;11восстановлений copyfile/SHA/EOL; scope523 до/после зелёный |
| 2026-10-30 | live/probe | Godot4.6.3:3passed/0skip, exit0/stderr0; probe gd/tres exit0/stderr0;111новыхUID удалены,83старых SHA сохранены |
| 2026-10-30 | дополнение корпуса | №006 — старый blind spot; №038 снят actual-old для незакрытого ];38кейсов/34входа,36dict+2exceptions;код прежний |
| 2026-10-30 | повтор после №038 | 2428passed53.24s,collect2428=XML2428,полное совпадение node IDs/86файлов; snapshot507/0,C.9 38/0;exit0/stderr0 |
| 2026-10-30 | финальный контроль | selfcheck91/38ok;11мутаций scope524,восстановлено524passed;live3passed;2116files/83UID,12обратных проекций,вне whitelist0 |
| 2026-10-30 | этап 6 | портёр завершил срез; следующее действие — независимый аудит, приёмка не объявлена |

## Проверки

Первый исходный `python -B tools/selfcheck.py verification.gd_lint`:
`ok`, unit **126 passed**, corpus **37**, layers/limits **492**, contract **18**.
В stderr были 21 строки `recovery: ... action=expired`; этот запуск не
объявляется stderr-clean. В промпте ошибочно указаны unit37/corpus37.
Исходный `python -B tools/selfcheck.py verification.check` (exit **2**, stderr **0 B**):

```text
selfcheck verification.check
  module         not_implemented заготовка: RuntimeError: python.modules.verification.check.module: нет MODULE (R-05)
  layers         ok              файлов 492, нарушений нет
  limits         ok              файлов 492, предупреждений 0
  contract       ok              артефактов 18, расхождений нет
  security       ok              нарушений нет
  unit           not_implemented тестов модуля нет: python/modules/verification/check/tests
  corpus         not_implemented нет корпуса механики: fixtures/corpus/verification/check
вердикт: blocked
```

Отчёт: `reports/selfcheck/verification.check.json`. Сырой UTF-8 вывод:
`C:/Users/Lich/AppData/Local/Temp/opencode/c9-resume-20261030/owner.stdout.txt`.
Это вывод исходной заготовки; актуальный финальный selfcheck после восстановления мутаций:

```text
selfcheck verification.check
  module         ok              verification.check (verify)
  layers         ok              файлов 495, нарушений нет
  limits         ok              файлов 495, предупреждений 0
  contract       ok              артефактов 19, расхождений нет
  security       ok              нарушений нет
  unit           ok              91 passed in 3.49s
  corpus         ok              кейсов 38, расхождений нет
вердикт: ok
```

Exit0/stderr0B: `final-owner.stdout.txt` и `reports/selfcheck/verification.check.json`.
Предыдущий `owner-final` тоже дал ok, но напечатал8 recovery-expired строк/392B
stderr после первого live; он не объявляется чистым. Тогда чистый повтор дал
90/37, а таблица выше — финальный прогон после дополнительного кейса038.

## Мутации на предъявленных байтах — финальный прогон с кейсом038

Полный scope каждой строки: `python/modules/verification/{check,gd_lint,tscn_lint}`,
`tests/py/integration/test_{verify,gd_lint,tscn_lint}.py`,
`tests/py/contract/test_{verify,check}_contract.py`.
Collect524 = XML524 при каждом прогоне; до и после всех мутаций524passed.
Первый прогон523 с полными логами сохранён в `round1/`, его история — WORKLOG62.

| Мутация | failed / passed | Обязательный детектор |
|---|---|---|
| M1 checked=True | 13 / 511 | md/tres/scn |
| M2 problems строкой | 37 / 487 | кейсы с находками и схема результата |
| M3 убрать внутренние py/json/cfg | 12 / 512 | py_syntax/json_duplicate/cfg_duplicate |
| M4 auto_fixable=False | 1 / 523 | tscn_fixable |
| M5 unavailable=[] | 21 / 503 | gd/tres и отсутствующий вклад |
| M6 игнорировать kinds | 4 / 520 | filtered_gd |
| M7 обойти deny_reason | 2 / 522 | denied_addons и preflight fake FS |
| M8 reverse problems | 2 / 522 | gd_order и двойной вклад |
| P1 required без checked | 0 / 524 | **gen_contract exit1: устарел verify.json**; unit это не ловит |
| P2 tscn problems строкой | 7 / 517 | реальный registry/dispatch, tscn corpus |
| P3 чужой domain import | 0 / 524 | **lint_arch exit1: модуль импортирует чужой модуль** |

Каждая мутация выполнялась отдельно с `shutil.copyfile` backup/restore, сравнением
полных SHA256 и количества LF/CRLF; stderr0B. `mutations.json` содержит все
failing IDs, до/мутант/после SHA и вывод гейтов; ничего не переписано «по памяти».
Восстановленные SHA: core `f84018b8ee08ea4dd9526b76edf6b3bc97e8359f0ab8334d5e1a6f3762984d5f`,
app `4aff8a3f1c074e9e912376486f5e344778a2439c6743536912ddc9d207d3c32d`,
tools `65974f15aa55196c740548a577a37ff833d27421588b93f2dfbc29736ed6dce0`,
tscn tools с разрешённым вкладом `48391faf81a0c5fae0817a61e098823f196be96663630b0a36c338c29106f257`.

## Проверки клиента и живого редактора

- `probe.py verify --args-file probe-gd.json --project fixtures/corpus/verification/check/project/common`:
  две дословные проблемы, checked=true, kinds=[gd], unavailable=[api,headless].
- `probe-tres.json`: checked=false, kinds=[], дословный unchecked_reason, headless unavailable.
  Оба exit0/stderr0, сырые JSON в temp `probe-*.stdout.txt`.
- `pytest tests/py/live -vv`: **3passed**, XML3, без failures/errors/skips,
  реальный `Godot_v4.6.3-stable_win64_console.exe`; subprocess exit0/stderr0.
- Финальный live: до2116файлов/83UID, после2227/194, удалены ровно111 новых `.gd.uid` по census;
  итог2116/83. `live-proof.json`: оставшихся добавлений/удалений/изменений0,
  все исходные UID (включая8исторических parity) побайтово сохранены.

Все одноразовые скрипты, XML и UTF-8 логи находятся в
`C:/Users/Lich/AppData/Local/Temp/opencode/c9-resume-20261030/`.
Ключевые доказательства: `capture.py`, `capture_header.py`, `final-count-proof.json`, `mutations.json`,
`accepted-proof.json`, `live-proof.json`, `final-integrity.json`; исходники
эталона не используются новыми тестами и не менялись при съёмке.

## Границы правок и байтовые доказательства

- `final-integrity.json`: база2035 → **2116файлов**, добавлено81, изменено24,
  неизменно2011, удалено0; неожиданных правок/добавлений0, debris0;83UID с теми же SHA.
- **12 обратных проекций** SHA256: четыре разрешённых gd/tscn module/tools,
  context case+manifest, два contract inventory-пина, четыре integration-пина.
  Обратное удаление разрешённых добавлений даёт исходные байты, включая EOL.
- Все принятые domain/app/read_inputs, форматы, scene executor, schema,
  lint_arch/gen_contract/security_audit/snapshot_diff, `_audit-handoff.md` совпадают
  с before. Все18 прежних capability-карточек и `_template` совпадают;
  добавлена только `verify.json`. `editor_verbs`:version3, шесть примитивов.
- Новые файлы:73корпусных (38case+34input+manifest), пять code/test
  (ports,test_app,CheckKind,contract,integration), verify-карточка, лист, selfcheck-report.
  Из24изменённых два — генерируемые соседние selfcheck reports; остальные строго
  владелец, разрешённые12файлов и пять документов. Полные имена/SHA/bytes в inventory.
- PROGRESS/parity меняют только строку владельца; tests-map сохраняет168 старых
  строк (у трёх уточнено покрытие) и добавляет четыре новых тестовых файла/91кейс.
  Исторический префикс WORKLOG побайтово сохранён; deviations дополнен согласованной границей.
- `coverage-proof.json`: все первоначальные37case побайтово прежние;72пина
  корпуса (38case+34input) валидны; SHA обоих capture scripts и эталонного bridge совпали.

## Следующее действие

Независимому аудитору проверить C.9 по стартовому промпту и этому листу, повторив selfcheck/корпус, мутации и live; только после его вердикта возможен этап7/ported.

## Блокеры

**B1–B5 сняты пользователем 2026-10-30**; исходные формулировки ниже сохранены для истории.

| ID | Что мешает | Кто решает |
|---|---|---|
| B1 | §2.2 требует передавать текст в собственный `gd_lint.app.call`, но его контракт принимает только путь, а `app.py:25` всегда вызывает `fs.read_raw`; чистый `domain.core.lint_gdscript(text)` существует | пользователь: разрешить вызов собственного чистого линтера во вкладе либо другой явный интерфейс |
| B2 | принятый `tscn_lint.app.call` вызывает `read_inputs.gather`: `fs.is_file`, чтение instance-сцен и `api_cache.classes()`; запрет IO/портов во вкладах несовместим с этим повторным использованием | пользователь: разрешить существующее чтение зависимостей/API-кэша вкладом сцены или пересмотреть контракт |
| B3 | фактический baseline `gd_lint` unit126/corpus37, в §0/§3 указано 37/37; §6 требует остановки при отличии | пользователь: подтвердить baseline126/37 без изменения принятых тестов |
| B4 | разрешена правка context case001, но не его SHA в `context/gather/manifest.json`; `test_verification_check.py` не выбирается selfcheck (ищет `test_check*.py`/`test_verify*.py`) | пользователь: разрешить companion SHA и имя интеграционного теста `test_verify.py` либо иной явный способ включения |
| B5 | `validation off` не закрывает blocking repro целиком; диапазон >2 Ми символов, но ≤4 МиБ не получает новый oversized-отказ, хотя старый агрегатор обрезает его | пользователь: зафиксировать непокрытые ветки repro и полную границу отказа от старой частичной проверки |

Ни один блокер не является разрешением редактировать принятые `domain/`, карточку
`check.json`, общие инструменты или `_audit-handoff.md`.

## Приёмка аудитом (сессия 61, 2026-10-30)

- Пересъёмка корпуса **своим** скриптом через `agent_bridge._access_policy` + `_check_one_path`
  на копиях проектов: `reference_result` 38/38, независимая проекция 32/32, порт 38/38,
  5 отказов контракта сверены по `kind` (абсолютного пути в ответе нет), кейс 037 дополнительно
  сверен полным текстом через старый `gd_lint.lint_gdscript`.
- Дифференциал: 1172 файла `fixtures/**` в одинаковых временных копиях. 381 совпал по
  `problems`/`checked`/`auto_fixable`, 784 — обоюдный отказ политики, 1 — граница лимита,
  2 — `addons`-policy, 3 — BOM (F1).
- Свои мутации: 13 / 36 / 5 / 1 / 21 / 4 / 2 / 2 (+P2 6) красных; P1 виден только
  `gen_contract --check`, P3 — `lint_arch`. SHA после восстановления совпали:
  core `F84018B8EE08`, app `4AFF8A3F1C07`, tools `65974F15AA55`, tscn tools `48391FAF81A0`.
- Соседи без сдвига: `gd_lint` 126/37, `tscn_lint` 315/65, `formats/tscn.py` `9D69AFECDCC0`,
  `tscn_lint/domain/core.py` `F23EDD5A4ED9`. Живое 3 passed, 111 сгенерированных `.gd.uid`
  удалены, дерево 2116 файлов / 83 UID / debris 0.
- Граница приёмки: BOM (F1) не исправлен — унаследован от принятого C.2 и вынесен
  в `_audit-handoff.md` §5 отдельным долгом; `.scn`/`api`/`headless` не проверяются по паритету.

## C.10 / F1 — отдельный ремонт после приёмки C.9

2026-10-31 пользователь выбрал закрытие F1. Основной файловый вход verify
использует общий incremental utf-8-sig decoder с gd_lint; accepted CHECK
candidate и tscn instance не меняются. Старые38C.9кейс-файлов сохранены байтами,
добавлены24actual-old BOM-кейса и4candidate-oracle внутри них. Дельта сдаётся
отдельно: `docs/porting/verification.bom.md`, ADR-0008; стадия7 C.9 историческая,
дельта F1 ещё не принята, аудиторский handoff не редактировался.

## Продолжение C.13 (вклад `api_check`)

**Состояние:** работа начата 2026-10-31; историческая приёмка C.9/этап7
сохранена. C.13 не принят; приёмка остаётся независимому аудитору.

### Цель и границы

Закрыть обход C.9: `.gd` проверяется линтером, затем API через вклад
`CheckKind('api', ('.gd',), …)`, а не прямой вызов внутри владельца.
F2: `API_CHECK.errors = ('invalid_input', 'denied')`, только это поле карточки.
F3: точные причины из §2.3.6, без ложного Godot-only текста на текстовых
расширениях. F4/селектор selfcheck остаётся вне среза.

| Старый код | Действие C.13 |
|---|---|
| `agent_bridge.py:1199–1206` | вклад `gd`, затем `api`; владелец задаёт ORDER |
| `gd_api_check.py:145–201` | принятую механику вызываем через собственный app; MAX6 не меняем |
| `_unchecked_reason:1267–1279` | прежние сообщения headless/unsupported сохраняем; F3 исправляет текстовый фильтр |

### Корпус и спецификация

62 прежних наблюдения не переснимаются/не меняются; только разрешённая
перепроекция `expect.result`. Добавляем ≥8 actual-old кейсов с маленьким
рукописным кэшем `Node2D → CanvasItem → Node → Object`: lint+API порядок,
API-only finding, чистый API, неизвестная база/no_extends, фильтры api/gd,
дубли kinds, отсутствие кэша и внутренние лимиты.
FRAGMENT получает необязательные checked/unavailable с умолчаниями True/[];
checked — any; unavailable вкладов дословно, перед расширенческими записями.
Проблемы не обрезаются владельцем; неизвестный ORDER-kind — internal.

### Уточнения пользователя до правок

- P1: обязательный точный пин errors сохраняется. Мутация доказывается
  красным gen_contract, зелёными unit/integration и отдельным ожидаемым
  падением контрактного пина; весь набор при P1 зелёным не называется.
- Единственная дополнительная перепроекция: `032-only_headless.json`
  (.tscn, kinds=['headless']), только `expect.result.unchecked_reason`
  по точной F3 плюс SHA/bytes в manifest. Raw reference/headless запись
  не меняются; принятый tscn_lint не затрагивается.
- Формулировку §3.7 «вклад принят C.13» не используем: §0/§8 запрещают
  портеру принимать собственный срез.

### Доказательства и следующее действие

Внешний byte-backup/evidence:
`C:/Users/Lich/AppData/Local/Temp/opencode/c13-verify-api-20261031-7f4d9b2c/`.
Fresh preflight: **2310 файлов / 83 .gd.uid** без cache/godot каталогов.
Полный baseline сохранён в `before/` и `before.json` до первой правки.

Корпус до кода: `capture.py` exit0/stderr0, **62 raw неизменны / 19
перепроекций / 13 новых actual-old / всего75**. Новые наблюдения включают
реальную конкатенацию 8 lint + 6 API. Тесты C.13 написаны до production-кода.

Красный прогон до production: **56 failed / 116 passed**, exit1/stderr0.
Реализованы вклад и агрегация; app владельца не менялся. Первый зелёный
прогон выявил ошибку нового теста: MCP-представление не содержит effects;
проверка перенесена на зарегистрированные ToolSpec. Companion api_check
integration меняет только обязательный пин contributes_to.

Первый полный прогон: snapshot622/0, unit-срезы183/206/126/315/186;
non-live2861 passed/1 failed (инвентарь новых GD-фактов). Все selfcheck
были fail из-за чужих импортов в новых unit-тестах; это ошибка тестового
слоя, не разрешение расширять lint_arch. Исправлено: unit использует
CheckKind-стабы, настоящие вклады проверяются в integration.

Узкие companion-правки вне исходного списка, **явно разрешены пользователем**:

- `tests/py/integration/test_api_check.py`: единственный пин
  `contributes_to=()` → `('verify',)` (ошибка исходного разрешения «только errors»).
- `fixtures/corpus/scene_model/scene_deps/manifest.json`: ровно7 новых
  actual-old script_facts для новых фикстур C.13. **133 старых факта и все
  остальные поля неизменны**, source/bytes/SHA сняты старым extractor;
  тест охвата и production scene_deps не меняются.

### Итог C.13 — готов к независимому аудиту, не принято

Повтор после исправлений и точного восстановления мутаций:

| Доказательство | Итог |
|---|---|
| Fresh actual-old пересъёмка | raw75/75; независимая проекция70/70 успешных; port75/75; 5 typed refusals отдельно |
| `pytest --ignore=tests/py/live` | **2874 passed**, 99 файлов, stderr0, 72.13s; collect2874/2877 +3 live |
| Настоящий editor/headless live | **3 passed**, 0 skipped, 28.11s, stderr0 |
| `snapshot_diff` | **622/0** = 609 baseline +13 новых; соседние корпуса unchanged |
| `selfcheck verification.check` | **ok**, unit188, corpus75/0 |
| `selfcheck verification.api_check` | **ok**, unit206, corpus52/0 |
| `selfcheck verification.gd_lint` | **ok**, unit126, corpus37/0 |
| `selfcheck verification.tscn_lint` | **ok**, unit315, corpus65/0 |
| `selfcheck engine_kb.class_api` | **ok**, unit186, corpus26/0; F4 selector frozen |
| Контракт/слои/лимиты/security | 21 artifacts/0 drift; 502/0 violations, 502/0 warnings; SEC ok |
| Probe verify lint_api.gd | exit0; kinds gd,api, два literal findings lint→API, checkedTrue |

Фрагмент настоящего вывода финального selfcheck (полный stdout снаружи):

```text
selfcheck verification.check
  layers         ok              файлов 502, нарушений нет
  limits         ok              файлов 502, предупреждений 0
  contract       ok              артефактов 21, расхождений нет
  security       ok              нарушений нет
  unit           ok              188 passed in 5.86s
  corpus         ok              кейсов 75, расхождений нет
вердикт: ok
```

Дифференциал **через verify**: все385 GD в75 project roots × свой кэш/реальный
кэш2 004 630B (`7352d27c8d8ed77b84b3b98400093c85144c4b6f8b8919b147ca035a67c8a93c`)
=770 вызовов, **0 расхождений**, все project bytes неизменны. 510 буквальных
сравнений; 260 явно записанных границ: 256 denied:addons, 2 approved4MiB,
2 approved full-text против старого 2Mi-char обрезания. Для последних
сверены полные **старые** lint+API scanners, raw truncated ответ сохранён.
Oracle agent_bridge/gd_api_check/gd_lint/cache bytes заморожены.

Последовательные byte-backed мутации, suite164tests: M1 ORDER31 fail;
M2 checked22; M3 fragment availability25; M4 F3 literal12; M5 problems string34;
M6 omitted checked4; M7 unsorted select31; M8 dropped availability24.
P1 errors rollback: gate exit1 `устарел: api_check.json`, behavioral357 passed,
отдельно exact-pin1 failed (разрешённое уточнение; не весь suite green).
P2 domain import os/P3 owner foreign domain: lint_arch exit1 с точной причиной,
behavioral357 passed каждый. **11/11 обнаружены, каждый SHA/bytes до=после,
finally restore; чужие процессы не убивались**. Полные JUnit и proof JSON
для каждой мутации сохранены. Служебная сводка сначала была перезаписана
метаданными одноимённого subprocess label; восстановлена из 11 неизменных
individual proof JSON в `mutations-summary.json` (не перепрогон/подмена).

Изменения: owner domain; APItools errors+adapter, module contributes_to;
shared CheckKind только docstring; check tests/verify integration/F2 pin;
19 старых expect-проекций (включая отдельно разрешённый032), manifest,
13 новых actual-old кейсов и10 fixture inputs; две разрешённые companion
правки, документация. Пять `reports/selfcheck/*.json` — свежие **сгенерированные
выводы обязательных selfcheck**, не изменения поведения соседей.
Полный перечень каждого нового/изменённого файла, bytes и **полный SHA256**:
`C:/Users/Lich/AppData/Local/Temp/opencode/c13-verify-api-20261031-7f4d9b2c/changed-files.md`;
машинный `scope-verdict.json` содержит before/after пины и511 frozen файлов.

Frozen byte proof: accepted gd_lint/**, tscn_lint/**, API app/domain/**,
source_text, engine_kb/**, check app/tools, check/verify карточки,
kernel/substrate/tools/editor, editor_verbs, context corpus и tscn inventory
неизменны; lint_arch SHA
`a6c5edd4765072d11df8ac8b60da5f40d39290fe43cf108f54e7fcd3f6b9aff7`.
APIcard parsed delta — только errors, inventory20 unchanged; original raw62
и все поля вне expect.result неизменны. Исторические stage7/ported сохранены;
`_audit-handoff.md` и исходный C.13 prompt не правились.

Гигиена: baseline2310 →2333 файла (+23 новых case/fixture files), UID83 →194
→83 (удалены ровно111 **измеренных новых live UID**, 8 исторических сохранены),
debris0 (cache/bak/tmp/orig/zz). Принятые доказательства C.12 снаружи не тронуты.

**Следующее действие:** независимый аудитор заново проверяет C.13 по этому
листу и исходному prompt; только он решает приёмку. Портер её не объявляет.

## Приёмка C.13 аудитом (сессия 65, 2026-10-31)

Историческая приёмка C.9 выше не переписана; ниже — доказательства дельты C.13.

| Проверка | Итог |
|---|---|
| Пересъёмка корпуса своим скриптом (живой `_check_one_path`, `_cache` reset) | `reference_result` **75/75** |
| Независимая проекция (свои lint + API по отдельности, затем конкатенация) | **70/70** |
| Порт `verify` против `expect` (+5 typed refusals по `kind`, идемпотентность) | **75/75** |
| Дифференциал: 384 `.gd`, 75 корней, 2 режима кэша (второй — реальный 2 004 630 B / 1488 классов) | 512 вызовов: 510 совпало, 254 обоюдных отказа, 2 лимита, 2 — граница 2 Ми символов (`between.gd`) |
| Свои мутации | M1 31, M2 22, M3 24, M4a 4, M4b 8, M5 34, M6 4, M7 31, M8 24; P1 — 1 тест + `gen_contract` `fail: api_check.json`; P2/P3 — `lint_arch`; восстановление побайтово |
| Гейты | non-live **2874**, collect 99; live **3** (29.4 с); snapshot **622/0**; contract **21**; selfcheck `check` **188/75**, `api_check` 206/52, `gd_lint` 126/37, `tscn_lint` 315/65, `class_api` 186/26; слои/лимиты 502/0; security ok |
| Гигиена | дерево 2333, `.gd.uid` 83 → 194 → 83 (удалены ровно 111 сгенерированных), debris 0 |

F2 закрыт (`api_check.json` отличается только строкой `denied`), F3 закрыт (три формы
причины, Godot-only текст остался у расширений без текстового канала). Долг **F4**
(селектор `tools/selfcheck.py:215`) остаётся открытым и в срез не входил.
