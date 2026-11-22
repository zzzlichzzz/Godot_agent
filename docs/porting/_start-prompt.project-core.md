# Мандат: «проектный фундамент» (project-core) — project_tools + project_settings_actions

Класс: **жёсткий**. Модель: gpt-6.1-sol. Приёмка: независимый аудит (частичный вердикт легален).

Цель: byte-exact перенос ядра доступа к проекту — единственного недостающего
фундамента для project_ops.architecture, project_ops.settings_get/set,
verification.runtime_checks, verification.headless и будущего answer_judge.

## §0 — самопересчёт перед стартом (обязателен, числа для сверки)

- Корень репо: `D:\vajno\Godot\agent-rebuild` (project.godot 335 B, 958b3a92… — лежит в корне, не в plugins-каталоге).
- `docs/WORKLOG.md` ≈770469 B, префикс SHA `ca45010476a3d015` — пересчитай фактически;
  возможны промежуточные добавки, appends только CRLF с префикс-ассертом на момент твоей записи.
- `docs/parity.md` 24262 B, SHA `5d1cec37…`, LF-файл (194 bare LF — исторические) — не трогать, кроме строк L95/L96/L97 строго по факту.
- `docs/porting/README.md` 32213 B, `cd28219c…`, CRLF; L69 api-core и L70 routing-runtime — принятые строки, не портить (недавний ремонт L69/L70 — история в WORKLOG).
- Гейты на старте: lint_arch 596 файлов/0 нарушений; check_limits ok/2 (те же 2 legacy-warning: split_py 11, editing 8400); gen_contract --check 28/0; security_audit ok/0.
- Регрессии на старте: полный non-live 6250 собрано = 6248 passed / 2 legacy-skip (WinError 1314), ×2, ordered/once-only; focused 376×2; frozen 230×2 (runtime 141 + SEC-03 72 + B-2 17); api-core 253×2.
- Гигиена: reports/selfcheck 44 файла, *.uid 86, *.pyc 0, 4 сентинела `fixtures/projects/corpus/editing/**/__pycache__/ref.gd`.
- Замороженные пины (byte-exact, кроме временных мутаций с восстановлением): facade 6abe81d2 (5333 B); browser_manager 4afd245f; cdp_ws 3b5298dd; net_monitor 54167afb; sites 06da9270; live_input cd2c6ccf; ai_studio_net 3d9a3fb4; qwen_net 57d1ab2b; browser_backend 21e5e911; security_audit c59e4faf (16153 B); парсеры parser_base 7b2ce9f1, arena_parser cdc01c59, ai_parser 20b0cf87, qwen_parser e0b888fe, kimi_parser f0db0f5c, deepseek_parser 554b6505, text_sanitize 2c18bbef; api-слой api_keys 340f73fb, providers a269ea59, catalog 8860d454 (в новом дереве providers_catalog), model_cache 58895c14, openai_compat 6b1022ae, anthropic_compat c7b8f32c, agent_prompts 633ad387, rate_limit a9d6d9f2, md_to_bbcode e90a7615, chat_store b275c7c2, api_history cce2c180; routing-слой runtime_debug ed7d6087, editor_context 32613d28, api_backend 93d22fb5; runtime_bindings.py 2725 B f310b781; tools/check_limits.py 5384 B 5ef23793.
- Окружение: Python 3.14.6, `python -B -X utf8`; pytest `no:cacheprovider`, basetemp и JUnit вне репо, `--import-mode=importlib`. Никакого `wb`-режима на tracked-файлах: всегда бэкап + пост-ассерт байтов/SHA/EOL (урок инцидента README).
- Проверь всё перечисленное сам и зафиксируй фактические числа в досье (§0-recount.json).


## Часть A — byte-exact перенос «проектного фундамента»

| native | размер | SHA256 | замыкание (top-level импорты) |
|---|---|---|---|
| `godot_tools/project_tools.py` | 102471 B | `79e9b035bd211f4a` | только `errno` (stdlib) + `text_sanitize` — **уже ported** в связке парсеров |
| `godot_tools/project_settings_actions.py` | 13735 B | `fcdb4635aa8ccb96` | только `project_tools` |

