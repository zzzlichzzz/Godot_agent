# Мандат: срез «gd-ядро: история + кэш движка» (engine-cache)

Класс: жёсткий. Модель: gpt-6.1-sol. Приёмка: независимый аудит. Частичный вердикт легален (укажи фазу и причину).

Цель: недостающее gd-ядро — `history_manager` (слой хранения) и семейство `gd_api_*`/`gd_lint` — открывает механики `engine_kb.engine_info` и `engine_kb.api_cache_refresh`, снимает deferred-блокировку с `tscn_lint` (аудит C.8) и является предпосылкой `answer_judge`/`action_judge`. `engine_kb.class_api` (C.11) не трогается: его read-only проекция (`substrate/store/api_cache_store.py`, `substrate/engine/api_cache_loader.py`) остаётся принятой публичной механикой; byte-exact `gd_api_cache.py` сосуществует с ней как эталон (связь фиксируется в отклонении, не кодом).

## §0 — самопересчёт (обязателен, до любых правок)

Пересчитай и запиши в `§0-recount.json`; расхождение с обещанным ≠ стоп, но каждое расхождение объясни в листе.

- Корень проекта: `D:\vajno\Godot\agent-rebuild\addons\godot_agent` (не каталог плагина — `project.godot` 335 B `958b3a92…` лежит на уровень выше `addons/godot_agent`? нет: корень репо = `agent-rebuild`, плагин = `agent-rebuild\addons\godot_agent`; все пути ниже — от корня репо).
- `docs/WORKLOG.md` ≈786 581 B, sha-префикс `75d151fc610cfedb`; append только чистой CRLF-добавкой с prefix-ассертом (промежуточные appends портёра/аудитора возможны — пересчитай).
- `docs/parity.md` 24 262 B `5d1cec37…` (LF-файл, 194 строки) — не трогать, кроме строк L42/L44 по факту (см. «Записи»).
- `docs/porting/README.md` 33 466 B `2503bb07…` (CRLF, bareLF=0): L71 project-core принят; новую строку регистрации вставляй ПОСЛЕ неё отдельным вызовом (урок r7: не в середину чужой строки, только CRLF).
- Гейты: lint_arch 599 файлов/0 нарушений; check_limits ok/2 (те же 2 legacy: split_py 11, editing 8400); gen_contract --check 28/0; security_audit ok/0.
- Регрессии: полный non-live 6562 passed / 2 legacy skip (symlink WinError 1314) ×2, ordered/once-only; focused 314×2; frozen 230×2; api-core 253×2; project-core native 288×2. Все прежние ID/outcomes сохраняются.
- Hygiene: reports/selfcheck = 44 .json; *.uid = 86; *.pyc = 0; 4 сентинела `fixtures/projects/corpus/editing/**/__pycache__/ref.gd`.
- Замороженные пины (не трогать байты вне временных мутаций с побайтовым восстановлением): facade 5333 B `6abe81d2…`; browser_manager 12 663 `4afd245f…`; cdp_ws 15 867 `3b5298dd…`; net_monitor 24 206 `54167afbb87d9a9b…`; sites 9906 `06da9270…`; live_input 4437 `cd2c6ccf…`; ai_studio_net 9735 `3d9a3fb4…`; qwen_net 12 199 `57d1ab2b…`; browser_backend 3380 `21e5e911…`; security_audit 16 153 `c59e4faf…`; 7 парсеров (parser_base 198 211 `7b2ce9f1…`, ai 37 004, arena 57 066, deepseek 14 989, kimi 25 355, qwen 37 217, text_sanitize 3305); API-ядро 11 файлов (api_keys 80 764 `340f73fb…`, providers 73 572 `a269ea59…`, providers_catalog←catalog 60 359 `8860d454…`, model_cache 12 322, openai_compat 39 682, anthropic_compat 10 859, agent_prompts 45 177, rate_limit 10 841, md_to_bbcode 10 185, chat_store 11 045, api_history 23 452); routing: runtime_debug 12 251 `ed7d6087…`, editor_context 14 161 `32613d28…`, api_backend 91 906 `93d22fb5…`; project-core: project_tools 102 471 `79e9b035…`, project_settings_actions 13 735 `fcdb4635…`; связка runtime_bindings 2877 `432a9b32…`; check_limits 5681 `862ce80e…`; C.11-проекция: `substrate/engine/api_cache_loader.py` 130 B, `substrate/store/api_cache_store.py` 3812 B.
- Python 3.14: `python -B -X utf8`; pytest: `no:cacheprovider`, basetemp и JUnit ВНЕ репо, `--import-mode=importlib`; прогоны ordered/once-only (пары до/после с равными ID).
- Урок F0: в таблице замыкания — ПОЛНЫЕ списки top-level импортов (включая stdlib). Стоп только на не-stdlib или незаявленном.
- Урок wb: никаких `open(...,'wb')` без бэкапа и пост-ассерта; правки документ-файлов — временные скрипты с prefix/post-ассертами.
- SEC-06 урок: любой красный флаг security_audit (в т.ч. на новых данных) — STOP без «подгонки», с сохранением первого состояния.

