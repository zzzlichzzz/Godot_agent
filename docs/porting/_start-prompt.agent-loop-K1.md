# Мандат K1 — рабочая петля агента (MVP CLI): модуль assistant.chat + каналы CLI

Класс: жёсткий. Приёмка: независимый аудит. Частичный вердикт легален (честная фиксация фазы).
Цель: получить РАБОЧУЮ петлю агента — CLI-диалог с реальной моделью, в котором модель
отвечает текстом с блоком ```agent_action, действия диспетчеризируются существующим
Agent.call, ответы оцениваются портированным judge, петля завершается по DONE.
Это срез «сборка работающего варианта»: инструменты и API-слой уже байт-точны —
K1 их связывает. Байт-точных переносов в K1 НЕТ (кроме уже запиненных): петля — новый код,
семантическая спецификация которого — нативный main.py.

## §0. Предусловия (обязательный пересчёт до первой правки)

- Репозиторий: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
- WORKLOG-голова на момент выдачи: **1 003 828 B, sha256-префикс `caf3944224450e5e`**, CRLF-хвост.
  J1 принят независимо (WORKLOG-запись «Независимая приёмка J1 (финал)»).
- Нативное дерево (источник спецификаций): `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`.
- Уже байт-точны и НЕ трогаются (пины из приёмок; переверить в §0):
  - API-слой `python/substrate/llm/api/` — 12 файлов: providers 73 572 `a269ea59ce55d390…`,
    api_keys 80 764 `340f73fbf36b80bd…`, providers_catalog 60 359 `8860d4544a93ceb8…`,
    openai_compat 39 682 `6b1022aeb3303a49…` (CRLF-файл), anthropic_compat 10 859 `c7b8f32c22828d60…` (CRLF),
    model_cache 12 322 `58895c14b6507ee4…`, agent_prompts 45 177 `633ad387d4ab5b83…` (CRLF),
    api_history 23 452, chat_store 11 045, md_to_bbcode 10 185, rate_limit 10 841,
    `backends/api_backend.py` 91 906 `93d22fb580b66e88…` (mixed LF44/CRLF1264);
  - алиасы BINDINGS уже есть (runtime_bindings.py L23–L36: api_keys/openai_compat/providers/
    model_cache/catalog/anthropic_compat/agent_prompts/rate_limit/md_to_bbcode/chat_store/api_history/api_backend);
  - parser_base 198 211 `7b2ce9f14695416e…`, librarian-квартет (340b5dd2/2f7694a9/e13d5680/bf35dcea),
    judge-замыкание 16 файлов 436 437 B, F2-пин ≤72 строк runtime_bindings, budget 84 LF;
  - `tools/probe.py` (R-18), selfcheck context.ask ok/exit0, assistant.judge ok/exit0.
- Заглушки K1-скоупа (замерить и запинить в §0): `python/channels/cli/{__init__,main,commands}.py`
  (113/130/105 B, TODO), `python/modules/assistant/chat/` — папки пока нет (проверить отсутствие).
- `substrate/llm/provider_base.py` (98 B TODO) и `substrate/llm/models.py` (95 B TODO) —
  заглушки интерфейса; НЕ удалять, НЕ заменять (см. §6).
- Нативная спецификация петли (читать, не переносить байт-в-байт):
  `python/main.py` 304 431 B — `_api_system_text` L320, `_reply` L433, `_reply_once` L527,
  `_usage_checklist` L589, `init_session` L2574, `chat` L2624, `_reply_with_self_heal` L2199;
  `python/backends/api_backend.py` — отделение блока ```agent_action (regex L52–53),
  стриминг `_stream_with_shrink`, ротация ключей `should_rotate_key`;
  `python/api/openai_compat.py` — SSE-формат `split_sse_lines`/`parse_sse_line`/`extract_delta`.
  Пины main.py (bytes/sha/LF/CRLF) замерить в §0 и записать в досье.

## §1. Архитектура K1 (новый код, класс «deviates/new» с фиксацией в deviations)

