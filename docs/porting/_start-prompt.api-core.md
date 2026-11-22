# Стартовый промпт: срез «API-ядро LLM» (assistant.model_choice + assistant.history + база routing)

Класс: **жёсткий**. Модель: **gpt-6.1-sol**. Приёмка: независимый аудит.
Один вердикт на срез; частичный вердикт допустим (честно назвать фазу и причину).

## 0. Сначала пересчитай сам

Все числа ниже — снапшот на момент выдачи и УСТАРЕЮТ после чужих записей.
Перед началом пересчитай и запиши фактические значения в досье (`§0-recount.json`):

- `project.godot` — 335 B, SHA `958b3a92…` (лежит в КОРНЕagent-rebuild, не в plugins-папке).
- `docs/WORKLOG.md` ≈ 749947 B, SHA `5340e0a0…` — только CRLF-добавка в конце, с префикс-ассертом по пересчитанному размеру.
- `docs/parity.md` — LF-файл, SHA `5d1cec37…`, не трогать кроме строк L87 (`assistant.history`) и L88 (`assistant.model_choice`).
- Гейты: lint_arch ~583 файлов/0, check_limits ok/2 (ровно 2 прежних warning: split_py 11, editing 8400), gen_contract --check 28/0, security_audit ok/0.
- Фокус-регрессии: runtime 141×2, SEC-03 72/72, B-2 17/17.
- Гигиена: reports/selfcheck 44, .uid 86, .pyc 0, 4 сентинела fixtures.
- Замороженные пины (byte-exact, трогать запрещено вне временных мутаций): facade `6abe81d2…`, browser_manager `4afd245f…`, cdp_ws `3b5298dd…`, net_monitor `54167afb…`, sites `06da9270…`, live_input `cd2c6ccf…`, ai_studio_net `3d9a3fb4…`, qwen_net `57d1ab2b…`, browser_backend `21e5e911…`, security_audit `c59e4faf…`, parsers: parser_base `7b2ce9f1…`, arena `cdc01c59…`, ai `20b0cf87…`, qwen `e0b888fe…`, kimi `f0db0f5c…`, deepseek `554b6505…`, text_sanitize `2c18bbef…`.
- Python: `python -B -X utf8`; pytest: `-p no:cacheprovider`, basetemp и JUnit ВНЕ репо, `--import-mode=importlib`.

## A. Перенос byte-exact (11 файлов)

Замыкание проверено аудитором: все 11 замыкаются на stdlib + друг друга.
Сам пересчитай и запиши таблицу в досье. Внутри эталонов импорты НЕ править (R-08).

| native | размер | SHA256 (первые 16) | новое место |
|---|---|---|---|
| `python/api/api_keys.py` | 80764 | `340f73fbf36b80bd` | `substrate/llm/api/api_keys.py` |
| `python/api/providers.py` | 73572 | `a269ea59ce55d390` | `substrate/llm/api/providers.py` |
| `python/api/catalog.py` | 60359 | `8860d4544a93ceb8` | `substrate/llm/api/providers_catalog.py` (замена стаба 145 B; байты native) |
| `python/api/model_cache.py` | 12322 | `58895c14b6507ee4` | `substrate/llm/api/model_cache.py` |
| `python/api/openai_compat.py` | 39682 | `6b1022aeb3303a49` | `substrate/llm/api/openai_compat.py` (замена стаба) |
| `python/api/anthropic_compat.py` | 10859 | `c7b8f32c22828d60` | `substrate/llm/api/anthropic_compat.py` (замена стаба) |
| `python/server/agent_prompts.py` | 45177 | `633ad387d4ab5b83` | `substrate/llm/api/agent_prompts.py` (или `llm/prompts/` — через deviations) |
| `python/server/rate_limit.py` | 10841 | `a9d6d9f227bc8f16` | `substrate/llm/api/rate_limit.py` |
| `python/server/md_to_bbcode.py` | 10185 | `e90a7615a0e6baa9` | `substrate/llm/api/md_to_bbcode.py` |
| `python/server/chat_store.py` | 11045 | `b275c7c22a9c6723` | `substrate/llm/api/chat_store.py` |
| `python/server/api_history.py` | 23452 | `cce2c180a471d503` | `substrate/llm/api/api_history.py` |

Стабы `llm/models.py`, `llm/provider_base.py`, `llm/secrets.py` НЕ трогать — их судьба
на этапе routing/локальных бэкендов. `__init__.py` по образцу соседей.

## B. Вне границы (честный deferred, не «перенести с заглушкой»)

- `server/chat_routes.py` (77333 B, `91c8a968…`) — импортирует **flask**, которого в новом
  дереве нет; решение о flask/HTTP-сервере — ADR на интеграционной стадии. НЕ переносить.
