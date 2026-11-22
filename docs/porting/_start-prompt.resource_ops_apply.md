# C.24 — `editing.resource_ops`, вторая половина: применение `.tres` через воронку

Ты — **портер**. Работаешь только в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Этапы сам себе не ставишь, «выполнено/принято/ported» не пишешь, `_audit-handoff.md`, статусы ADR
и таблицу механик не правишь. Сдаёшь строкой «C.24 готов к независимому аудиту, не принято».
Приёмка — только моими прогонами.

## Читать до первой строки кода

1. `AGENTS.md`, `RULES.md` в корне плагина (`docs/porting/RULES.md` не существует):
   R-02/03/05/09/11/12/13/16/20/22.
2. `docs/architecture.md`, `docs/PORTING.md`, `docs/security/invariants.md` (SEC-21/22/**23**),
   `docs/deviations.md` (C.22 и **C.23**).
3. ADR-0005/0006/0013/**0015/0016** (принят); ADR-0017 ещё **не существует** — его создаёшь ты.
4. Лист `docs/porting/editing.resource_ops.md`: §10 (семь ответов), **§10.5 D14–D16**, **§11 D17**.
5. Код C.23: `python/modules/editing/resource_ops/**` (prepare-половина, порт, `ports.py`).
6. Воронка: `shared/funnel.py` (ops `script_edit/create/delete/move/dir_case/replace_raw`,
   `preflight`, `EFFECT_INTENT`, inverse), `shared/script_edits.py`, `write_apply`, `rollback`,
   `substrate/fs/*`, `substrate/store/*`.
7. Эталон `python/godot_tools/resource_actions.py` (19 642 B,
   sha256 `edef33817b0f5e9a9885dae55648b2c0c01fa2a8f908c07b10007fa1ff7fbbc5`) — prepare-часть
   уже портирована; тебе нужны **пробы записи**, а не его текст.
8. `docs/porting/_start-prompt.resource_ops.md` §9–§10 — формат и уроки.

## §0 База (снято аудитом после приёмки C.23 — не пересчитывать)

- non-live **5019/0/0/0** (моя junit), snapshot **1144/0**, `gen_contract` **27** артефактов,
  отчётов **44**, гейты 560 (1 информационное `split_py`), security ok, live 3 по рецепту §8.
- selfcheck: `resource_ops` ok **452 unit / 235 corpus**; `file_refactor` 124/52; `split_py` 583/107;
  `split_gd` 625/102; `class_api` 128/26; `node_info` 247/65; `tree` 116/40.
- дерево **3772 / 829 / 83**, промптов 43 (3772 — включая сам этот промпт; поправка аудитора
  от 2026-11-02, в первой редакции стояло 3771); `project.godot` 335 B sha `958b3a92…`;
  ADR 16, правил 22; WORKLOG 4479 CRLF-префикс, писать только `ab`.

## §1 Границы среза

В срезе: применение ресурсных операций — **источник transformed bytes** + запись через воронку.
Разрешённые файлы: `python/modules/editing/resource_ops/**`; `docs/adr/0017-*.md` (**proposed**);
`docs/deviations.md`; `docs/security/invariants.md` (SEC-24); `fixtures/corpus/editing/resource_ops/**`
+ manifest; тесты `tests/py/{contract,integration,formats,security}/test_resource*`;
`shared/funnel.py`, `shared/script_edits.py`, `write_apply/app.py`, `rollback/*`, `substrate/fs/*`
и `kernel/write_plan.py` — **только** если проба докажет необходимость, и с моим ответом §10.4.
Записи: лист, `tests-map.md`, `parity.md`, `PROGRESS.md`, `WORKLOG.md`.

Запрещено: `editor/**`, `contract/editor_verbs.json`, `_audit-handoff.md`, таблица механик,
статусы ADR, правка `reports/selfcheck/*.json` руками, чужие корпуса, `project.godot`,
`.gd.uid` вне `fixtures/`, `__pycache__`/`.pyc`/`.bak`.

## §2 Контракт правки

2.1 **Один вопрос среза:** кто производит байты после применения операций. Два допустимых
ответа (§10.1): (а) engine/editor transformer-port — потребует `editor/**`, а он **запрещён** до
моего отдельного разрешения; (б) собственная текстовая трансформация секций с **байтовым
сохранением входа** (BOM/EOL/одиночный CR) — **явное отклонение** от native, потому что
Godot 4.6.3 отвергает BOM и приводит CRLF/lone CR к LF. Выбираешь пробами, утверждаю я.

2.2 Запись — только через воронку. `replace_raw` для ресурсов разрешён **после** ADR-0017
(proposed) и только им; назначение расширяется **новым** ADR, а не правкой ADR-0016.

2.3 Хэш-гвард: `expected_hash` = raw sha256; расхождение → `stale_plan`; повторный apply →
`stale_plan`. Digest независим от форматирования входа. Публичная проекция — без абсолютных
путей и байтов (R-15).

2.4 Политика (D16/SEC-23): target **и** dependency, resolved identity + casefold до плана;
`addons/**`/`ADDONS/**`, `.agent_history`/`.AGENT_HISTORY`, `project.godot`, выход за проект —
запрещены; trusted-флаги не портируются; `realpath`-containment на read и write; общий
`guard_path`/`guard_transfer` — второй барьер, не ослаблять.

2.5 Публичного инструмента не появляется (native не объявляет), контракт остаётся **27**.
Любая публичная утечка байтов — стоп.

## §3 Шаги

0. **Снять замечание F1:** в `tools/selfcheck.py:286` удалить `and module_id != "editing.file_refactor"`
   (мёртвый хардкод: `corpus_folders` для `file_refactor` и `resource_ops` непусты). Доказать:
   `file_refactor` 52/0, `resource_ops` 235/0, `split_py` 583/107, `split_gd` 625/102,
   `class_api` 128/26, `node_info` 247/65, `tree` 116/40, 64 пина C.19 зелёные.
1. Лист: раздел «C.24 — запись».
2. §10-пробы **до кода**: 3–4 actual-native применения, досье наружу, дословные фрагменты
   с номерами строк.
3. **Стоп до моего ответа.** После ответа: ADR-0017 `proposed` → red-тесты → production → корпус.
4. Корпус: успех каждой из шести операций, BOM/CRLF/lone CR, занятая цель, stale hash,
   не-`.tres`, каталог, `res://../`, `addons`/`ADDONS`, `project.godot`, dependency-отказ.
5. Двойной прогон, записи, SHA-таблица **последней**.

## §4 Решения (не переспрашивать)

Воронка — единственный путь записи; `script_edit` не трогаем (он нормализует EOL);
`replace_raw` — только для ресурсов и только после ADR-0017; JSON-отчёты руками не правятся;
`tools/selfcheck.py` больше не меняем, кроме шага 0.

## §5 Доказательства

M1 снять хэш-гвард → «изменился после плана» красный. M2 снять policy-проверку dependency →
кейс `ADDONS`/`project.godot` красный. M3 записать текст через `script_edit` вместо выбранного
способа → кейс байтового равенства красный. P1 занятая цель → `conflict`, исходник цел.
P2 повторный apply → `stale_plan`, дерево байт-в-байт. P3 гигиена: дерево = база + прирост
среза, UID 83, debris 0. Каждая мутация — красный junit + восстановление источника побайтово.

## §6 Стоп-условия

SHA эталона не совпал; нужен `editor/**` или правка принятых тестов; §0 не сходится;
требуется ослабить guard/статус ADR/таблицу; выбор (а)/(б) из §2.1 невозможен без моего решения.

## §7 Что проверит аудитор

Свои прогоны и своя проекция SHA; свои мутации; побайтовое равенство `.tres` после apply;
политику на `ADDONS`/`.AGENT_HISTORY`/`project.godot`; отсутствие IO в `domain`; неизменность
соседних корпусов и отчётов; снятие F1; записи и SHA-таблицу.

## §8 Финал

Числа тестов (collect == executed), junit SHA, snapshot 1144+N, 44 отчёта, contract 27,
гейты, live 3 (335→419 B, вернуть `958b3a92…`, удалить созданные `.gd.uid`), дерево/UID,
таблица кейсов, M/P с SHA, SHA-таблица последней, строка сдачи.
EOL: WORKLOG только `ab`+CRLF, остальные `docs/**` LF, `\r\r\n` — ноль.

## §9 Уроки

1. Буква ≠ смысл (C.19: `tree 128` против 116). 2. Приёмка в одном файле теряется.
3. SHA до записей устаревает. 4. Live оставляет `.gd.uid`. 5. Числа — из источника, не из handoff.
6. `\r\r\n` — ноль. 7. JSON руками не править. 8. Чужие корпуса не переформатировать.
9. Ослабленный пин без красного следа — не пин. 10. Адреса в промпте проверять (SHA мог быть
от соседнего файла; `_cli:792` в `file_refactor.py` не существовало).

## §10 Вопросы (код не писать до ответа)

1. Какой источник байтов выбираешь — (а) engine-порт или (б) текстовая трансформация с
   сохранением входа; что именно меняется в `.tres`, если операция меняет структуру.
2. Что делает native при BOM, CRLF, одиночном CR, хвостовом переводе строки; что делает
   выбранный вариант — таблицей «native / наше / отклонение».
3. Нужен ли новый op, или хватает `replace_raw` с `expected_hash` и компенсацией; как
   выражается многофайловая операция (несколько шагов? порядок отката?).
4. Какие правки инфраструктуры нужны (файлы, причина, минимальность) — список утверждаю я.
5. Какие отклонения войдут в ADR-0017 и `deviations.md` закрытым списком.