- Новый модуль `python/modules/assistant/chat/`: module.py (ModuleSpec id `assistant.chat`,
  provides_tools=() — внутренняя механика, не публичный инструмент; capabilities=("assistant.chat",)),
  app.py (вход `run_turn`), domain/ (чистая логика: сборка сообщений, парсинг ответа, решение
  «продолжить/DONE»), ports.py (Protocol: ModelGateway, ToolCaller, HistoryStore, Judge).
- Адаптер `python/substrate/assistant/chat_gateway.py` (по образцу judge_read.py 3 118 B):
  тонкая обёртка над api_backend.ApiBackend + api_keys; биндинги уже постоянные (register()
  в runtime_bindings); адаптер маршрутизирует хранилище ключей/истории в state_dir профиля
  (D53-паттерн: ENV_CONFIG_DIR override → state_dir; ключи и api-кэш НЕ в проекте
  пользователя; физическая проверка «ключ не записан в проект» обязательна).
- Канал `python/channels/cli/`: main.py — argparse-точка входа (`chat` one-shot, `repl`,
  `tools list`, `health`); commands.py — реализация; вывод — человекочитаемый для chat,
  JSON для служебных команд (R-15).
- Петля одной итерации (MVP): история → системный промпт (agent_prompts) → ApiBackend
  (stream при доступности, fallback complete) → parser_base.split_net_text_and_action /
  select_best_answer_variant → для каждого действия: Agent.call(tool, args) через registry
  (только READ-инструменты; write-действие → вежливый отказ без исполнения) → judge
  (substrate/assistant/answer_judge) → при отсутствии DONE и остатке бюджета — следующая
  итерация с результатами инструментов в контексте. Бюджет итераций — явный параметр.
- Запрещено в MVP: план/confirm/rollback-машина main.py, write-действия, editor-канал,
  HTTP-сервер, MCP, browser-live, minilich-ML, doh.py (остаётся deferred, D36).

## §2. Порядок работ (G)

1. §0 пересчёт + пины (включая main.py и заглушки cli) → tree-identity.
2. Red-before-code: тесты offline-петли (записанные SSE-фикстуры) красные до кода;
   фикстуры — синтетические записи SSE-потоков OpenAI-совместимого формата
   (openai_compat.split_sse_lines/parse_sse_line/extract_delta байт-точны — гоняются как есть).
3. domain/ → app/ → адаптер → channels/cli; selfcheck assistant.chat (corpus_folders
   найдёт `fixtures/corpus/assistant/chat` естественно; manifest module=assistant.chat).
4. Мутации ≥3 (например: смена DONE-детектора, бюджета итераций, направления write-отказа)
   с exact-восстановлением и same-ID зелёными.
5. Гейты ×2 + security ×2 (B-1 не трогать; SEC-02/03/04 — новые файлы не должны
   добавлять сетевые импорты ВНЕ substrate/llm; channels/cli не делает сети сам —
   только через gateway в substrate/llm).
6. Полный регресс ×2 (ожидание: текущие 7 921+2 skip растут на новые тесты; exact IDs),
   frozen230/API253/project288 ×2.
7. Документы: parity.md (assistant.chat → new), deviations (класс нового кода),
   docs/porting/agent-loop.md (новый лист), README/PROGRESS/WORKLOG.
8. Seal последним; ZIP побайтно; реверификация аудитором.

## §3. Секреты и сеть (критично)

- api_keys.config_dir() поддерживает ENV_CONFIG_DIR override (натив L161) — использовать:
  в адаптере выставлять/пробрасывать так, чтобы хранилище ключей оказалась в state_dir
  профиля, а не в APPDATA-наследии и не в проекте. Физический тест: после прогона
  дерево проекта побайтно неизменно, секретные строки не появляются ни в репо, ни в отчётах
  (маскирование api_keys.mask/redact — байт-точное, использовать).
