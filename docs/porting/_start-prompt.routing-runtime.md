# Стартовый промпт: срез «runtime-контекст + routing» (context.runtime_snapshot + assistant.routing)

Класс: **жёсткий**. Модель: **gpt-6.1-sol**. Приёмка: независимый аудит.
Один срез, две части (A → B последовательно), один вердикт; частичный вердикт допустим
(назвать фазу и причину). Часть B выполняется только после зелёной части A.

## 0. Сначала пересчитай сам

Все числа ниже — снапшот на момент выдачи и УСТАРЕЮТ. Пересчитай и запиши фактические
значения в досье (`§0-recount.json`):

- `project.godot` — 335 B, SHA `958b3a92…` (корень agent-rebuild).
- `docs/WORKLOG.md` ≈ 761 427 B, SHA `6a1cdf3a…` — только CRLF-добавка с префикс-ассертом
  по пересчитанному размеру (предыдущий ассерт поймал чужие записи — рассчитывай на это).
- `docs/parity.md` — LF, SHA `5d1cec37…`, не трогать кроме строк L80 (`context.runtime_snapshot`)
  и L89 (`assistant.routing`); строки обновлять ТОЛЬКО по факту (см. «Отклонение в пользу честности»).
- Гейты: lint_arch ~591 файлов/0, check_limits ok/2 (ровно 2 прежних warning: split_py 11,
  editing 8400), gen_contract --check 28/0, security_audit ok/0.
- Регрессии: full non-live 5872 pass / 2 legacy skip ×2 (IDs равны), focused 253×2,
  frozen 230×2 (browser 141 + SEC-03 72 + B-2 17).
- Гигиена: reports/selfcheck 44, .uid 86, .pyc 0, сентинелы fixtures (4 файла
  `fixtures/projects/corpus/editing/**/__pycache__/ref.gd`).
- Замороженные пины (byte-exact; вне временных мутаций не трогать): facade `6abe81d2…`,
  browser_manager `4afd245f…`, cdp_ws `3b5298dd…`, net_monitor `54167afb…`, sites `06da9270…`,
  live_input `cd2c6ccf…`, ai_studio_net `3d9a3fb4…`, qwen_net `57d1ab2b…`,
  browser_backend `21e5e911…`, security_audit `c59e4faf…`, parsers (7 файлов, см. api-core
  пин-таблицу), API-ядро (11 файлов: api_keys `340f73fb…`, providers `a269ea59…`,
  providers_catalog `8860d454…`, model_cache `58895c14…`, openai_compat `6b1022ae…`,
  anthropic_compat `c7b8f32c…`, agent_prompts `633ad387…`, rate_limit `a9d6d9f2…`,
  md_to_bbcode `e90a7615…`, chat_store `b275c7c2…`, api_history `cce2c180…`).
- Python: `python -B -X utf8`; pytest: `-p no:cacheprovider`, basetemp/JUnit вне репо,
  `--import-mode=importlib`.

## A. Часть A: context.runtime_snapshot (+ editor-контекст)

Перенос byte-exact двух файлов — единственные недостающие зависимости api_backend:

| native | размер | SHA256 (первые 16) | заметки |
|---|---|---|---|
| `python/godot_tools/runtime_debug.py` | 12251 | `ed7d6087c84f1634` | 16 top-level def/class; импорты только stdlib (json/secrets/time) |
| `python/server/editor_context.py` | 14161 | `32613d2844967413` | ноль top-level импортов — самодостаточный |

- Размещение: предложить в deviations (spec-before-code), по умолчанию
  `substrate/editor/` (editor_context) и рядом runtime_debug; `__init__.py` по образцу соседей.
- Байты = native, импорты внутри эталонов не правятся (R-08).
- Корпус: синтетические кейсы с bytes/SHA/provenance — `strip_status`, сборка runtime-снимка,
  user_prompt_without_context, негативные/краевые ветки (по фактическому коду, не по догадкам).

## B. Часть B: assistant.routing (api_backend)

| native | размер | SHA256 (первые 16) | новое место |
|---|---|---|---|
| `python/backends/api_backend.py` | 91906 | `93d22fb580b66e88` | `substrate/llm/backends/api_backend.py` (сиблинг `browser/backends/browser_backend.py`; альтернатива — через deviations) |

- Замыкание после части A полностью закрыто: api_history, api_keys, anthropic_compat,
  catalog(→providers_catalog), md_to_bbcode, openai_compat, parser_base, providers,
  rate_limit, agent_prompts (константы), editor_context, runtime_debug — все уже ported
  и связаны через `runtime_bindings.py`. Сам пересчитай и запиши таблицу замыкания в досье.