- Замыкание **полностью закрыто** — проверено аудитором до выдачи мандата; если при пересчёте найдёшь иной top-level импорт — STOP, это отклонение от замыкания, честный вердикт.
- Размещение (отклонение D39, spec-before-code): `python/substrate/project/` — новая директория (сиблинг editor/fs/llm/store), `__init__.py` по образцу соседей; project_settings_actions — там же либо в `substrate/project/settings/`, решение портёра, зафиксируй в листе.
- Байты = native, включая EOL; никаких правок импортов внутри эталонов: плоские `import text_sanitize` / `import project_tools` не редактировать.
- Связка: расширить `python/substrate/llm/runtime_bindings.py` (+2 алиаса: `project_tools`, `project_settings_actions`). Пины D33 неизменны: только явный импорт связки, idempotent, алиас `is` реальный модуль substrate, без sys.path/meta_path/скрытых хаков, production-профили и bootstrap связку не импортируют, откат = только новые алиасы. Порядок внутри связки: парсерные алиасы (в т.ч. `text_sanitize`) существуют — `project_tools` регистрировать после них; проверь `sys.modules['text_sanitize'] is` модуль substrate на момент импорта project_tools.
- **SEC-ядро (главное содержание среза)**: project_tools — слой безопасности путей плагина (`can_read_project_path`, `_resolve_safe_path`, guards `read_project_file`/`search_project_text`, `begin_case_only_dir_casing`, `describe_scene`, обзор autoload-каркаса). Корпус и тесты обязаны покрыть: обход каталогов (`..`, абсолютные пути, UNC), симлинки/junction, регистронезависимость имён Windows (case-only dir), UTF-8/unicode-имена, отказ чтения вне корня проекта, пустые/битые сцены в `describe_scene`. Всё на fixture-проектах под `fixtures/projects/…` и sandbox-каталогах; реальный Godot-редактор и внешняя сеть не нужны и запрещены. Маскирование/спуфы не ослаблять; урок SEC-06: совпадение с транспортными паттернами в корпусе — STOP, а не подгонка.

## Часть B — корпус и тесты

- Корпус: `fixtures/corpus/project/manifest.json` (байты/SHA/происхождение кейсов) + fixture-проекты с минимальной структурой Godot-проекта, нужной нативной семантике (project.godot, .tscn/.gd, вложенные каталоги). Повторяй поведенческие ветви нативных тестов по воспроизводимым наблюдениям, не копируя старый тестовый код (R-16).
- Тесты: `tests/py/project/test_project_tools_*.py` и `test_project_settings_*.py`, прогон ×2, ordered/once-only ID/outcomes; минимум: security-матрица чтения путей, casing-кейс, ветви get/set project_settings_actions (включая отказ по can_read), describe_scene на fixture-сценах.
- `docs/tests-map.md` — править только строки project_ops по фактическому покрытию; частичное покрытие = пометка в листе, не смена статуса legacy-строк.

## Часть C — лимиты, мутации, гейты

- check_limits: project_tools ≈102 КБ не влезает в текущие классы — добавь узкое классовое правило для `substrate/project/` по образцу D32/D35/D38: сначала red-пины точных границ (нового класса нет → нарушения), затем правка `tools/check_limits.py` (только классовое правило), прежние 2 legacy-warning остаются.
- Мутации ≥3: (1) эталон — граница `can_read_project_path` deny→allow для одного класса путей → красная SEC-матрица; (2) эталон — искажение нормализации `_resolve_safe_path` → красные кейсы canonicalization; (3) связка — алиас не тот модуль/idempotence сломана → красный binding-тест. Каждая: red → восстановление byte-exact (SHA+LF/CRLF) → green. Мутации замороженных файлов — только временные, финальные байты = эталонные.
- Гейты ×2 (до и после записей): lint_arch / check_limits --json / gen_contract --check / security_audit — ok/0 (кроме прежних 2 warning). Полный non-live ×2 (6248 + новые), frozen 230×2, api-core 253×2, focused новые ×2. Отчёты selfcheck 44 не трогать; substrate-selfcheck project_ops останется blocked (нет MODULE) — честно, не поднимать.
## Порядок работ

§0-пересчёт → tree-before (dossier) → таблица замыкания (проверь импорты сам) →
red-доказательство нового класса лимитов → перенос A byte-exact → связка +2 алиаса →
корпус + тесты (×2) → мутации (red → restore → green) → гейты ×2 → записи →
tree-after → SHA-печать досье **последней**.