- Live-проба с реальным провайдером — ТОЛЬКО по отдельной санкции пользователя (какие
  провайдеры/ключи); по умолчанию все тесты offline на записанных SSE-фикстурах.
- doh.py НЕ переносить и НЕ активировать (D36).

## §4. STOP-пункты

Любое из перечисленного — стоп с досье, а не молчаливое решение: (а) правка любого
запиненного байта (включая api-слой, parser_base, judge, runtime_bindings сверх нужды
новых алиасов для assistant-модуля — только token-only дописывание в конец по
прецеденту D48/D50 с red-before-code); (б) необходимость сети в tests/py вне записанных
фикстур; (в) необходимость править security_audit/check_limits (лимит строк для новых
файлов — обычный 400, кроме class3400-исключений); (г) поведение ApiBackend, требующее
изменений байтов; (д) отсутствие в registry нужных READ-инструментов для петли.

## §5. Честность

Хронология до работ; никакого self-acceptance; rejected-попытки сохраняются в досье;
WinError1314-symlink gap и 2 limits-warnings не трогать; если реальный ключ недоступен —
честный blocked-статус live-пробы, MVP валидируется offline-фикстурами (это легальный
результат, а не провал).

## §6. Чек-лист независимой приёмки

tree-identity → §0-пересчёт (пины api-слоя/квартета/judge/main.py/заглушек cli до правок)
→ offline-фикстуры red-before-code → selfcheck assistant.chat ok/exit0 ×2 → CLI-пробы
(one-shot с SSE-фикстурой; live-проба только с санкцией) → секреты: state_dir, no-project-write
(дерево побайтно до/после), маскирование в выводе → мутации ≥3 exact restore → полный
регресс ×2 + focused/frozen/api/project → гейты ×2 + security ×2 (B-1) → docs → досье/ZIP →
seal последним → реверификация аудитором.

# CONTINUE_K1b — решения аудитора по STOP этапа 1 (2026-11-16)

Префlight-досье `agent-loop-K1-preflight-20261115` принято как STOP-рекорд (verdict partial_STOP; §0 ok, tree-identity J1→K1 exact; security/layers controls exit0; selfcheck blocked/exit2 ×2; docs: agent-loop.md 12 533 `9c3741a7…`, PROGRESS:66 single-row, WORKLOG 1 011 387 `b4c70110…`; baseline-bytes сохранены). Оба блокера верифицированы аудитором механически:

- **Блокер 1 подтверждён**: `tests/py/engine_cache/test_engine_cache_binding.py:12` — `len(binding.BINDINGS)==50` с точными префикс-срезами — замораживает точное число алиасов; `test_no_production_bootstrap_wiring` (L67) запрещает активацию биндингов из bootstrap. Любой новый импорт-активатор = red этого guard-а.
- **Блокер 2 подтверждён**: `tools/selfcheck.py:136` — ModuleSpec без provides_tools И без contributes_to = FAIL; `check_corpus` (L292–309) идёт в `tools/snapshot_diff.py`, generic-ветка умеет только `agent.call(tool)` — внутренний модуль без публичного инструмента недостижим для честного corpus-реплея. Это ДЕФЕКТ ДИЗАЙНА МАНДАТА (§1 предписывал provides_tools=()) — исправляется санкцией D71, вина на аудиторе.