## Часть A — таблица переноса (byte-exact, 5 файлов)

| native (godot_tools/) | B | SHA256 | замыкание top-level (полное) | новое размещение |
|---|---|---|---|---|
| `history_manager.py` | 48 840 | `f665517341abbab9…` | os, json, time, uuid, shutil, hashlib, tempfile, threading, functools.wraps + `project_tools` (`_resolve_safe_path`, `begin_case_only_dir_casing`) — всё уже ported | `python/substrate/store/history_manager.py` |
| `gd_api_cache.py` | 11 545 | `6e6f5e0c83de40d2…` | os, json + `history_manager` — закрывается этим же срезом | `python/substrate/engine/gd_api_cache.py` |
| `gd_api_check.py` | 9137 | `b9e0df9f604ce376…` | re + `gd_api_cache` — закрывается этим же срезом | `python/substrate/verification/gd_api_check.py` |
| `gd_lint.py` | 9640 | `666186488cc9e7f4…` | re | `python/substrate/verification/gd_lint.py` |
| `agent_api_cache/default_api_cache.json` | 2 004 630 | `7352d27c8d8ed77b…` | данные (не код) | `agent_api_cache/default_api_cache.json` — КОРЕНЬ плагина, byte-exact |

Порядок переноса строго: history_manager → gd_api_cache → gd_api_check → gd_lint → data. Байты = native 1:1, импорты внутри файлов не переписывать (старые абсолютные `import history_manager` и т.п. остаются; связь — только через связку, п. B.2).

Размещение — отклонение D40 (spec-before-code): `store/` рядом с принятой `api_cache_store.py`; `engine/` рядом с `api_cache_loader.py`; `verification/` — новый каталог для gd-проверок. Иное размещение — только через отклонение с обоснованием.

Отклонение D41 (пин данных): `agent_api_cache/default_api_cache.json` — данные кэша движка, byte-exact копия; после среза SHA обязан совпадать с native (`7352d27c…`); тесты НИКОГДА не пишут в настоящий файл — только в sandbox-копии. SEC-06: файл проходит security_audit как данные репозитория (2 МБ JSON кэша Godot API, секретов нет; любой флаг — STOP).

Связка (расширение `runtime_bindings.py`, пины D33): +4 алиаса `history_manager`, `gd_api_cache`, `gd_api_check`, `gd_lint` — регистрация на явном импорте, idempotent, alias is real substrate module, порядок после существующих (project-алиасы последними), production-профили связку не импортируют. `agent_api_cache` модульного алиаса НЕ получает (данные, не модуль).


## Часть B — корпус, тесты, мутации, гейты

B.1 Корпус: `fixtures/corpus/engine-cache/manifest.json` + кейсы с bytes/SHA/provenance. Обязательные ветки:
- history_manager: атомарная запись (tempfile+replace), откат при сбое, блокировки (однопоточные последовательности + случай «файл занят»), `begin_case_only_dir_casing` поверх project_tools, декоратор-обёртки, путь user://-хранилища через sandbox.
- gd_api_cache: чтение кэша (валидный/битый/пустой/устаревший JSON), `engine_info`-ветка (версия/поля из шапки кэша), `api_cache_refresh`-ветка — ЗАПИСЬ только в sandbox-копию `agent_api_cache/` (данные снапшота подаются на вход как bytes, live Godot не запускается).
- gd_api_check: deny/allow-матрица на существующих fixture-проектах `fixtures/corpus/verification/api_check/*` (они уже в дереве) + 2–3 новых синтетических.
- gd_lint: синтетика на re-правилах (fail/skip/pass), без копирования старых тестов.
Тесты: `tests/py/engine_cache/` (`test_history_*.py`, `test_gd_api_cache_*.py`, `test_gd_api_check.py`, `test_gd_lint.py`, `test_engine_cache_binding.py`) ×2, ordered/once-only. tests-map — только по факту покрытия.