## Записи

- Новый лист `docs/porting/project-core.md` (CRLF, spec-before-code, решения, вердикт).
- `docs/WORKLOG.md` — добавка CRLF с префикс-ассертом (текущий байтовый размер+SHA пересчитай; добавка — чистая, без дублирования, урок инцидента debt-cases).
- `docs/porting/README.md` — регистрация: добавь строку после L70 (routing-runtime) по тому же шаблону; L69/L70 не редактировать.
- `docs/deviations.md` — D39 append (CRLF; урок routing: не терять CR старых строк — prefix-ассерт перед записью).
- `docs/parity.md` — только L95/L96/L97 по факту, статус остаётся `skeleton` с пометкой «reference-срез принят, MODULE-интеграция отдельно» (прецедент api-core/routing: полный модуль не заявляется ported без MODULE-интеграции).
- Досье: `%TEMP%\opencode\c8_audit\project-core-<дата>\` — tree-before/after, JUnit всех фаз (до/мутации/после), orig-копии мутированных файлов, скрипты, SHA-печать последней.

## Разрешено / запрещено

Разрешено: `tests/py/project/**`, новые кейсы в `tests/py/**` по необходимости,
`fixtures/corpus/project/**`, `fixtures/projects/**` (новые fixture-проекты),
`python/substrate/project/**`, `python/substrate/llm/runtime_bindings.py` (+2 алиаса),
`tools/check_limits.py` (только классовое правило), `docs/tests-map.md` (project_ops-строки
по факту), `docs/deviations.md` (D39), `docs/WORKLOG.md`, `docs/porting/project-core.md`,
`docs/porting/README.md` (одна строка регистрации), `docs/PROGRESS.md` (только честные
добавки прогресса), досье.

Запрещено: менять байты замороженных эталонов (см. §0-пины) вне временных мутаций с
восстановлением; facade/transport; `contract/`; `parity.md` кроме L95–L97; native-источники;
другие `tools/*`; внешняя сеть; реальные профили Godot; substrate-selfcheck runtime;
runtime_owner/server_state; браузерные/парсерные/api-эталоны; `reports/selfcheck/*`.

## Стоп-условия

- Мутация не красная на новом кейсе → стоп, честный вердикт, без подгонки тестов.
- Гейт ok→fail или SHA/EOL-restore mismatch → стоп до разбора.
- Замыкание тянет незапланированную подсистему (gd_api_cache/history/flask/ctypes-механики) → честный deferred, не «перенесём и сервер».
- Частичное исполнение — легальный вердикт: укажи фазу и причину.
- Пересчёт §0 расходится с обещанным замыканием (иной top-level импорт у эталонов) → STOP.

## Поправка F0 (аудитор, 2026-11-06) — полные списки top-level импортов

Моя таблица замыкания части A перечисляла только non-stdlib импорты и была неполной.
Портёр корректно остановился по §0-стоп-условию. Полные списки (проверены аудитором):

- `project_tools.py`: `errno`, `os`, `shutil`, `stat`, `tempfile` (stdlib) + `text_sanitize` (уже перенесён, доступен через связку parsers).
- `project_settings_actions.py`: `hashlib`, `json`, `math`, `os`, `re`, `uuid` (stdlib) + `project_tools` (эталон этого среза).

Вердикт замыкания НЕ меняется: все дополнительные импорты — стандартная библиотека,
новых проектных/сетевых/бинарных зависимостей нет. Перенос остаётся полностью замкнутым.

Пересмотр стоп-условия §0: STOP обязателен только при появлении top-level импорта,
НЕ входящего в эти два списка (т.е. любого не-stdlib или незаявленного). Перечисленные
stdlib-импорты разрешены явно. Если в теле файлов найдётся условный/ленивый импорт
вне этих списков — обычная обработка по правилам мандата (отклонение D39 с фиксацией).

Портёр может продолжить в том же досье project-core-20261106: STOP-записи остаются
в WORKLOG/PROGRESS как доказательство честной остановки; код, aliases, лимиты и
corpus не создавались — §0 и tree-before пересчитывать заново не требуется, но
перед продолжением убедись, что рабочее дерево совпадает с tree-before досье.
