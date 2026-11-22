# Мандат J1 — answer_judge: полное замыкание судьи ответов (12 файлов, 373 684 B)

**Класс: жёсткий. Приёмка: независимый аудит. Частичный вердикт легален (честная фиксация фазы).**

## §1 Цель

Нативный `godot_tools/answer_judge.py` (25 313 B) — детерминированный проект-осведомлённый
судья параллельных ответов LLM: парсит `agent_action`, применяет write-действия к
in-memory overlay, переиспользует librarian-проект-индекс и существующие Godot-линтеры,
возвращает explainable findings (`{acceptable, vote_eligible, score, blocking[], action{}}`)
для выбора ответа. Категории: schema / transaction / gdscript / protocol. Есть
`select_best_project_answer(root, [(key, text), ...])`. Вызывающий в нативе:
`tools/agent_bridge.py:1370`.

Результат среза: MODULE `modules/assistant/judge` — зарегистрированный публичный
инструмент **`judge`** (одиночная оценка ответа; опционально кандидаты для выбора —
форма аргументов фиксируется по нативным тестам и фиксируется в контракте),
selfcheck `assistant.judge` verdict ok / exit 0, корпус зелёный ×2.

## §0 Предусловия (проверить ДО старта; расхождение = STOP)

1. Репозиторий: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
2. WORKLOG: 940 185 B, sha256 `f0f9ceb6df5a1a66…`, CRLF. Если изменился — пересчитать §0, не переписывать.
3. Четыре замороженных пина librarian-quartet на диске byte-exact:
   librarian 97 676 `340b5dd2be96ebc4…` LF1551/CRLF1551; ml_project_index 65 753 `2f7694a91a48e294…` LF1120/CRLF866;
   ml_data 32 324 `e13d56800d124627…` LF757/CRLF0; gd_semantic_parser 15 723 `bf35dcea5e77011d…` LF392/CRLF0.
4. `substrate/llm/parsers/parser_base.py` 198 211 `7b2ce9f14695416e…` — уже ported byte-exact
   (импорт `selenium.common.exceptions` резолвится: selenium 4.46.0 в окружении; judge сеть не использует).
5. `python -m tools.selfcheck context.ask --json` → ok/exit 0; корпус `fixtures/corpus/context/librarian/` нетронут (213).
6. Нативное дерево: `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python`.

## §2 Замыкание: 12 byte-exact файлов (пины сняты аудитором 2026-11-12; перепроверь §0-пересчётом)

| # | нативный файл | B | sha256 (префикс 16) | LF/CRLF | назначение в substrate |
|---|---|---|---|---|---|
| 1 | godot_tools/tscn_lint.py | 74 080 | `118e9ddc0b776cd8` | 1315/0 | substrate/verification/tscn_lint.py |
| 2 | godot_tools/runtime_checks.py | 20 148 | `1ce232f17af8a5e1` | 433/0 | substrate/verification/runtime_checks.py |
| 3 | godot_tools/symbol_refactor_data.py | 974 | `96b31fa44154d593` | 18/0 | substrate/code_intel/symbol_refactor_data.py |
| 4 | godot_tools/symbol_refactor_part1.py | 43 259 | `b83f4ab5504de7a5` | 0/824 | substrate/code_intel/symbol_refactor_part1.py |
| 5 | godot_tools/symbol_refactor_part2.py | 42 744 | `4889c9b118cad3b0` | 718/0 | substrate/code_intel/symbol_refactor_part2.py |
| 6 | godot_tools/symbol_refactor_part3.py | 49 533 | `93f8c8923703020f` | 714/0 | substrate/code_intel/symbol_refactor_part3.py |
| 7 | godot_tools/symbol_refactor.py | 3 964 | `92448cdb5d59116f` | 120/0 | substrate/code_intel/symbol_refactor.py (фасад) |
| 8 | godot_tools/scene_deps.py | 19 866 | `dbd502afeca7fa2f` | *пересчитать* | substrate/scene/scene_deps.py |
| 9 | godot_tools/scene_actions.py | 17 246 | `0aaef0aa4efc30e4` | 349/0 | substrate/editing/scene_actions.py |
| 10 | godot_tools/file_refactor.py | 67 833 | `61171473c1bb6735` | *пересчитать* | substrate/editing/file_refactor.py |
| 11 | godot_tools/high_level_actions.py | 8 724 | `3ac1a1c141fdf107` | 186/0 | substrate/assistant/high_level_actions.py |
| 12 | godot_tools/answer_judge.py | 25 313 | `545639a905fdb2b0` | 492/0 | substrate/assistant/answer_judge.py |