**D70 — gateway-адаптер и место активации (санкционировано).**
1. NEW `python/substrate/assistant/chat_gateway.py` — адаптер ModelGateway по образцу `judge_read.py` (D65/D68-паттерн): ленивая активация runtime-биндингов ВНУТРИ методов (function-local, прецедент D55), never at import; хранилище ключей/истории/кэша — только state_dir профиля (ENV_CONFIG_DIR, D53-паттерн); физический запрет записи в проект (physical-check + restore в finally); маскирование ключей только через байт-точные `api_keys.mask/redact`.
2. Импорты адаптера — ТОЛЬКО абсолютные package-пути (`python.substrate.llm.backends.api_backend`, `python.substrate.llm.api.*`, `python.substrate.llm.parsers.parser_base`) → НОЛЬ новых записей в BINDINGS; точный guard `==50` не трогается. Неустранимая необходимость нового алиаса — STOP (не молча).
3. `python/runtime/bootstrap.py default_ports`: добавка порта `"chat_gateway"` лениво (прецедент D55/D65, ADR-0020 семантика сохраняется); `tests/py/judge_j1/test_adapter.py:13` не ломается (проверяет только librarian); иной замороженный тест, падающий от нового порта, — красный список в досье + token-правка ТОЛЬКО по явному перечню в досье.
4. red-before-code: «import chat_gateway не активирует биндинги» (sys.modules-снапшот до/после) + «активация только в методах». Мутация ≥1: активация на import → killed.
5. Записи в deviations.md (D70) + лист docs/porting/agent-loop.md; байты frozen-файлов (BINDINGS 4 518/84LF, bootstrap 8 451, judge_read 3 118, librarian-квартет, checker'ы) не меняются.

**D71 — публичный инструмент `chat` вместо внутреннего модуля (санкционировано; правка дизайна мандата аудитором).**
1. ModuleSpec `assistant.chat`: `provides_tools=("chat",)` (было () — ошибка мандата §1); корпус-политика "corpus"; entrypoints call+setup; capabilities ("assistant.chat"); requires_ports ("chat_gateway",).
2. ToolSpec `chat`: effects "read", idempotent False (недетерминизм модели — честно), errors ("invalid_input","not_found","denied"), availability "*", cost "heavy", limits {"max_turns","budget_chars"}; args: {text (обязательное, ≥1 символ), max_turns (int 1..8), budget_chars (int >0)}; result STRING (финальный текст) + фиксированные diagnostics-поля envelope (turns_used, actions_executed[read-only], judge_summary) — зафиксировать в контракт-артефакте по прецеденту judge.json.
3. Семантика turn — по §1 мандата (история → agent_prompts → ApiBackend stream/complete → parser_base split/select → Agent.call ТОЛЬКО READ-инструменты → judge → до DONE или max_turns; write-действие = вежливый отказ с объяснением, НЕ ошибка протокола).
4. Corpus: `fixtures/corpus/assistant/chat/` — manifest (module assistant.chat, module_stage 0→1, reference_only false), catalog.json + offline-SSE-фикстуры (записанные потоки провайдер-формата, воспроизводимые без сети). Кейсы: прямой ответ без действий; read_file-действие с последующим ответом; неизвестное действие; write-действие → отказ; DONE-маркер; обрыв потока (SSE-error); ротация ключа (байт-точная should_rotate_key); бюджет-обрезка; judge-низкий балл → повтор. Observations = эталоны оффлайн-петли ×2 (byte-equal). snapshot_diff generic-ветка (agent.call("chat", args)) обязана работать БЕЗ правок snapshot_diff; недетерминизм в сравнении — нормализация ТОЛЬКО документированных полей по прецеденту D52 (отдельная мини-санкция в досье, не молча).
5. red-before-code: corpus-тесты красные до кода; selfcheck assistant.chat blocked→ok обязателен; unit-тесты domain (budget, max_turns, DONE-детекция, отказ write) + тесты адаптера (routing, маскирование, no-project-write).
6. CLI (`channels/cli/*` — NEW TODO-файлы, не frozen): main = argparse: `chat` (one-shot: build_agent → agent.call("chat", …)), `repl` (цикл, история в state_dir), `tools` (tools/list), `health` (registry status); R-15 JSON для tools/health, человекочитаемый вывод для chat/repl; коды выхода 0/1 по AppError-видам; CLI сам НЕ активирует биндинги (активация внутри адаптера).

Порядок продолжения: D70 (адаптер+порт+red) → D71 (инструмент+корпус, red-before-code) → CLI → мутации ≥3 суммарно → гейты ×2 + security ×2 (B-1 сохранён; сеть в tests только через offline-фикстуры, SEC-02 не ослаблять) → полный регресс ×2 exact IDs → docs → seal последним. Живая проба реального провайдера — по-прежнему только по отдельной санкции пользователя (offline-MVP легален). Всё сверх D70/D71 + мандат §6 — STOP.

# CONTINUE_K1c — решения аудитора по противоречиям K1b (2026-11-20)

Досье `agent-loop-K1b-review-20261120` принято как STOP-рекорд (partial_STOP; самопроверка blocked/exit2 ×2; probe chat unknown_tool/exit1 — корректное пред-регистрационное состояние; только docs-обновления; провайдеры не вызывались). Оба противоречия признаны ошибками моей санкции K1b:

**D72 — вставки в bootstrap.py санкционированы явно (замена противоречивого D70.3/D70.5).**
Формулировка K1b «байты bootstrap 8 451 не меняются» при одновременном предписании добавить порт — противоречие; правильная граница:
1. Санкционированы РОВНО две token-вставки в `python/runtime/bootstrap.py`: (а) method-scoped ленивый импорт адаптера chat_gateway ВНУТРИ default_ports (паттерн D65/ADR-0020: никаких импортов на уровне модуля bootstrap); (б) элемент словаря портов `"chat_gateway": <adapter>`. Ничего сверх этого.
2. Обе подстановки D65 (judge) сохраняются байт-в-байт вокруг вставок; дельта фиксируется пинами before 8 451 `2c064347…` → after (измерено, в досье и deviations D72).
3. red-before-code: тест «порт chat_gateway присутствует и callable» + тест ленивости «import bootstrap не импортирует chat_gateway до вызова default_ports» (sys.modules-снапшот) — оба красные до вставок.
4. Receipt-пины мутантов (включая D65-composition) в будущих досье ссылаются на НОВЫЕ байты after как restore-пин — обновление receipt-пина легально и обязано быть записано; frozen live-тесты, падающие от вставок, — явный список в досье + token-правка только по перечню (прецедент D62/D63-границ).
5. deviations D72 + строка в ADR-0020/0021; SEC-02/PROC_ALLOWED/listen-границы не трогаются.

**D73 — object-result утверждён (замена противоречивого D71.2).**
Формулировка K1b «строковый result + отдельные diagnostics в result-envelope модуля» не имеет production hook — Agent.call возвращает результат инструмента как есть. Простое решение (предпочтительное):
1. ToolSpec `chat` result = JSON-схема ОБЪЕКТА: {"text": string, "turns_used": integer, "actions_executed": array of string, "judge_summary": object, additionalProperties false, все поля required}. Envelope-hook в kernel/protocol НЕ добавляется — `python/kernel/*` и `python/protocol/*` не трогаются вовсе.
2. Внутренний run_turn/domain по-прежнему производит строку финального ответа; обёртка в объект — ровно на границе app.call. Инструмент judge остаётся STRING (нативный паритет).
3. CLI печатает result["text"] (человекочитаемый режим); diagnostics — в --json/verbose; snapshot_diff структурно сравнивает весь объект.
4. NEW контракт-артефакт `contract/capabilities/chat.json` (прецедент judge.json 1 737 B); module Tools-список/регистрация — по D71.
5. D69-пины (8 файлов: test_functions_contract, test_usages_contract, test_gd_lint, test_node, test_scene, test_tscn_lint, test_verify, test_selfcheck_unit_selector) — token-only правки ТОЛЬКО там, где `chat` входит в рекламируемые списки/счётчики (tools 29→30, счётчики unit-selector); порядок и члены сохраняются; red-before-code; deviations D73.

Порядок: D72 (вставки+red) → D73 (schema+контракт+пины) → корпус/CLI по D71 → мутации ≥3 → гейты ×2 + security ×2 → полный ×2 exact IDs → docs → seal последним. Live-провайдер — по-прежнему только отдельная санкция. Всё сверх D70–D73 + мандат §6 — STOP.