B.2 Мутации ≥4 (каждая: red → byte-exact restore SHA/LF/CRLF → green):
1. history_manager: сломать атомарную замену (tempfile → прямая запись) — красный по history-корпусу.
2. gd_api_cache: пропустить валидацию битого кэша — красный по кэш-корпусу.
3. gd_api_check: deny-набор урезать — красный по api_check-матрице.
4. эталон: gd_lint regex ослабить — красный по lint-корпусу.
Мутации замороженных файлов — только временные, с побайтовым восстановлением.

B.3 Гейты ×2 (до записей и после): lint_arch (ожидаю ~610/0), check_limits (классовое правило D42 для byte-exact классов `substrate/engine/`, `substrate/store/`, `substrate/verification/` — FILE_MAX 3400 по образцу D38/D39, red-доказательство правила ДО кода; прежние 2 warning неизменны), gen_contract --check 28/0, security_audit ok/0. Полный non-live ×2 (6562+новые pass), focused (314+новые)×2, frozen 230×2, api-core 253×2, project-core 288×2. Selfcheck честный: engine_kb.* остаются blocked/не-ported (MODULE-интеграция отдельно); reports/selfcheck = 44 файла не изменять.

## Порядок
§0 → tree-before → пересчёт замыкания → red-доказательство правила лимитов → перенос A (порядок таблицы) → связка +4 → корпус+тесты ×2 → мутации → гейты ×2 → записи → tree-after → SHA-печать досье последней.