- `backends/api_backend.py` (91906 B, `93d22fb5…`) — тянет `runtime_debug` (skeleton в новом
  дереве). Переносится после `context.runtime_snapshot`. Сейчас — deferred.
- `server_state.py` / `history_manager.py` (48840 B, тянет project_tools) — свой будущий мандат;
  шов `server_state → runtime_owner` уже существует (D33), не трогать.
- Локальные бэкенды, `editor_context`-биндинг, `minilich` — вне среза.
## C. Связка (расширение D33-модуля)

Расширить `substrate/llm/runtime_bindings.py` алиасами: `api_keys`, `providers`,
`model_cache`, `catalog → providers_catalog`, `openai_compat`, `anthropic_compat`,
`agent_prompts`, `rate_limit`, `md_to_bbcode`, `chat_store`, `api_history`.
Пины D33 неизменны: только явный импорт связки, идемпотентность, алиас `is`
реальный модуль, отказ при чужом алиасе, откат только новых алиасов,
запрет sys.path/meta_path/PathHook, production-профили/bootstrap связку не импортируют.
Спецификация до кода. Лимиты: классовое правило для verbatim-эталонов
`substrate/llm/api/` (FILE_MAX 3400) по образцу D32 — правка только в
`tools/check_limits.py` классовым правилом, прежние 2 warning остаются ровно двумя.

## D. Corpus и тесты (без сети, без секретов)

- `fixtures/corpus/llm/api/manifest.json` + inputs по образцу browser/runtime:
  каждый кейс — JSON с bytes/SHA/provenance, источник — native поведение и старые
  тесты (`python/tests/`, 157 файлов) как репро-источник БЕЗ копирования их кода.
- Покрыть: openai_compat (SSE-потоки, error-кадры, частичные чанки), anthropic_compat
  (event-потоки через oc), md_to_bbcode (пары вход/выход), catalog (разбор ответов
  моделей, оффлайн-функции; сетевой fetch — только mock/локальный 127.0.0.1),
  model_cache (кэш/устаревание), providers (resolve/set/cooldown/defaults),
  api_keys (add/set/delete/resolve/маскирование), rate_limit (расписание пауз,
  фиксированный seed для random), chat_store (запись/чтение во временном каталоге),
  api_history (бюджет API_HISTORY_BUDGET, декоратор).
- SEC: настоящие ключи ЗАПРЕЩЕНЫ — только синтетические фикс-ключи; хранение api_keys
  на диске — только в sandbox-каталоге теста (monkeypatch/env), ни одного пути
  пользователя; маскирование в отчётах не ослаблять; внешняя сеть запрещена.
- Тесты `tests/py/llm/test_llm_api_*.py` + корпусные прогоны ×2.
- tests-map: закрытие строк ТОЛЬКО по фактическому покрытию кейсов, построчно.

## E. Свои мутации

Минимум 2 на новом коде (примеры: удаление cooldown-логики в providers;
изменение парсинга SSE-чанка в openai_compat) и минимум 1 на эталоне
(например правка regex в md_to_bbcode → red → byte-exact restore по SHA → green).
Каждая мутация: красный список тестов, byte-exact восстановление, зелёный повтор.

## F. Порядок, записи, стоп-условия

Порядок: §0 → tree-before → таблица замыкания → классовое правило лимитов →
перенос byte-exact → связка → corpus+тесты → мутации → гейты → записи → seal.

Записи: `docs/porting/api-core.md` (новый лист, CRLF, spec-before-code, решения,
вердикт); appends в WORKLOG (CRLF, префикс-ассерт) и README (регистрация среза);
parity.md — ТОЛЬКО строки L87/L88 → `ported` (остальное frozen); tests-map — только
api-строки по факту. Досье `%TEMP%\opencode\c8_audit\api-core-<дата>\`:
tree-before/after, JUnit всех фаз, orig-копии, скрипты, SHA-печать последней.

Запрещено: менять байты перенесённых ранее эталонов (кроме временных мутаций
с byte-exact restore), facade/transport, `contract/`, parity кроме L87/L88,
PROGRESS, таблицу 44 механик, native-источники, другие tools/, внешнюю сеть,
реальные ключи, `substrate-selfcheck` runtime, `runtime_owner`/`server_state`.

Стоп-условия: мутация не краснеет на новом кейсе → стоп; гейт ok→fail или
SHA-restore mismatch → стоп; замыкание тянет незапланированную подсистему
(flask/сервер/api_backend) → честный deferred, не «перенести всё»; обнаружены
реальные ключи/сеть → немедленный стоп и доклад. Итоговый отчёт: что перенесено,
числа прогонов, отклонения (D-номера), что осталось.