- Внутри эталона импорты не правятся; недостающие алиасы добавляются в связку
  (`runtime_debug`, `editor_context`, `api_backend`; `parser_base` — если ещё не привязан).

### Связка (расширение runtime_bindings.py)
Пины D33 сохраняются: регистрация только при явном import связки, идемпотентность,
алиас IS реальный substrate-модуль, rollback только новых алиасов, без sys.path/meta_path,
production-профили связку не импортируют.

### Транспорт и сеть — критические ограничения
- ВСЕ транспортные вызовы в тестах — mock/локальный recorded-сервер 127.0.0.1. Внешняя сеть
  ЗАПРЕЩЕНА. Реальные ключи запрещены (синтетические, sandbox-каталог, маскирование как в
  api-core: имена заголовков сохраняются, значения — `<redacted>` только в корпусных
  фикс-кейсах нового наблюдателя, D37-прецедент).
- Корпус: `fixtures/corpus/llm/routing/manifest.json` — SSE-потоки (openai + anthropic),
  ошибки/ретраи/таймауты (детерминированное время), rate_limit-расписание с фиксированным
  seed, выбор провайдера/модели/базового URL, proxy/DNS-ветки (без реального DNS —
  мок, поведение честно pin'ится, D36-граница: реальный DoH вне среза), streaming-кадры,
  отмена/таймаут-ветки. Каждый кейс: bytes/SHA/provenance.

### Тесты
`tests/py/llm/test_llm_routing_*.py` — юниты транспорта/ретраев/выбора модели, связка,
интеграция с compat-модулями. Прогон ×2 (IDs равны). tests-map — только строки, закрытые
фактически доказанными кейсами; частичное покрытие = заметка в листе, не смена статуса.

## C. Лимиты и мутации

- Классовое правило check_limits для verbatim-эталонов новых папок по образцу D32/D35
  (FILE_MAX 3400) — правка tools/check_limits.py ТОЛЬКО классовым правилом, прежние
  2 warning остаются.
- Мутации ≥2 на новом коде (например: срыв ретрая/таймаута в api_backend; порча
  strip_status в editor_context) + ≥1 на эталоне (правка внутри api_backend/editor_context/
  runtime_debug → red → byte-exact restore по SHA → green). Каждая: red-прогон с именами
  упавших, restore с проверкой SHA и EOL, green-повтор. Логи и JUnit — в досье.

## D. Отчётность и порядок

Порядок: §0 → tree-before → таблица замыкания → классовое правило → перенос A → связка
(A-алиасы) → corpus/тесты A → перенос B → связка (B-алиасы) → corpus/тесты B → мутации →
гейты ×4 + security_audit ×2 → записи → SHA-печать досье последней.

Записи:
- новый лист `docs/porting/routing-runtime.md` (CRLF, spec-before-code, решения, вердикт);
- CRLF-добавки: WORKLOG (префикс-ассерт), README (регистрация/статус);
- parity.md — ТОЛЬКО L80 и L89, по факту (см. отклонение ниже); tests-map — по факту;
- досье `%TEMP%\opencode\c8_audit\routing-runtime-<date>\`: tree-before/after, JUnit всех
  фаз, orig-копии мутированных файлов, скрипты, SHA256-final.json записан последним.

Отклонение в пользу честности: если MODULE-интеграция не поднимает механику
(substrate-reference без HTTP/интеграции), НЕ поднимай статус в parity — оставь skeleton
и зафиксируй решение в листе (прецедент api-core). Никаких «ported» без фактического
доказательства.

## E. Вне границы (честный deferred)

- flask/chat_routes (ADR интеграционной стадии), server_state/history_manager,
  answer_judge (тянет gd-механики: gd_lint, gd_api_check, tscn_lint, symbol_refactor,
  high_level_actions, minilich, project_tools), librarian/context.ask (96356 B, `90f4f664…`,
  тянет gd_api_cache/minilich/project_tools), локальные бэкенды, DNS/DoH (D36), browser
  frozen-файлы, substrate-selfcheck runtime.

## F. Стоп-условия

- Мутация не краснеет на новом кейсе → стоп.
- Гейт ok→fail или restore SHA/EOL mismatch → стоп.
- Замыкание тянет незапланированную подсистему (flask, gd-механики, сервер) → честный
  deferred, не «перенести с заглушкой».
- Внешняя сеть/реальные ключи → немедленный стоп.
- Частичное выполнение — легитимный вердикт (фаза + причина).