## Записи
- Новый лист `docs/porting/engine-cache.md` (CRLF): вердикты, D40/D41/D42, инциденты.
- WORKLOG: CRLF-append с prefix-ассертом (пересчитай актуальный размер/sha!).
- README: строка регистрации после L71 (project-core), не задевая её.
- parity.md: только L42/L44 по факту — статус остаётся `skeleton`, добавить пометку «reference-срез принят (дата), MODULE отдельно» (прецедент api-core/routing/project-core; parity LF — правка LF-only, без CRLF).
- Досье: `%TEMP%\opencode\c8_audit\engine-cache-<дата>\`: tree-before/after, JUnit всех фаз, orig-копии, скрипты, SHA-печать последней.

## Запрещено
Байты замороженных эталонов вне временных мутаций; facade/транспорт; `contract/`; parity кроме L42/L44; PROGRESS (кроме честных добавок о ходе); таблица 44 механик; native-источники; чужие `tools/`; внешняя сеть; реальный `agent_api_cache/` из тестов (только sandbox); reports/selfcheck/*.json.

## Стоп-условия
Мутация не красная → стоп. Гейт ok→fail или SHA-restore mismatch → стоп. Замыкание тянет незапланированное (flask, api_backend, gd-механики answer_judge) → честный deferred. Внешняя сеть/реальный кэш перезаписан → немедленный стоп + восстановление из native. Частичное исполнение легально вердиктом.

## Поправка F1 (аудитор, 2026-11-06) — разрешение на узкую правку fixed-count пина связки

STOP preflight1 признан честным: принятый тест `tests/py/project/test_project_tools_binding.py` пинит ровно 29 алиасов (строка 16, `assert len(binding.BINDINGS) == 29`), мандат добавляет 4 → конфликт, не описанный в границах. Разрешаю:

1. ЕДИНСТВЕННАЯ разрешённая правка принятого теста: строка 16, `== 29` → `== 33` (замена одного токена-числа). Остальные байты файла не трогаются; файл LF-only (native-линия, было 4633 B `ba0f20a4…`, 94 LF / 0 CRLF) — LF-дисциплина сохраняется, конвертация в CRLF запрещена.
2. Красное доказательство ДО кода связки: с ожиданием 33 при фактических 29 тест краснеет (твоё in-memory подтверждение принято, сохрани протокол в досье); после расширения связки — зелёный.
3. Порядок: 4 новых алиаса добавляются В КОНЕЦ BINDINGS, после project-пары. Относительный пин строки 18 (`BINDINGS[parser_end+1:parser_end+3] == tuple(TARGETS.items())`) обязан остаться зелёным; тесты sanitizer/rollback/conflict — без изменений, зелёные.
4. deviations.md, D43: fixed-count пин связки обновляется при каждом расширении связки минимальной правкой числа; red-before-code обязателен; счётчик всегда равен фактическому len(BINDINGS); никакие другие пины принятых тестов не правятся без явного разрешения аудита.
5. Продолжение — в том же досье engine-cache-20261106: перед работой подтверди tree-identity с STOP-срезом (репо == tree-after STOP, seal `dc934ed0…` сохранён), затем пересчитай §0 по факту и продолжай по порядку мандата. STOP-записи портёра остаются в протоколе как доказательство честной остановки.

## Поправка F2 (аудитор, 2026-11-06) — два блокера resume-f1

STOP resume-f1 признан честным; оба блокера проверены мной по коду и досье. Разрешаю:

### Блокер 1 — пин длины связки (D43-класс, пиновая правка)
Единственная разрешённая правка: `tests/py/browser/test_browser_runtime_binding.py` строка 34, `<= 60` → `<= 72` (файл CRLF — сохранить байт-в-байт вне токена; текущая связка 64 строки). Обоснование headroom: запланированный срез librarian добавит ~3-4 алиаса. Доказательство работоспособности guard'а: временно удлиить связку до 73 строк → тест красный под `<= 72`; восстановить байт-в-байт; затем зелёный. Номер в deviations: D45 (пиновые правки cap'ов связки — токен-only, red-proof обязателен).

### Блокер 2 — коллизия bundled cache (только test-side изоляция)
Механика подтверждена: `api_cache_store.py:49-53/82-86` — fallback на `addon/agent_api_cache/default_api_cache.json`; `bootstrap.py:57` — `addon_dir=AGENT_DIR`; `AGENT_DIR=ROOT` (bootstrap.py:30; также используется на :98 — учти при выборе механизма). Разрешено:
1. Новый общий helper/fixture в tests/py/integration/ (conftest.py или helper-модуль): sandbox addon-dir (tmp, без agent_api_cache/); точечная подмена ТОЛЬКО источника addon_dir для api_cache при сборке агента. Предпочтительный механизм — monkeypatch `bootstrap.ApiCacheStore` с привязкой addon_dir=sandbox (не задевает :98); monkeypatch `bootstrap.AGENT_DIR` допустим ТОЛЬКО если задокументируешь, что affected-путь не достигает :98.
2. Подключение изоляции к деградационным кейсам ровно в 5 файлах: test_api.py (013-016, replaced_or_removed), test_api_check.py (033-035, observes_changes), test_verify.py (001-003, 023, 024, 031, 045, 071, 072), test_verify_bom.py (045), test_tscn_lint_ports.py::test_default_bootstrap_binds_consumer_protocols. НОЛЬ изменений ассертов/ожиданий — только явная фиксация предусловия «среда без bundled default».
3. Прецедент уже принят: test_bundled_legacy_cache_is_read_without_migration_or_write использует синтетический addon — тот же паттерн изоляции.
4. НЕ трогать: api_cache_store.py (3812 B `352f9e9b…`), bootstrap.py, C11-семантику, corpus-ожидания, frozen-байты.
5. НОВЫЙ обязательный тест в tests/py/engine_cache/: deployed-bundle fallback для проекта без кэша при реальном ROOT — classes=1488, version `4.6.3-stable (official)` (пины из твоего cache-fallback-probe; это теперь честное native-default поведение, ставшее реальным благодаря D41).
6. deviations D44 — правило видимости deployed-данных: данные в repo-root = native-default среда; деградационные тесты обязаны изолировать deployed-данные явно; изменение ожиданий по средовым причинам — только через явное решение аудита.

### Цель после F2
full 6833 collected → **6831 passed / 2 legacy skip** ×2 (ordered/once-only, старые IDs сохранены); frozen **230×2**; browser binding зелёный; native 228×2 / focused 269×2 / combined 583×2 / API 253×2 / project-native 288×2 сохраняются; мутации 7/7 с byte-exact restores; гейты ×4 + security ×2; selfcheck engine_kb.* остаётся blocked/exit 2 честно; продолжение в том же досье после подтверждения tree-identity с resume-f1-срезом.

