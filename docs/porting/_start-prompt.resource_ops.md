# C.23 — `editing.resource_ops`: правка `.tres` через воронку записи

Ты — **портер**. Работаешь только в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Этапы сам себе не ставишь, «выполнено/принято/ported» не пишешь, `_audit-handoff.md`,
статусы ADR и таблицу механик не правишь. Приёмка — только моими прогонами.
Сдаёшь строкой «C.23 готов к независимому аудиту, не принято».

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` (в корне плагина; `docs/porting/RULES.md` **не существует**):
   R-02, R-03, R-05, R-09, R-11, R-12, R-13, R-16, R-20, R-22.
2. `docs/architecture.md`, `docs/PORTING.md`, `docs/security/invariants.md` (все SEC, особенно
   SEC-21/SEC-22), `docs/deviations.md` (разделы C.20–C.22 — твои прошлые отклонения).
3. ADR-0005 (транзакционный протокол), ADR-0006 (контракт → артефакт), ADR-0013 (длительности не
   контракт), ADR-0015 (create/delete в воронке), **ADR-0016** (raw transfer, `replace_raw`,
   `dir_case`, фазовый WAL) — принят аудитором.
4. Листы `docs/porting/editing.split_py.md` (C.20) и `editing.file_refactor.md` (§10, D1–D13) —
   как оформляются решения и «Намеренная граница».
5. Скелеты: `python/modules/editing/resource_ops/{module,tools,app,__init__}.py`,
   `domain/core.py`, `tests/test_core.py` — все TODO-заглушки, `ModuleSpec` закомментирован.
6. Воронка: `python/modules/editing/shared/funnel.py` (preflight, `EFFECT_INTENT`, компенсации),
   `shared/script_edits.py` (ops `script_edit`/`create`/`delete`/`move`/`dir_case`/`replace_raw`),
   `editing/write_apply/app.py`, `editing/write_preview/app.py`, `editing/rollback/*`,
   `substrate/fs/{disk_fs,memory_fs,atomic_write}.py`, `substrate/store/*`.
7. Эталон `D:\vajno\Godot\random-game\addons\godot_agent\python\godot_tools\resource_actions.py` —
   **19 642 B, sha256 `edef33817b0f5e9a9885dae55648b2c0c01fa2a8f908c07b10007fa1ff7fbbc5`**
   (этот же SHA обязан совпасть у копий в `yandex-game-dev` и `_agent_backup`; если нет — STOP).
   Карта: `ResourceActionError:14`, `_MEMBER_RE:19`, `_CLASS_RE:20`, `_THEME_TYPES:21`,
   `_INTERPOLATION:22`, `_UPDATE_MODES:23`, `_THEME_VALUE_TYPES:24`, `_exact:30`, `_text:41`,
   `_number:47`, `_path:58`, `_target:75`, `_tagged:87`, `_normalize_operation:131`,
   `normalize_action:249`, `_operation_dependencies:301`, `canonical_digest:322`,
   `file_sha256:328`, `prepare:333`, `public_prepared:344`, `operation_summary:349`.
   **Функции apply в этом файле нет** — где живёт применение, выясняешь пробами (§10.1), а не догадкой.
8. `docs/mapping.md:31` (`project_ops.resources` → `editing.resource_ops`), `:66` (строгая схема
   правок `.tres`: sub_resource, theme, операции, canonical digest, хэш-гвард), `:120`
   (`agent_resource_executor.gd` — редакторская половина: temp-save, UID, копирование/переименование),
   `:157` («что не надо делить»: `resource_actions` не дробить).
9. Промпты `docs/porting/_start-prompt.split_py_apply.md` и `_start-prompt.file_refactor.md` —
   §9 (уроки) и §10 (форма preflight) обязательны как образец.

## §0 База (снята аудитом, сессия 76, 2026-11-02 — не пересчитывать)

- non-live: **4483** теста, 0 падений/ошибок/пропусков (мой junit `4483/0/0/0`, 135.6 с; время — не контракт).
- snapshot: **909/909**; внутри `editing/file_refactor 52/52`, `editing/paths_preview 25/25`,
  `editing/split_py 108/108`.
- selfcheck: `editing.file_refactor` ok (124 unit / 52 corpus), `editing.paths_preview` ok (58/25),
  `editing.split_py` ok (583/107), соседи без сдвига: `split_gd 625/102`, `class_api 128/26`,
  `node_info 247/65`, `tree 116/40`, `check 188/75`, `api_check 206/52`, `gd_lint 126/37`,
  `tscn_lint 315/65`. Отчётов **44**, canonical не правятся руками (ADR-0013).
- contract: **27** артефактов (28 файлов в `contract/capabilities`, `_template.json` не артефакт).
- гейты: `lint_arch` 558 ok, `check_limits` 558 (1 информационное — `editing/split_py`: 11 элементов),
  `security_audit` ok.
- дерево: **3436 файлов / 813 каталогов / 83 audit-UID / 42 промпта**; `project.godot` 335 B,
  sha256 `958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
- ADR **16** (0016 принят), правил 22, PROGRESS — 45 строк этапа = **25 / 1 / 19**
  (строка `editing.resource_ops` = **0**), WORKLOG **625 476 B**, исторический префикс **4479 CRLF**
  — писать только `ab`, без нормализации EOL.
- C.22 принят: `move`/`dir_case`/`replace_raw`, `EFFECT_INTENT`, аддитивный `funnel.preflight`.

## §1 Границы среза

Срез — механика `editing.resource_ops`: строгая схема правок `.tres` (`normalize_action`,
`canonical_digest`, `file_sha256`, `prepare`, `public_prepared`, `operation_summary`) и запись
результата **только через общую воронку**. Редакторская половина (`agent_resource_executor.gd`,
temp-save через EditorPlugin, `ResourceSaver`) в срез **не входит** — это редакторская ветка.

Разрешённые файлы (закрытый список; всё прочее — STOP по §6):

| что | зачем |
|---|---|
| `python/modules/editing/resource_ops/**` | модуль среза (`module/tools/ports/domain/app`) |
| `contract/capabilities/resource_ops.json` | артефакт контракта, **28 → 29 файлов = 28 артефактов** |
| `tests/py/{contract,integration,formats,security}/test_resource*` | новые тесты |
| `fixtures/corpus/editing/resource_ops/**` + `manifest.json` | корпус, формат — как у соседей |
| `docs/adr/0017-*.md` | новый ADR **proposed**, если понадобится (см. §10.5) |
| `docs/porting/editing.resource_ops.md`, `docs/tests-map.md`, `docs/parity.md`, `docs/PROGRESS.md`, `docs/WORKLOG.md` | записи среза (`WORKLOG` — `ab`, CRLF) |
| `docs/deviations.md` | отклонения среза, закрытым списком |
| `python/modules/editing/shared/*`, `editing/write_apply/app.py`, `editing/rollback/*`, `substrate/fs/*` | **только** если новый op/порт объективно нужен; такое расширение требует моего согласия (§10.5) |

Запрещено: `editor/**`, `contract/editor_verbs.json`, `_audit-handoff.md`, `tools/selfcheck.py`,
`reports/selfcheck/*.json` руками, чужие корпуса и их манифесты, `project.godot`, `.gd.uid` вне
`fixtures/`, `__pycache__`/`.pyc`/`.bak`/временные файлы в дереве, статусы ADR, таблица механик.

## §2 Контракт правки

2.1. **Поведение эталона — источник истины.** Переносишь литерально: наборы констант
(`_THEME_TYPES`, `_INTERPOLATION`, `_UPDATE_MODES`, `_THEME_VALUE_TYPES`), регулярки
`_MEMBER_RE`/`_CLASS_RE`, порядок валидации `_exact`/`_text`/`_number`/`_path`/`_target`/`_tagged`,
разбор операций `_normalize_operation:131`, зависимости `_operation_dependencies:301`, digest
`canonical_digest:322` (канонический JSON, порядок полей значим), `file_sha256:328` по **raw**
байтам, `prepare:333` и `public_prepared:344` (публичная форма без внутренних путей), тексты
отказов — дословно, с исходными номерами строк в листе.

2.2. **Запись только через воронку.** Модуль не пишет файлы сам: `domain` считает
`(текст/байты, ожидаемый sha256)`, `app` собирает `Step`-ы и отдаёт их в общий
`write_preview` → `write_apply`. Для правки `.tres` решаешь по пробам §10.2, чем это выражать:
`script_edit` (текст, нормализует EOL — помни урок C.22 про 152 B против 149 B) или
`replace_raw` (сырые байты). Выбор обязан сохранять BOM, CRLF и одиночный CR байт-в-байт.

2.3. **Хэш-гвард.** `expected_hash` в плане — raw sha256 текущего файла; расхождение → `stale_plan`,
не «перечитаем и поправим». `canonical_digest` в ответе считается по канонической форме
нормализованного действия и не зависит от форматирования входа.

2.4. **Ничего не изобретать.** Если `mapping.md` противоречит эталону — это стоп-условие, а не
повод выбрать «как логичнее». Схема ответа — строгая, лишних полей нет, `additionalProperties: false`.

2.5. **Публичный периметр — по факту native.** Срезаешь ровно то, что native объявляет
(§10.1). Если native регистрирует инструмент — контракт растёт на 1 артефакт; если нет —
контракт остаётся **27**, а механика входит вклад-ом в уже принятые инструменты, и это
записывается в «Намеренную границу».

## §3 Шаги

**0. Долги прошлых срезов (мои, не твои — только эти три пункта):**
   * ячейка `editing.file_refactor` в таблице механик: **0 → 7** (C.22 принят); формат таблицы не ломать;
   * `docs/parity.md`: запись `editing.file_refactor` → `ported` с датой приёмки 2026-11-02;
   * `docs/tests-map.md`: строки для тестов C.22 (`test_file_refactor*`, `test_native_corpus`-набор,
     security-файл) с числом тестов, старые строки не двигать.

**1.** Лист `docs/porting/editing.resource_ops.md` из `_template.md`: цель, старый код (карта функций
с номерами), старые тесты, корпус, спецификация, SHA256 до правки.

**2.** §10: пробы и ответы до первой строки production (см. ниже). STOP до моего ответа.

**3.** ADR (если §10.5 покажет необходимость) — `proposed` **до** первого production-байта.

**4.** Red-тесты по R-16: кейсы из старых тестов эталона + новые на каждый отказ; прогон красный,
junit наружу, SHA в лист.

**5.** Production: `domain/core.py` (чистые правила схемы), `domain/<...>.py` по необходимости,
`ports.py` (только чтение через `fs`), `tools.py` (`ToolSpec` — если public), `app.py` ≤ 80 строк
оркестрации, `module.py` с `ModuleSpec` и вкладом в воронку.

**6.** Корпус `fixtures/corpus/editing/resource_ops/**`: успешные операции по каждой группе
(theme/sub_resource/свойства), `.tres` с BOM и CRLF, одиночный CR, отсутствующий файл,
не-`.tres` путь, занятая цель, устаревший hash, каталог вместо файла, `res://../` выход,
`addons/**` (включая `ADDONS`), `plugin.cfg`, `project.godot`.

**7.** Контракт: `contract/capabilities/resource_ops.json` — строгая схема входа/выхода, ошибки
(`invalid_input`, `not_found`, `conflict`, `stale_plan`, `denied`, `internal`), `effects="write"`,
`idempotent=False`, `requires_preview=True`.

**8.** Двойной прогон: non-live целиком (collect == executed), `snapshot_diff`, все selfcheck,
`lint_arch` / `check_limits` / `security_audit` / `gen_contract --check`, live 3 по рецепту
(`project.godot` 335 → 419 B, возврат побайтово, удалить только созданные `.gd.uid`).

**9.** Записи: лист, `tests-map`, `parity`, `PROGRESS`, `WORKLOG` (`ab`, CRLF), `deviations`
(если есть отклонения). SHA-таблица — **последней**.

## §4 Решения, которые уже приняты (не переспрашивать)

1. **Запись — только воронкой.** Свой `open`/`os.replace`/`shutil` в модуле запрещён: R-12,
   проверяется грепом и `security_audit`.
2. **Схема ответа строгая**, публичная форма — без абсолютных путей и без raw-байтов (R-15):
   если native их отдаёт, это отклонение в `deviations.md`, а не тихий перенос.
3. **Порядок отказов** — как в эталоне, дословными текстами; наш `kind` маппится
   (`invalid_input`/`not_found`/`conflict`/`stale_plan`/`denied`/`internal`), текст — по эталону.
4. **`tools/selfcheck.py` не меняется.** Три дельты C.19 и вклад C.22 остаются как есть.
5. **JSON-отчёты не правятся руками** (ADR-0013); длительности — не контракт.
6. **Стадии не двигаешь**, `ported` не пишешь, `ADR` не активируешь.

## §5 Доказательства (обязательный минимум)

* **M1** — снять хэш-гвард (`expected_hash` пустой/игнорируется): обязан покраснеть кейс
  «файл изменился после плана» (`stale_plan`).
* **M2** — валидировать `_MEMBER_RE`/`_CLASS_RE` как «просто str»: краснеют кейсы недопустимых имён.
* **M3** — записать `.tres` не тем способом, что выбран в §10.3 (например `script_edit` при
  выбранном `replace_raw`): краснеет кейс побайтового равенства с BOM/CRLF.
* **P1** — подложка: готовый целевой файл до apply → `conflict`, исходник не тронут.
* **P2** — повторный apply того же плана → `stale_plan`, дерево байт-в-байт.
* **P3** — гигиена: дерево = база 3435 + прирост среза, `.gd.uid` = 83, debris 0, `__pycache__`/`.pyc`/`.bak` нет.

Каждая мутация: красный junit, затем источник восстановлен **побайтово** (sha + EOL).

## §6 Стоп-условия

1. SHA эталона не совпал с §0/списком копий.
2. `mapping.md` противоречит эталону (`project_ops.resources` против фактических имён/поведения).
3. Пробы показывают, что нужный op/порт в воронке отсутствует и его нельзя добавить без правки
   принятых тестов или без моего решения.
4. Числа §0 не сходятся с фактическим состоянием репозитория.
5. Требуется правка запрещённого файла, `tools/selfcheck.py`, `editor/**`, статуса ADR,
   таблицы механик или `_audit-handoff.md`.

Стоп оформляется как «STOP §6: …», с досье наружу, без единого production-байта.

## §7 Что будет проверять аудитор

Своими прогонами: non-live целиком, snapshot, все selfcheck, гейты, `gen_contract --check`;
своей проекцией SHA; своими мутациями (не только твоими) и своей подложкой; побайтовым
равенством `.tres` после apply; чистотой дерева и UID; отсутствием IO в `domain`; соответствием
текстов отказов эталону; тем, что корпус соседей и отчёты не сдвинуты; записями (лист,
`deviations`, `parity`, `PROGRESS`, `WORKLOG` с целым префиксом 4479 CRLF).

## §8 Финальный прогон и записи

В отчёте: число тестов и collect == executed, время (не контракт), junit SHA; snapshot «кейсов N,
расхождений 0» (база 909 + кейсы среза); 44 отчёта с указанием, какие изменены и почему;
contract 27 → 28 артефактов (или 27, если §10.1 показал «нет public»); гейты 558; live 3 с точной
последовательностью включения/возврата `project.godot`; дерево и UID после уборки; таблица кейсов;
M1–M3 и P1–P3 с SHA; SHA-таблица — **последней**; строка «C.23 готов к независимому аудиту, не принято».

EOL: `WORKLOG.md` — только `ab` + CRLF; остальные `docs/**` — LF; `\r\r\n` — ноль.

## §9 Ошибки прошлых срезов (не повторять)

1. Буква ≠ смысл: в C.19 промпт сказал `tree 128`, реальность дала `116`.
2. Приёмка, записанная в один файл (C.18 — только в §8 handoff), теряется; пиши во все места.
3. SHA сдачи, снятая **до** записей, устаревает (C.19: 3 из 7 путей); SHA-таблица — последней.
4. Живой прогон оставлял 162 `.gd.uid` в `fixtures/**`; после live проверяй 83 и убирай ровно созданные.
5. Числа, скопированные из handoff, а не из источника («19 механик» вместо 20, «ADR 13» вместо 15).
6. `\r\r\n` в handoff (79 строк) — при записи документов проверяй `crcrlf = 0`.
7. Руками править JSON-отчёты запрещено (ADR-0013).
8. Правка чужого «удобного» формата — вне среза (C.20, кейс `context/gather/001`).
9. Ослабленный пин без красного следа не принимается: изменение принятого теста — только с моим
   разрешением и с мутацией, доказывающей, что пин живой (C.22: `case = False` краснит `q2-parent-prepare`).
10. Адреса в промпте проверяй: `docs/porting/RULES.md` не существует, `_cli:792` в
   `file_refactor.py` нет, SHA из промпта может принадлежать соседнему файлу.

## §10 preflight-вопросы: код не писать до моего ответа

1. **Регистрация.** Что native реально объявляет: имена инструментов, вход/выход, `list_tools`
   и настоящий `call_tool` (MCP stdio, оба профиля). Подтверждаются ли фактически имена из
   `mapping.md:31`/`:66`; есть ли парный к `paths_preview` публичный инструмент ресурсов.
2. **Apply.** Где живёт применение `prepare` (в `resource_actions.py` его нет): `transaction_actions.py`,
   `agent_bridge.py`, `agent_resource_executor.gd`? Кто пишет файл, кто считает квитанцию, как
   выглядит план и откат; дословные тексты и порядок проверок.
3. **Байты.** Как эталон сохраняет `.tres` (текст / `ResourceSaver` / temp-save), что происходит
   с BOM, CRLF, одиночным CR, хвостовым переводом строки; правятся ли `uid://` и `sub_resource id`.
   Какой наш op это выражает — `script_edit` или `replace_raw` — и почему.
4. **Схема.** Полный перечень операций и их полей, ограничения значений (`_THEME_VALUE_TYPES`,
   `_INTERPOLATION`, `_UPDATE_MODES`), что такое `_tagged` и `_target`, как формируется
   `public_prepared`, что попадает в `operation_summary` и `canonical_digest`.
5. **Периметр и ADR.** Нужен ли новый op/порт в воронке или новый ADR-0017 (и о чём именно);
   достаточно ли `script_edit` + `replace_raw` из ADR-0016; какие отклонения от native неизбежны
   (порядок, публикуемые поля, ограничения редакторской ветки).
6. **Политика.** Как эталон трактует `addons/**` (включая `ADDONS`), корневой `plugin.cfg`,
   `project.godot`, `.agent_history`, выход за проект; что из этого `guard_path`/`guard_transfer`
   уже покрывает, а что требует отдельного решения.
7. **Корпус и старые тесты.** Какие тесты эталона станут источником кейсов (R-16), сколько их,
   какие кейсы снимать actual-native и в каком формате (как в C.21/C.22: payload + SHA + байты фикстур).



