# Runtime/editor-контекст + API routing — эталонный срез

Мандат: `_start-prompt.routing-runtime.md`, 2026-11-05, 10715 B,
SHA256 `d1d296e4b1595300477fb8fbca60074c0f7bb6277cf89e8856637b595e04f54e`.
Стратегия: **byte-exact verbatim**, последовательно A → B. Приёмка независимая.
Полные MODULE/HTTP-механики остаются skeleton; reference ≠ ported модуля.

## §0. Пересчёт до правок

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/routing-runtime-20261105/`.
`§0-recount.json`, `tree-before.json`, `baseline-bytes/`, `native-before.json`:
4348 файлов / 859 каталогов / reports44 / UID86 / pyc0. Четыре реальных
сентинела в __pycache__ — ref.gd, ref.gd, ref.gd.uid, ref.py (точные пути в JSON);
формулировка мандата «четыре ref.gd» неточна, сохраняется фактический инвентарь.
project.godot335 B / `958b3a92…`; WORKLOG763546 B / `7e694e8a…`, полный
byte-prefix обязателен, существующий mixed EOL не переписывается.
parity24262 B / `5d1cec37…` LF, заморожен. После API seal изменились только
auditor append api-core.md/WORKLOG/porting README и добавлен routing prompt.
Первый kickoff имел ошибку внешнего scope-пути README; исходная база сохранена,
исправлен только assertion, повтор подтвердил полную byte-equality.
Baseline gates: lint591/0, limits591/2 (split_py11, editing8400), contract28/0,
security0. Фактический вывод — `baseline-gates/`.

## §1. Решения до production (D38)

- A: `python/substrate/editor/references/{runtime_debug,editor_context}.py`.
  Это эталоны one-turn контекста, не примитивы/transport и не новая domain-копия.
  Пакетный __init__.py по образцу соседей. Исходники 12251/14161 B,
  SHA `ed7d6087c84f1634…` / `32613d2844967413…`, импорты неизменны.
- B: `python/substrate/llm/backends/api_backend.py`, 91906 B,
  SHA `93d22fb580b66e88…`, imports неизменны.
- Классовый лимит3400 только для двух новых reference-каталогов;
  default400/editor transport400/browser600/parser3400/API3400 и entry150/80
  не расширяются. Red class-пины до правки гейта обязательны.
- В runtime_bindings только три explicit alias; register/rollback алгоритм
  и24старых alias неизменны, production bootstrap/profile не подключаются.
- Корпус первичен: native synthetic capture ×2 → спецификация → red → copyfile.
  Это порядок R-07/R-16/R-22, даже если краткий маршрут §D перечисляет иначе.
- Внешняя сеть/реальные ключи/живой Chrome запрещены. Mock transport и external
  sandbox; clock/random/token генерация детерминирована. D37 только Authorization
  value в новом observer, имена/прочие наблюдения не маскируются.
- D36: реальный DNS/DoH deferred, missing doh не заменяется фиктивным модулем.

## §2. Замыкание и граница спецификации

`closure.json` содержит исходные imports/полные SHA/EOL и24existing alias.
A runtime_debug: только json/secrets/time; editor_context: imports0.
B: api_history/api_keys/anthropic_compat/catalog→providers_catalog/md_to_bbcode/
openai_compat/parser_base/providers/rate_limit/agent_prompts плюс A; stdlib re/time/XML.
Перед B проверяется реальный импорт через bindings, не заглушки compat/parser.
Flask/chat_routes, STATE/history_manager, answer_judge, librarian/minilich,
локальные backends, live DNS и MODULE/HTTP integration не входят в этот срез.
Нового ToolSpec/capability нет: спецификация reference — input/output/error/state
наблюдения native-корпуса, не фиктивный публичный инструмент.

## §3. Кейсы и инварианты A

Источники кейсов: native test_runtime_debug.py и test_editor_context.py;
прочитан test_runtime_debug_flow.py только для определения deferred HTTP scope.
tests-map L55/118/119/142/149 имеют судьбу; historical owners/fates не заменяются.
Runtime: strip/attach status, session readiness/ambiguity, action sections/selectors,
node/name bounds и отказ выражениям, request/public/runtime projection,
snapshot protocol/96KiB/depth/list/dict/text limits, section/property correspondence,
read-only report truncation. Editor: normalize malformed snapshots, selected-code
priority, unrelated current-script omission, bounded formatter, one-turn stripping.
Инварианты: нет IO/сети, input не меняется; ошибок native не чинить; result_token
не пересекает runtime_request; исходники равны native bytes/SHA/EOL.

## §4. Ход и текущий вердикт

2026-11-05: обязательные правила/архитектура/карта/прогресс/NOTES прочитаны;
свежая база и closure сняты; baseline gates зелёные. Production0, corpus0.
Последний selfcheck этого среза: ещё не запускался, не заявляется ok.
Приёмка/готовность к аудиту: **не заявляется**.

2026-11-05 A: native144 cases ×2 совпали, corpus/context/runtime_reference с
полными provenance/source/case SHA/EOL. Red169:156failed/13passed; class3 red,
binding4 red, остальные source/corpus. После минимального directory-class и
двух alias copyfile12251+14161 B точно native. Green169/169, gates594/0,
limits2старых/contract28/security0. B production ещё не начат.

2026-11-05 A завершён на reference-уровне: green169 ×2; actual selfcheck
context.runtime_snapshot exit2/blocked: MODULE/unit/module corpus отсутствуют.
Свежий report в a-selfcheck/, все44canonical восстановлены byte-exact.

## §5. B: corpus/spec/red до production

193 synthetic native cases ×2 совпали. Первый capture записал все карты, но shell
timeout120s не считается exit0; исходное сообщение сохранено. Повторный
replay b-native-exit-verified подтвердил193 ×2 против тех же SHA-карт с exit0.
Корпус fixtures/corpus/llm/routing/manifest.json: source SHA/EOL, per-card bytes/SHA,
provenance и фиксированные time1000/seed77, silence clock1000→1003.
Нативные tests/test_api_backend.py прочитаны только как источники кейсов.

Спецификация B: closed/open/bare/legacy XML action, parse_error, budgets catalog/
fallback/ceilings, retry-state pop-once и seeded schedules; send provider/model/key
refusals, chat-fixed model, key rotation vs outage, history-shrink floor/ceiling,
max3 continuations/overlap, empty/reasoning-only, progress и cancellation,
truncation/closed-action rescue, history atomic pair/persistence refusal,
ephemeral context. Compat SSE loops и owned reader threads настоящие; mock только
recorded _open/IO и boundary typed errors; silence queue/time детерминированы.
Реальный DNS не вызывался: TransportError DNS branch и proxy projection, DoH
deferred (D36). No network/config inside repository, closed readers/responses,
unchanged input; result/action/error/state/progress/stdout сравниваются целиком.
D37 меняет только наблюдаемое Authorization value.

B red212:204failed/8passed, source/corpus/binding до копирования B. Pre-copy gates
594/0, limits2старых, contract28/security0. Ожидания/производственные эталоны не
менялись. A green остаётся условием входа B, не MODULE-паритетом.

## §6. B green и submitted-byte mutations

B copyfile91906 B native SHA93d22fb5…, LF1308/CRLF1264 сохранены (mixed EOL).
Добавлен только третий alias: binding58строк/27aliases, алгоритм D33 неизменен.
Focused376×2 exit0; b-gates596/0, limits2прежних, contract28/security0.
Пять submitted-byte mutant: class3 red, alias1, observer Authorization2,
runtime strip_status1, API MAX_HISTORY_SHRINKS2. Каждый red именными новыми
поведенческими тестами; source-byte pin не был единственной причиной. Backup
copyfile → exact SHA/EOL restore → те же тесты green0, JUnit/log/orig/results
в досье. Ни один mutant не выжил, native/frozen файлы не редактировались.

## §7. Фактическая сдача reference-среза (не приёмка)

- Native A144×2 и B193×2 совпали; replay B после timeout имеет явный exit0.
- Focused376×2, frozen230×2, API-core253×2 exit0. Full6250×2:6248passed/
  2старых skips. Все5874старых IDs/outcomes сохранены; дельта ровно376 новых
  focused IDs. Ordered IDs/outcomes равны, каждый testcase выполнен once-only.
- verify_results.py подтвердил native inventory без изменений, 3 byte-exact
  reference, project.godot335B exact, reports44/UID86/pyc0/sentinels4 exact.
- Actual final selfchecks context.runtime_snapshot и assistant.routing: **blocked,
  exit2**; MODULE/unit/module-owned corpus отсутствуют. Layers596/limits2/contract28/
  security0 внутри обоих selfchecks. Fresh JSON/logs в final-selfchecks/;
  все44canonical восстановлены copyfile byte-exact. Это не selfcheck ok.
- Actual tools/probe.py runtime_snapshot/routing на внешнем synthetic project:
  unknown_tool, exit1; клиентская MODULE/MCP-интеграция не заявляется.
- Canonical parity целиком прежний SHA5d1cec37…, обе skeleton ячейки и MODULE
  этапы0 неизменны. Reference завершён в границе мандата, HTTP/live/editor ownership,
  replay/auth/concurrency/TTL, полноценная provider/server orchestration deferred.
  Anthropic SSE проверен на реальном compat loop, registry boundary в send-cases
  замокан; это не отдельная live-проверка agentrouter/claude. Flask/STATE/GD/DoH/
  librarian/minilich/local/backend/browser live не затрагивались, сеть не открывалась.
- Новые тесты/корпус зарегистрированы только append в tests-map; historical168
  owners/fates не переприсваивались. WORKLOG/porting README append с prefix assert.
- Наблюдавшиеся setup-события сохранены: kickoff README path assertion,
  capture timeout, atomic patch rejected missing PROGRESS context (изменений0).
  Ни expectation, ни frozen security/production semantics не ослаблялись.

**Вердикт:** A+B reference-срез готов к независимому аудиту, **не принят**;
полные context.runtime_snapshot/assistant.routing остаются skeleton/blocked.
Финальные gate logs и SHA256-final.json — в досье; SHA-печать пишется последней.

**Следующее действие:** независимый аудит запечатанных bytes/JUnit; MODULE/HTTP
и live-интеграция — только отдельный мандат после принятия reference-среза.

### Seal preflight repair (перед окончательной печатью)

Первый seal exit1 до tree-after/SHA записи: patch добавления D38 заменил только
CRLF последней исторической строки467 на LF (байт46311). Diff подтвердил ровно
потерянный CR; repair_prefix.py восстановил original46313byte prefix, D38 tail
полностью unchanged. Submitted до repair сохранён; никаких source/test/corpus
байтов не менялось. Последующие gates и seal повторены, дефект не скрыт.


### Приёмка независимого аудита (2026-11-05, сессия 78)

Срез ПРИНЯТ: печать repository+evidence 13712/13712 bad=0; репо = tree-after
4700/4700; граница 7 changed + 352 added, removed=0; пины 3/3 byte-exact vs
native (runtime_debug ed7d6087…, editor_context 32613d28…, api_backend 93d22fb5…).
Прогоны: native A144/B193×2, focused 376×2, api-core 253×2, frozen 230×2,
full 6250×2 = 6248 pass/2 legacy skip; ordered/once-only; 5874 старых ID сохранены.
Мутации 5/5 red (3/1/2/1/2) → byte-exact restore → green. Гейты после prefix-repair:
lint 596/0, limits ok/2, contract 28/0, security ok/0. Инцидент потери CR в
deviations при D38-append обнаружен seal-preflight и устранён до печати — принят.
Selfcheck runtime_snapshot/routing blocked exit 2: skeleton сохранён, parity.md
не тронут. Принятое отклонение: PROGRESS.md обновлён честными фазами портёра
(упущение границы промпта, documentation-only). Вне этого среза: MODULE/HTTP-
интеграция и live — отдельные мандаты.