Сумма: 373 684 B. Замыкание проверено аудитом BFS-прогоном по нативным импортам:
транзитивные зависимости ВСЕХ 12 файлов резолвятся внутри этого набора + уже
перенесённого (parsers/*, project_tools, gd_api_check, gd_lint, gd_api_cache,
history_manager, gd_semantic_parser, minilich-алиас, runtime_debug, scene_deps в наборе).
EOL сохранять нативные (конвертация запрещена; part1 — CRLF-файл). Новые каталоги
`substrate/scene/`, `substrate/editing/`, `substrate/assistant/`, `substrate/code_intel/`
с инертными `__init__.py` (прецедент `substrate/context/__init__.py`, 83 B).

## §3 Стадии и порядок G

- **A1** tscn_lint + runtime_checks (94 228 B). Red-before-code: нативные тесты
  `test_runtime_checks.py` (5 336) как спот-корпус; для tscn_lint нативных тестов нет —
  красные кейсы составить из вызовов judge (битые сцены) до порта.
- **A2** symbol_refactor пятерка (140 474 B). Red-before-code: нативные
  `test_rename_symbol.py` (12 125) + `test_rename_symbol_flow.py` (4 023) +
  `test_rename_symbol_overrides.py` (11 782) + `test_find_symbol_usages.py` (7 087).
- **A3** scene_deps + scene_actions + file_refactor + high_level_actions (113 669 B).
  Red-before-code: нативные `test_scene_actions.py` (7 733) + `test_scene_action_flow.py`
  (14 898) + `test_high_level_actions.py` (5 701) + `test_high_level_flow.py` (4 429).
- **B** answer_judge + адаптер + MODULE `assistant.judge` + корпус + мутации + гейты + seal.
  Красные кейсы из нативного `test_answer_judge.py` (16 419, ~20 тестов) до порта.

Правила каждой стадии: свои красные до кода, эталонный прогон ×2, mini-seal артефактов
стадии в досье, честный STOP-протокол при проблеме (запечатать срез, доложить).
Мутации: ≥2 на A2 и A3 (по одному на критичный файл стадии), ≥6 суммарно на финале,
все с exact restore (raw bytes/SHA/LF/CRLF) и same-IDs green.


## §4 Архитектура MODULE `assistant.judge`

- Skeleton NEW: `modules/assistant/judge/` по образцу `modules/context/ask/` (после L2a):
  `tools.py` ToolSpec name **"judge"**, effects=("read",), idempotent=True, errors
  (invalid_input, not_found, denied), args/result JSON-схемы additionalProperties:False;
  `module.py` ModuleSpec(id="assistant.judge", provides_tools=("judge",),
  requires_ports=("fs","librarian"), capabilities=("assistant.judge",),
  entrypoints={"call": app.call}); `app.py` ≤80 строк (валидация → домен → Result);
  `domain/core.py` чистая логика, R-11 (без os/pathlib/socket/subprocess — в domain);
  `ports.py` Protocol по надобности; `tests/test_core.py` + `tests/test_public.py`.
- Нативный judge НЕ пишет на диск (докстринг). Но он вызывает `build_index` и legacy
  хранилища — роутинг storage в state_dir профиля по прецедентам D53/D56/D57: тонкий
  NEW-адаптер (по образцу `substrate/context/librarian_read.py`, 4 226 B) — например
  `substrate/assistant/judge_read.py` — активирует биндинг-окружение и маршрутизирует
  legacy history/API-cache/index storage в профиль под shared lock с restore в finally.
  Простое решение предпочтительнее умного; обоснование выбора — в листе.
- Биндинги: +12 алиасов в `substrate/llm/runtime_bindings.py` BINDINGS (tscn_lint,
  runtime_checks, file_refactor, scene_deps, scene_actions, high_level_actions,
  symbol_refactor, symbol_refactor_data, symbol_refactor_part1/2/3, answer_judge) —
  алиасы добавляются В КОНЕЦ списка (прецедент D48/D50); minilich-родитель уже есть.
  F2-пин ≤72 строк runtime_bindings будет задет правомерно — обнови пин-тест с
  red-before-code (точное новое число строк по факту правки).
- Корпус: `fixtures/corpus/assistant/judge/` — manifest (module "assistant.judge",
  stage, provenance с пинами всех 12 файлов, normalization), catalog.json с кейсами из
  нативного test_answer_judge + синтетические (edge бюджета, нет файла, битый
  GDScript, patch-транзакция, content_ref, protocol-нарушение, librarian-взвешивание),
  fixtures/ мини-проект, observations — эталоны нативного поведения, снятые с нативного
  прогона (дважды) до порта. `selfcheck corpus_folders` найдёт `assistant/judge`
  естественно — правка selfcheck НЕ требуется (в отличие от L2).
- snapshot_diff generic path (build_agent → agent.call("judge")) — ожидается рабочим;
  если потребуется нормализация или ветка — по прецеденту D52 (отдельная санкция).

## §5 Критерии успеха (проверяются приёмкой)

1. `python -m tools.selfcheck assistant.judge --json` → verdict ok / exit 0, ×2
   (module/layers/limits/contract/security/unit/corpus; limits — прежние 2 warnings).
2. Probe: реальный `agent.call("judge", ...)` — нативный формат вердикта
   (acceptable/vote_eligible/score/blocking/action) на эталонных входах ×4
   (answer, invalid_input exit1, denied exit1, no-write-доказательство: дерево проекта
   до/после побайтно идентично, storage только в state_dir).
3. 12 файлов + `__init__`ы byte-exact с нативными EOL; binding-пин обновлён легально.
4. Мутации ≥6 killed / 0 survivors, exact restores; эталонные прогоны ×2 exact IDs.
5. Полный регресс ×2 (текущий полный + новые тесты), frozen230/API253/project288,
   gates ×2 + security ×2 с B-1 (никаких реальных bind/listen), symlink1314 gap не трогать.
6. Досье запечатано seal-ПОСЛЕДНИМ, ZIP побайтно проверен; честность blocked/exit2 →
   unknown_tool/exit1 → ok в хронологии.

## §6 Авторизованные правки

- NEW: substrate-каталоги+`__init__`, 12 файлов, module skeleton, адаптер, корпус,
  тесты, алиасы биндингов, контракт-артефакт, docs (parity/лист/README/PROGRESS/WORKLOG).
- Token-only правки tools/* и тестовых пинов — только через STOP-прецедент D52/D55/D57:
  запечатать срез, доложить, санкцию получить, red-before-code, deviations-запись.
  Self-санкции запрещены. Всё сверх §6 — STOP.

## §7 Честность и STOP-пункты

- Selfcheck/probe-хронология до работ честно в досье; никаких self-acceptance.
- Инцидент-протокол: исчезновение пустых файлов в %TEMP% — восстанавливать только по
  детерминированному allowlist из seals (прецедент инцидентов №1/№2), без перезаписи.
- Сеть/сокеты judge не использует; SEC-03 AST-детектор не ослаблять (B-1 сохранён).
- NN-модули, browser-live, production HTTP — вне среза, не трогать.

## §8 Чек-лист приёмки (аудитор)

tree-identity → §0-пересчёт → 13+ пинов byte-exact (включая EOL) → corpus ×2 →
probes ×4 (с no-write) → мутации → полный ×2 + focused/frozen/api/project →
gates/security ×2 → docs (parity строка `assistant.judge`, лист
`docs/porting/answer-judge.md`, README/PROGRESS/WORKLOG, deviations) →
досье/ZIP → seal последний → реверификация аудитором.

Порядок стадий соблюдай строго; STOP между стадиями легален и предпочтительнее
тихого отклонения. Удачи.

---

# Поправка J1a (2026-11-13, аудитор) — санкции D58–D61 по preflight-STOP

Preflight-досье `answer-judge-J1-preflight-20261113-postseal` принято как STOP-рекорд:
verdict ok, module_verdict STOP, 995 evidence, seal 726 677 `de1e5cae4fab3530…`,
ZIP 4 198 325 `0fac7bf8b568895d…`, ZIP_full_byte_check_bad=0, repository_unchanged.
Все четыре блокера независимо подтверждены аудитом. Санкции:

## D58 — замыкание 15 файлов / 434 736 B (замена §2)

Мой §2-BFS пропустил lazy-импорты (answer_judge.py:96/103 → resource_actions,
transaction_actions; transaction_actions.py:11 → godot_headless_validation).
Три новых файла с пинами аудита (перепроверь §0-пересчётом):

| нативный файл | B | sha256 (префикс 16) | LF/CRLF | назначение |
|---|---|---|---|---|
| godot_tools/godot_headless_validation.py | 21 780 | `a77aec0cf345964c` | 453/0 | substrate/verification/godot_headless_validation.py |
| godot_tools/resource_actions.py | 19 642 | `edef33817b0f5e9a` | 355/0 | substrate/editing/resource_actions.py |
| godot_tools/transaction_actions.py | 19 630 | `fe02a40b16974456` | 397/0 | substrate/editing/transaction_actions.py |

Итого: **15 файлов / 434 736 B**, биндинг-алиасов +15. Всё остальное §2 (пины, EOL,
инертные `__init__`) без изменений. Замыкание 15 закрыто аудитом повторным BFS
(ast.walk: top-level + lazy) — транзитивных зависимостей вне набора+ported нет.

## D59 — dotted-child импорт minilich (token-only правка runtime_parent.py + старый пин-тест)

Подтверждено: `substrate/context/runtime_parent.py` (809 B) создаёт ModuleType('minilich')
без `__path__` и кладёт в sys.modules только 'minilich'; точный
`from minilich.ml_project_index import search` (answer_judge.py:12) даёт
ModuleNotFoundError после настоящей регистрации биндингов.

Разрешено: token-only правка `bind_parent` — дополнительно регистрировать
`sys.modules['minilich.ml_data']` и `sys.modules['minilich.ml_project_index']`
(identity-bound к тем же реальным модулям, добавить в `added`, чтобы существующий
rollback владел и ими). Red-before-code: репродукция «изолированный реальный import
после настоящего register» — красный до правки, зелёный после; отдельный кейс:
rollback снимает и child-ключи. Старый пин `test_librarian_binding.py:26` («явно
запрещает dotted child») правится с red-before-code на НОВЫЙ точный контракт:
child-ключи присутствуют ровно пока биндинг активен и снимаются rollback-ом.
Deviations-запись D59 обязательна.

## D60 — check_limits: класс-правило для 6 verbatim-файлов (прецедент D29/class3400)

Внешняя проекция line-counts даёт fail/exit1 на: file_refactor 1457, part1 824,
part2 718, part3 714, answer_judge 492, scene_deps 412 — default400 в новых
каталогах. A1/verification (включая godot_headless_validation 453) уже покрыт
прежним class3400 — гейт не ослабляется.

Разрешено: token-only правка check_limits — НОВОЕ класс-правило «verbatim native
reference J1» с ЯВНЫМ списком ровно этих 6 путей и их измеренных line-counts;
все прочие файлы (включая новые каталоги) остаются под default400. Red-before-code:
произвольный новый 401-строчный файл в новых каталогах → fail; каждый из 6 → pass;
после правки гейты зелёные. Deviations-запись D60 + строка в ADR/листе.

## D61 — порядок G: A2↔A3 (forward dependencies)

Подтверждено: part1:14/15 и фасад:15/16 импортируют A3-файлы при загрузке.
Новый порядок стадий (суммы байт):

- **A1 (verification)** tscn_lint 74 080 + runtime_checks 20 148 +
  godot_headless_validation 21 780 = **116 008**
- **A2 (scene/editing/actions)** scene_deps 19 866 + scene_actions 17 246 +
  file_refactor 67 833 + resource_actions 19 642 + transaction_actions 19 630 +
  high_level_actions 8 724 = **152 941**. Красные источники:
  test_scene_actions 7 733, test_scene_action_flow 14 898,
  test_high_level_actions 5 701, test_high_level_flow 4 429,
  test_transaction_actions/flow + test_resource_actions/flow (если есть в
  нативных tests — взять оттуда эталоны).
- **A3 (symbol_refactor)** data 974 + part1 43 259 + part2 42 744 + part3 49 533 +
  фасад 3 964 = **140 474**. Красные источники: rename* 27 930 + find_symbol_usages 7 087.
- **B** answer_judge 25 313 + адаптер + MODULE + корпус (без изменений §4).

Runtime-замыкание каждой стадии теперь закрыто предыдущими стадиями; native-only
replay не выдаётся за готовую стадию — для каждой стадии свои реальные red/green
и mini-seal (§3 без изменений в остальном).

Прочее: §5 критерий 3 читается как «15 файлов + __init__-ы»; честная хронология
(preflight fail/exit1 assistant.judge → unknown_tool/exit1 probe) уже в досье —
образец правильного STOP-протокола. Продолжай с A1.

---

# Поправка J1b (2026-11-13, аудитор) — решения D62–D64 по STOP стадии A1

STOP-досье `answer-judge-J1-A1-20261113` (+postseal-corrected ZIP) принято как
рекорд: security-projection запускал НЕИЗМЕНЁННЫЙ checker (a558da5b42f872e0,
17 566 B) на проекции 5274 существующих файлов + 3 A1-цели (пины подтверждены,
116 008 B) → exit1 ровно с 2 блокировками (SEC-03 subprocess.run, SEC-04
verification placement). Копирование побайтное, checker_source_identical.
Решения:

## D62 — SEC-03: узкое исключение subprocess.run (прецедент B-1/D51, file-scoped, fail-closed)

Санционирована новая функция в tools/security_audit.py по образцу
`_exclusive_probe_bind_start` («распознаёт ровно один не-listening вызов, никогда
не авторизует файл целиком»). Вызов `.run()` НЕ считается listener-ом тогда и
только тогда, когда ВСЕ условия выполнены одновременно:

1. path == PY/"substrate"/"verification"/"godot_headless_validation.py" (единственный файл);
2. callee — ровно `Attribute(value=Name(id='subprocess'), attr='run')`;
3. в файле есть top-level `import subprocess` без asname;
4. первый позиционный аргумент — `ast.List`, каждый элемент — `ast.Constant(str)`
   ИЛИ `ast.Call(func=Name('str'), args=[ast.Name], keywords=[])` (форма str(proc.pid));
5. в kwargs нет `shell`; значения kwargs — только `subprocess.DEVNULL`/`subprocess.PIPE`
   или константы (`check=False`).

Любое невыполнение — вызов остаётся flagged (fail-closed). Пропуск действует
только на точное byte-offset смещение конкретного вызова; ДРУГИЕ совпадения
LISTEN_PATTERNS в том же файле флагуются как раньше. Parse error → hits=True
(не меняется). B-1 не ослабляется.

Красная/зелёная матрица (новые тесты в tests/py/security/, red-before-code):
- green: строка 369 пин-файла (taskkill со str(proc.pid), DEVNULL/DEVNULL,
  check=False) не флагуется; security итог ok.
- red: тот же вызов в ЛЮБОМ другом файле → red; `subprocess.run(cmd_var)` → red;
  `subprocess.run("taskkill /PID 1")` (строковая команда) → red;
  `import subprocess as sp; sp.run([...])` → red; `from subprocess import run;
  run([...])` → red; элемент-списка с атрибутом/сабскриптом/звёздочкой → red;
  `shell=True` → red (и SEC-04); socket `.bind`/`.listen`/`.run()` на иных
  приёмниках → red; unparseable → red.
- Инвариант (записать в deviations D62 + ADR-строку): исключение описывает
  «завершение собственного таймаутом дочернего процесса списочной командой без
  shell в единственном пин-файле»; общего послабления `.run` нет — поведение
  всех прочих файлов не меняется.

## D63 — SEC-04: единичный файл-пин для import subprocess

Санционировано: в check_processes — file-pin: `substrate/verification/
godot_headless_validation.py` разрешает РОВНО один top-level `import subprocess`
без asname. Запрещены: `from subprocess import ...`, `import subprocess as ...`,
`import subprocess, <другой модуль>`, второй subprocess-импорт, subprocess в
любом ДРУГОМ файле verification (директория не освобождается — blanket
exemption запрещён). `shell=True` остаётся запрещённым везде. Red/green:
green — строка 13 пин-файла; red — все перечисленные формы + тот же импорт в
соседнем verification-файле. Deviations D63.

## D64 — harness-ресурс: байт-точный примитив по точному пути

Санционирован новый файл `python/agent_headless_validator.gd` — byte-exact
нативный примитив 1 701 B, sha256
`799ec9e26f43f65aa8208a1cf1e5379b8d5c3ca80fbd3ad7a0a8e87251da895e`, LF39/CRLF0.
Обоснование: `_harness_source()` (нативные строки 215–218) вычисляет
`dirname(__file__)/../../agent_headless_validator.gd` — нативно это корень
аддона, для byte-exact копии в substrate/verification это `python/`. Ресурс —
данные: только чтение ресурсов, запись в owned overlay, exit; сам Godot-бинарник
не запускает и процессов не порождает (в срезе actual validation не выполняется).
Обязательные доказательства: (а) default-path тест — `_harness_source()` без
аргумента находит ресурс и читает ровно 1 701 B с пин-sha; (б) explicit-path
тесты остаются зелёными; (в) фиксация в deviations D64; (г) ресурс входит в
tree/seal/ZIP и в §2-таблицу (итог замыкания: 15 py + 1 gd = 436 437 B;
sys._MEIPASS-ветка строки 220 — нетронутый нативный код, вне среза).

Resume: со стадии A1 этапа 3 — implement D62/D63 (red-before-code), добавить
ресурс D64, перенести canonical references, green тех же 121 ID (нулевые
setup-ошибки), differential ×2, гейты и live-пробы, mini-seal. MODULE/алиасы/
D59/D60/A2 — далее по плану.



