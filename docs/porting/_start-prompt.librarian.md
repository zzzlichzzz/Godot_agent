# Мандат: «Библиотекарь — локальный поиск и сборка ответа» (librarian)

Класс: жёсткий. Модель: gpt-6.1-sol. Приёмка: независимый аудит. Частичный вердикт легален (честная фиксация фазы).

**Предусловие, жёсткое**: срез engine-cache должен быть ЗАКРЫТ независимой приёмкой ДО старта этого мандата (librarian импортирует `gd_api_cache` — алиас появится только там). Параллельные срезы запрещены (контаминация tree-diff). Свежее досье, свежий пересчёт §0.

Цель: byte-exact перенос 2 файлов (ml_project_index.py + librarian.py) в `substrate/context/`, явная связка (+2 алиаса + синтетический родительский пакет `minilich`), offline-корпус и тесты для справочного среза `context.ask`. Это открывает critical-path механику context.ask (parity L77) и снимает последнюю предпосылку answer_judge (`librarian_search`).

## §0 — самопересчёт (всё по факту, числа ниже — ориентиры)

1. Корень репо: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`; project.godot — на УРОВЕНЬ ВЫШЕ (корень agent-rebuild), 335 B, `958b3a92d706979e…`.
2. docs/WORKLOG.md — CRLF; пересчитай размер/SHA на момент старта (ориентир ≈805 000 B, `bd04d0bb…`); append чистой добавкой с prefix-assert (промежуточные appends других срезов легальны — бери фактические числа).
3. docs/parity.md — 24 262 B, `5d1cec37…`, LF-only, не трогать кроме строки L77 (и только по факту покрытия).
4. docs/porting/README.md — CRLF; пересчитай; строку-регистрацию вставлять ПОСЛЕ конца строки engine-cache (урок r7: никогда не в середину строки).
5. Гейты на момент старта (пересчитай): lint_arch 0 нарушений (~599+ файлов), check_limits ok/2 прежних legacy-предупреждения (split_py 11, editing 8400), gen_contract --check 28/0, security_audit ok/0.
6. Регрессии: full non-live ×2 (ordered/once-only; после engine-cache ожидается база ≈6831 pass / 2 legacy skip — пересчитай), frozen-набор ×2, API-core 253×2, project 288×2; все старые ID/outcomes сохраняются.
7. Hygiene: reports/selfcheck 44, .uid 86, .pyc 0, 4 сентинела fixtures/projects/corpus/editing/**/__pycache__/ref.gd.
8. Замороженные пины (пересчитай по факту): facade `6abe81d2…`; браузерные 8 (browser_manager `4afd245f…`, cdp_ws `3b5298dd…`, net_monitor `54167afb…`, sites `06da9270…`, live_input `cd2c6ccf…`, ai_studio_net `3d9a3fb4…`, qwen_net `57d1ab2b…`, browser_backend `21e5e911…`); парсеры 7 (parser_base `7b2ce9f1…`, arena `cdc01c59…`, ai `20b0cf87…`, qwen `e0b888fe…`, kimi `f0db0f5c…`, deepseek `554b6505…`, text_sanitize `2c18bbef…`); API 11 (api_keys `340f73fb…`, providers `a269ea59…`, providers_catalog `8860d454…`, model_cache `58895c14…`, openai_compat `6b1022ae…`, anthropic_compat `c7b8f32c…`, agent_prompts `633ad387…`, rate_limit `a9d6d9f2…`, md_to_bbcode `e90a7615…`, chat_store `b275c7c2…`, api_history `cce2c180…`); routing 3 (runtime_debug `ed7d6087…`, editor_context `32613d28…`, api_backend `93d22fb5…`); project 2 (project_tools `79e9b035…`, project_settings_actions `fcdb4635…`); gd-файлы 4 из engine-cache (history_manager `f6655173…`, gd_api_cache `6e6f5e0c…`, gd_api_check `b9e0df9f…`, gd_lint `66618648…`); данные `agent_api_cache/default_api_cache.json` 2 004 630 B `7352d27c…`; C.11-проекция api_cache_store `352f9e9b…`; runtime_bindings и check_limits — пересчитай по факту.
9. Python 3.14.6: `python -B -X utf8`; pytest `no:cacheprovider`, basetemp и JUnit — ВНЕ репо, `--import-mode=importlib`.
10. Уроки (обязательны): F0 — полные списки top-level импортов в таблице, STOP только на не-stdlib/незаявленном; запрет `wb`-режима — всегда бэкап + пост-ассерт; SEC-06 — любой security-флаг = STOP; r7 — не рвать строки README вставками; CR-loss при appends в deviations (фиксируй EOL до/после); D43/D45 — пиновые правки счётчика связки/лимитов строки теперь самостоятельные по шаблону (токен-only + red-before-code); D44 — deployed-данные в repo-root = native-default среда, деградационные тесты изолируют sandbox-addon явно.


## Часть A — таблица переноса (byte-exact, 2 файла)

| native | B | SHA256 | замыкание top-level (провери ПОЛНОСТЬЮ по F0) | новое размещение |
|---|---|---|---|---|
| `godot_tools/librarian.py` | 96 356 | `90f4f66440fa6ecb…` | difflib, json, os, re, time + `gd_api_cache` (алиас из engine-cache) + `minilich.ml_project_index` (см. D46) + `project_tools` (`can_read_project_path`, `describe_scene`, `read_project_file`, `search_project_text`) | `python/substrate/context/librarian.py` |
| `minilich/ml_project_index.py` | 64 059 | `474dcc3b959559b8…` | json, hashlib, os, re (stdlib) — перепроверь построчно | `python/substrate/context/ml_project_index.py` |

- Байты = native 1:1; импорты внутри файлов не переписывать (`import gd_api_cache`, `from minilich import ml_project_index`, `from project_tools import …` остаются; связь — только через связку).
- `minilich/__init__.py` (14 476 B, NN-пакет) НЕ переносится — решение пользователя о нейросети. Родительский пакет даёт связка (D46).
- Function-level `from minilich import ml_data` (librarian ~L898, телеметрия обкатки) — dormant-ветка: остаётся в байтах; при исполнении обязана падать честно (нет алиаса ml_data) — запинь это поведение, маскировать запрещено.
- Отклонение D46 (spec-before-code): размещение `substrate/context/`; синтетический родительский пакет `minilich` в связке — запись в sys.modules с атрибутом `ml_project_index` → реальный ported-модуль; НЕ копия native `__init__`; ничего из NN не импортирует; idempotent; rollback владеет только своими добавками; production-профили связку не импортируют.

## Часть B — SEC-ядро и корпус

SEC-ядро среза: librarian читает проект пользователя (search/fragments/describe_scene/autoloads) — все чтения через гард project_tools; обязательные матрицы corpus: traversal, UNC, симлинки, case-only dirs, UTF-8/не-UTF-8, бинарные файлы, отказы вне корня, read-only доказательства (дерево проекта неизменно до/после). Особое: `_log_query` ПИШЕТ в native — определи точную цель записи, изолируй в sandbox и запинь поведение побайтно (куда/что/когда пишет и когда молчит).

Корпус `fixtures/corpus/context/librarian/manifest.json` (bytes/SHA/provenance на синтетических fixture-проектах): сборка `answer()` (бюджет `budget_chars`, секции, усечение), токенизация запроса/синонимы/rerank, grep-фрагменты и лимиты, callers, autoloads, signal_wiring, `_symbol_card`, ветка `_godot_api` через `gd_api_cache` (деградационные кейсы с sandbox-addon по D44 + кейсы с реальным deployed-бандлом 1488 классов — по прецеденту engine-cache), `note_files_changed` (инвалидация индекса), семантика `ml_project_index` (индексация/поиск/snapshot/дедупликация на синтетических проектах).

Тесты `tests/py/context/test_librarian_*.py` ×2 (ordered/once-only, старые ID сохраняются). tests-map строку L77 обновлять только по факту покрытия; статус в parity остаётся skeleton с честной пометкой (прецедент api-core/routing/project-core: reference-срез ≠ ported-механика, selfcheck MODULE остаётся blocked/exit 2 — не поднимать).


## Часть C — связка, лимиты, мутации

Связка: +2 алиаса (`ml_project_index`, `librarian`) + синтетический родитель `minilich` (D46) — регистрация на явном импорте, порядок после engine-cache-алиасов; счётчик связки обновляется по D43 (токен-only + red-before-code). Пины: `sys.modules['ml_project_index'] is import_module(цель)`, откат владеет только своими добавками, `sys.path`/`meta_path`/`hooks` неизменны.

Лимиты (D47): классовое правило для `python/substrate/context/` — narrow FILE_MAX 3400 (red-доказательство ДО кода по шаблону D32/D39: пин класса краснеет на текущем cap, затем cap-правка, затем перенос); проверка в check_limits.py — только класс-правило, прежние 2 предупреждения неизменны.

Мутации (≥3, каждая red → byte-exact SHA/EOL restore → green):
1. Синоним-расширение запроса отключить (`_synonyms` → пусто) → корпус краснеет на rerank/синоним-кейсах;
2. Обход гарда (`can_read_project_path` пропустить в одной ветке) → SEC-матрица краснеет (вне-корневые/запрещённые пути читаются);
3. Бюджет усечения сдвинуть на 1 (`budget_chars` ±1) → корпус краснеет на boundary-кейсах;
4. (опционально) алиас-идентичность/D33 — красный на identity-тесте.

## Часть D — порядок, записи, границы, стопы

Порядок: §0 → tree-before → таблица замыкания (СТОП при любом не-stdlib/незаявленном) → red-доказательство D47 → перенос 2 файлов → связка (+2 алиаса + пакет-minilich) → corpus+тесты ×2 → мутации red→restore→green → гейты ×4 + security ×2 → full ×2 (старые ID/outcomes) → записи → tree-after → SHA-печать досье последней.

Записи: новый лист `docs/porting/librarian.md` (CRLF, spec-before-code, решения/отклонения, вердикт); WORKLOG — CRLF append с prefix-assert по факту; README — строка регистрации после конца строки engine-cache; deviations — D46/D47 (+ ссылки D43/D44/D45); parity — только L77 по факту; досье `%TEMP%\opencode\c8_audit\librarian-<дата>\` (tree-before/after, JUnit всех фаз, orig-копии, скрипты, §0-recount, SHA-печать последней).

Разрешено: tests/py/context/**, fixtures/corpus/context/**, fixtures/projects/** (новые fixture-проекты), python/substrate/context/**, правка runtime_bindings.py (только добавки), tools/check_limits.py (класс-правило), docs/{WORKLOG,deviations,tests-map,parity:L77,porting/librarian.md,porting/README.md}, досье.

Запрещено: байты замороженных эталонов вне временных мутаций (с точным restore), facade/transport, contract/, PROGRESS-статусы, native-источники, NN-модули (ml_model/ml_train/ml_tokenizer/ml_github/ml_fix/ml_data) и native minilich/__init__.py, другие tools/, внешняя сеть, реальный user:// телеметрия, reports/selfcheck, тесты других срезов вне пиновых правил D43/D45.

Стоп-условия: мутация не краснеет / гейт ok→fail / SHA-restore mismatch → STOP; замыкание тянет не-stdlib или NN → STOP (честный deferred, не «перенести нейросеть»); предусловие (engine-cache принят) не выполнено → не начинать; частичное исполнение легально (фиксируй фазу и причину); любое расхождение §0 с фактами → пересчёт до старта работ.


## Поправка F0-librarian (аудитор, 2026-11-06) — закрытие четырёх блокеров STOP

Признание аудитора: таблица замыкания части A была неполной — не перечисляла
function-level импорты (librarian L1214/L1221 `import function_card`, L898
`from minilich import ml_data`) и package-relative импорты внутри
ml_project_index. Правило впредь: таблицы перечисляют ВСЕ импорты, включая
function-level и относительные.

### A. Расширение таблицы переноса (решения пользователя зафиксированы)

| native | B | SHA256 | статус |
|---|---|---|---|
| `godot_tools/gd_semantic_parser.py` | 15 723 | `bf35dcea5e77011d…` | **D48** — расширение границы: чистый stdlib (только `re`), leaf, agent-функционален (semantic-разбор GD для карточек Библиотекаря; его же ждёт function_card). Размещение `substrate/context/gd_semantic_parser.py` |
| `minilich/ml_data.py` | 32 324 | `e13d56800d124627…` | **D49** — решение ПОЛЬЗОВАТЕЛЯ: переносится byte-exact как storage-инфраструктура ИНДЕКСА (librarian/ml_project_index требуют `ml_data.storage_dir` на L283/L287); нейросеть/обучение ОСТАЮТСЯ исключёнными (ml_model/ml_train/ml_tokenizer/ml_github — нет; NN-вызовы ml_data не задействуются). Размещение `substrate/context/ml_data.py` |
| `minilich/ml_project_index.py` | 64 059 | `474dcc3b959559b8…` | как было → `substrate/context/ml_project_index.py`; после D48/D49 импортируем |
| `godot_tools/librarian.py` | 96 356 | `90f4f66440fa6ecb…` | как было → `substrate/context/librarian.py` |

Дополнение замыкания ml_project_index: json, hashlib, os, re, **threading, time** (stdlib),
L35 `from . import ml_data` (резолвится ВНУТРИ `python.substrate.context` — модули лежат
рядом, отдельного legacy-алиаса ml_data НЕ нужно), L36 `import gd_semantic_parser`
(абсолютный — закрывается алиасом D48). После переноса ml_project_index импортируем.

### B. Связка (D46 уточнено, D50 новый)

- **+2 алиаса в BINDINGS**: `('gd_semantic_parser', …context.gd_semantic_parser)`,
  `('librarian', …context.librarian)` — в конец, после engine-четвёрки. 33 → **35**.
- **Синтетический родитель `minilich`** (librarian L36/L898 `from minilich import …`):
  ModuleType('minilich') в sys.modules с атрибутами `ml_project_index` и `ml_data`,
  привязанными К РЕАЛЬНЫМ импортированным модулям (identity: атрибут is
  import_module('python.substrate.context.…')). **__path__ НЕ выставлять** — двойной
  импорт одного кода под двумя именами запрещён. Конфликт с существующим/чужим
  'minilich' → отказ как у алиасов; rollback владеет только своей записью.
  Это документированное ИСКЛЮЧЕНИЕ из пина «alias is real module» (D46/D50).
- ml_data/ml_project_index как legacy-алиасы НЕ регистрируются (достижимы только
  через пакет и относительный импорт — единственный экземпляр каждого модуля).

### C. Исправление моего пункта: _log_query

Моё требование «dormant-ветка обязана падать честно» ПРОТИВОРЕЧИТ native:
L891–910 импортирует ml_data внутри try и ГЛОТАЕТ все исключения — native-поведение
есть тихий no-op при отсутствии ml_data. Пиновать НАТИВНОЕ молчание; твою статическую
спецификацию цели записи принять как корпус-спеку: `<history storage>/minilich/
librarian_log.jsonl`, fallback `<project>/.agent_history/minilich/librarian_log.jsonl`,
override `<addon>/minilich_brain`; append UTF8 JSON+LF, ts/root, ротация >262144 → .1;
sandbox-кейсы без единой реальной записи.

### D. function_card — не переносится (своя механика L24)

librarian L1214 (вне try) → честный ImportError на card-пути — запинь как поведение;
L1221 (в try) → молча. Никаких алиасов function_card/gd_functions/symbol_refactor_part1.

### E. Санкция на суффикс-пин engine-cache (D50)

`tests/py/engine_cache/test_engine_cache_binding.py:12`: разрешена токен-правка
`len(binding.BINDINGS)==33` → `==35` И `binding.BINDINGS[-4:]` → `binding.BINDINGS[-6:-2]`
(engine-четвёрка остаётся запиненной относительно конца после librarian-пары).
Остальные пины файла (строка 13 — первые 29 имён; late-failure на gd_lint; rollback)
совместимы: новые алиасы стоят ПОСЛЕ gd_lint и при срыве на gd_lint не создаются.
Red-before-code: твой статический tuple-контрпример принят как предварительное
доказательство; финальный красный прогон реального теста до правки токенов обязателен.
D43/D45 действуют; номер D50 в deviations.

### F. Цель после поправки

full (6831 + новые) / 2 legacy ×2, все прежние пары ×2 зелёные; glue ≤72 соблюдён
(64 + 2 строки алиасов = 66); сор-пины честные; гейты ×4 + security ×2; selfcheck
context.ask остаётся blocked/exit 2 честно; parity L77 skeleton с пометкой.

### G. Порядок

Полный перечитанный мандат → свежий §0 (пересчитать, CURRENT state) → tree-identity
с STOP-досье librarian-20261106 → D48/D49/D50 в deviations (CRLF, префикс-ассерты) →
перенос 4 файлов → связка (+2 алиаса, шим minilich) → суффикс-пин токен-правка →
corpus/тесты ×2 → мутации ≥3 (storage_dir sandbox-изоляция, deny-матрица чтений,
semantic-parse отключение) → гейты → записи (лист/WORKLOG/PROGRESS) → seal последней.


## Поправка F1-librarian (аудитор, 2026-11-08) — corrected-native пины и разрешение на перенос

Native-фикс проверен аудитором по diff (librarian.review.diff / ml_project_index.review.diff):
`can_read_project_path` добавлен на ВСЕ пути чтения цепочки (vocab/structure/candidates/
needle-группировка/symbol-names + зеркально в ml_project_index), traversal-отказ сохранён,
allow_addons/allow_self_edit/addon_dir семантика сохранена. Security-corpus 54 fail →
**72/72 ×2** — это и есть red→green доказательство. Fix принят как native-authoritative
(решение пользователя: native чинится первым).

### Обновлённая таблица пинов (corrected-native)

| файл | B | SHA256 | EOL |
|---|---|---|---|
| `librarian.py` | **97 676** | **`340b5dd2be96ebc4…`** | CRLF 1551 |
| `ml_project_index.py` | **65 753** | **`2f7694a91a48e294…`** | mixed LF 1120 / CRLF 866 |
| `ml_data.py` | 32 324 | `e13d56800d124627…` (без изменений) | LF 757 |
| `gd_semantic_parser.py` | 15 723 | `bf35dcea5e77011d…` (без изменений) | LF 392 |

Исторические пины (90f4f664/474dcc3b) — в досье native-fix; переносить ИЗ corrected-native,
byte-exact с родными EOL каждого файла (конвертация запрещена).

### Конфликт CRLF/LF логгера — решён измерением

Спека части B писала «append UTF8 JSON+LF» по статическому анализу. Измерение native
после фикса: JSONL-лог пишется строками с **CRLF**. Правило: корпус пинует ИЗМЕРЕННЫЙ
native-формат (CRLF JSONL, ротация >262144 → .1, поля ts/root — по пробам досье); если
какая-то ветка пишет иначе — пинуется измеренный формат той ветки. Логгер молча не менять,
код не трогать — байт-exact переносит формат как есть, спека корпуса следует коду.

### Разрешение

Перенос byte-exact ИЗ corrected-native разрешён и является текущим шагом: 4 файла →
substrate/context/, связка (+2 алиаса, шим minilich D46), D48/D49 в силе, суффикс-пин D50
(count 33→35, `[-4:]` → `[-6:-2]`), guard-corpus 72/72 входит в focused ×2, полный набор
проверок мандата (F0-исправленное замыкание, native-молчание _log_query, dormant
function_card, sandbox-изоляции). Паритет context.ask не заявляется (MODULE0/skeleton).
