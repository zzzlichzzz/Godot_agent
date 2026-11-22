# assistant.chat — рабочая петля агента / CLI (K1)

**Статус:** этап `6`, K1c read-only реализован и проверен, готов к независимому аудиту; seal/ZIP впереди. Прежние K1/K1b приняты только как partial_STOP.
**Обновлено:** `2026-11-20`. Самоприёмки нет.

## Цель и границы

Мандат: актуальные D70–D73 в `docs/porting/_start-prompt.agent-loop-K1.md`:
24335 B/164CRLF/bareLF0, SHA256
`e392746964246679f337612aeaf47bf63bd632686810c3100179b7c00cee9b78`.
Прежние11739/19529 B — byte-exact префиксы (mandate-readback.json).
Новый публичный `assistant.chat/chat`, `provides_tools=("chat",)`: история →
нативный agent_prompts → неизменённый ApiBackend → parser_base split/select →
существующий Agent.call для READ → нативный judge → DONE/явный бюджет итераций.
CLI: chat, repl, tools list, health. Это новый семантический код, не byte-port.

Не разрешены: запись/plan/confirm/rollback, editor/HTTP/MCP/browser-live,
NN/minilich-ML, doh.py. Реальная сеть/провайдер — только отдельная санкция;
пользователь разрешил автономное выполнение, но не снял STOP-пункты мандата.

## Прочитанная нативная спецификация

Корень: `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent`.
`python/main.py`: **304431 B**, SHA256
`c5b3edd1a1528d8662b49081880549b2f4cd1f9eed108030605fdaf2c6a17d0b`, LF4990/CRLF0.
Функции: _api_system_text:320, _reply:433, _reply_once:527,
_usage_checklist:589, _reply_with_self_heal:2199, init_session:2574, chat:2624.
Системный промпт неизменен внутри хода, обновляется между ходами; API получает
его отдельным системным сообщением, не второй копией в user prompt.
ApiBackend.send/_reply_from_raw сохраняют полную пару user/raw assistant;
parser_base может убрать DONE и собрать несколько agent_action в synthetic plan.
Поэтому DONE нельзя определять только по уже очищенному text, а plan нельзя
превращать в разрешение исполнения write-машины.
openai_compat split_sse_lines:394 / parse_sse_line:410 / extract_delta:431
читаются как неизменяемые SSE-примитивы; transport [DONE] не равен ответному ===DONE===.

## §0: пины и исходное дерево

Досье (внешнее, не предыдущий sealed J1):
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/agent-loop-K1-preflight-20261115/`.
Полные bytes/SHA256/LF/CRLF: `section-zero.json`; исходное дерево:
`repository-before.json`; сравнение с J1: `J1-to-K1-tree-identity.json`.

- API12 byte-exact с native; judge16 =436437 B byte-exact; parser198211 B exact;
  corrected-native librarian-квартет совпал с принятыми, не с устаревшим native.
- runtime_bindings4518 B/84LF/50 aliases; старые35 — точный префикс.
- WORKLOG на начало1006300 B/fe574510…; issued-head1003828 B — точный
  префикс caf3944224450e5e…; принятие J1 независимо записано в WORKLOG.
- J1→K1:6061→6062 файлов; добавлен только мандат, изменены до этой работы
  WORKLOG и два selfcheck-report. WORKLOG описывает собственные прогоны аудитора;
  эти предварительно существовавшие отчёты сохранены, не перезаписываются.
- CLI TODO-пины113/130/105 B подтверждены. provider_base/models НЕ тронуты:
  фактически127/141 UTF-8 B;98/95 в мандате — число Unicode-символов.
- `python/modules/assistant/chat/` уже существует как TODO-scaffold;
  утверждение «папки нет» устарело. MODULE и run_turn отсутствуют.
- F2≤72 устарело: принятый pin84LF; два старых теста требуют ровно84.
- Три отвергнутые попытки §0 (исходная tree/report-оценка, порядок quartet,
  bytes/characters интерфейсов) сохранены; успешный recount exit0 отдельно.

## Старые тесты и будущие кейсы

`docs/parity.md`: assistant.chat skeleton; строка присутствует, статус не повышен.
`docs/tests-map.md`: test_megaprompt_once.py, указано2, assistant.chat/replaced
(contract+live). Прочитанный native-файл фактически содержит5 check: нет чата,
не primed, старый пустой hash, тот же hash, изменённый hash. Эти наблюдения
записаны как будущие семантические кейсы, а не как уже выполненные K1-тесты.
Группы — первичный prompt и отсутствие повторного browser-priming;
API/K1 использует системный prompt в каждом запросе. Старый код тестов не копируется.
api_backend-тесты назначены assistant.model_choice/replaced; их нельзя молча
закрыть реализацией chat. HTTP cleanup/isolation/routes остаются вне MVP.

## Предварительные препятствия

1. `tests/py/browser/test_browser_runtime_binding.py:84–121` разрешает
   единственный точный lazy-import только в LibrarianRead.answer / JudgeRead.judge.
   K1 gateway требует нового места активации; D65/D66/ADR0020 разрешили два
   конкретных существующих места, не произвольное расширение allow-list.
2. `tools/snapshot_diff.py:309–348`: internal clients только resource/project_text;
   `tools/corpus_replay.py:37–49`: специальный маршрут только context.ask (D52).
   Manifest chat сам по себе не вызывает run_turn. Публичный фиктивный chat-tool,
   подмена чужого client или динамический import ради обхода запрещены.
3. Agent/registry не публикуют lookup callable internal entrypoint.
   Нужен явный runtime composition для CLI; channels не импортирует modules/substrate.
   Это проектирование шва, не утверждение об отсутствии READ-инструментов.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-15 | обязательное чтение / §0 | защищённые пины точны, документальные расхождения зафиксированы |
| 2026-11-15 | лист до production-кода | создан; код, старые тесты/пины и checker не менялись |
| 2026-11-15 | внешний pytest importlib harness | первая collection-попытка exit2: evidence не в sys.path; сохранена, исправлен только внешний harness |
| 2026-11-15 | genuine frozen guard + internal replay ×2 | точные одинаковые6 IDs;2 ожидаемых red/4 control pass, без error/skip; новый import запрещён; client chat отсутствует |
| 2026-11-15 | genuine selfcheck assistant.chat ×2 | blocked/exit2: нет MODULE, unit и corpus; реальные layers/limits/contract/security ok |
| 2026-11-15 | независимые CLI/гейты-контроли ×2 | security/layers/limits/contract exit0; existing read через tools/probe exit0; project bytes/metadata/dirs/links exact |

## Проверки и честность

Настоящий `tools/selfcheck.py assistant.chat`, неизменённые predicates; перенесён
только REPORTS во внешний каталог (предварительно существующие отчёты сохранены):

```text
module  not_implemented  нет MODULE (R-05)
layers  ok              файлов642, нарушений нет
limits  ok              файлов642, предупреждений2 (исторические, не менялись)
contract ok             артефактов30, расхождений нет
security ok             нарушений нет
unit    not_implemented тестов модуля нет
corpus  not_implemented нет корпуса fixtures/corpus/assistant/chat
verdict blocked         exit2 ×2
```

Проверки: `diagnostics/preflight-boundaries-corrected-{1,2}/output.log`, JUnit IDs;
`diagnostics/selfcheck-assistant-chat-{1,2}/reports/assistant.chat.json`;
`preflight-and-selfcheck-results.json`, `independent-controls.json`.
Genuine frozen-test отказал ровно на новом ChatGateway.send import-site
(`tests/py/browser/test_browser_runtime_binding.py:111`). Genuine snapshot_diff
отказал `KeyError: 'chat'` (`tools/snapshot_diff.py:327`). Это два воспроизведённых
интеграционных red, **не** успешный replay новой петли и **не** её red-before-code suite.
Существующие READ read/search/context/ask/judge зарегистрированы: STOP §4(д)
«нет нужных READ» не заявляется. Нет физического изменения проверенных READ-проектов.

## STOP и следующий допустимый шаг

STOP §4(а): нормальная lazy-активация нового gateway требует расширения принятого
frozen scoped-guard; настоящий selfcheck/corpus требует нового internal-chat
маршрута через защищённые snapshot_diff/corpus_replay. Старые D52/D65/D66 разрешали
только конкретные ask/judge места. Молчаливое изменение guards/checkers, dynamic
import для обхода, фиктивный публичный chat-tool или чужой corpus-client не сделаны.
Проектирование нового runtime composition само по себе возможно; оно не снимает
эти два препятствия. Нет необходимости менять байты ApiBackend или security/limits.

В репозитории изменены **только** этот новый лист, одна assistant.chat-строка
PROGRESS и новый append-only хвост WORKLOG. Все прочие исходные файлы, metadata,
dirs/links, принятые пины, CLI/interface TODO и два аудиторских selfcheck-report exact.
parity остаётся skeleton; deviation/new и README-команды не заявляются без кода.
Внешнее досье содержит отвергнутые попытки, исходные bytes и новые docs-readback;
seal записывается последним, ZIP проверяется побайтно вне sealed-каталога.
Упаковочная проверка — не независимая приёмка, последняя остаётся не заявленной.

Не достигнуты: production run_turn/gateway/CLI, модульные offline-fixtures и
red-before-code петли, мутации≥3, full7921+2/frozen230/API253/project288×2,
CLI SSE one-shot/repl, физическая secret/state_dir проверка новой петли.
Два синтетических внешних SSE декодированы pinned-примитивами ×2;
это control, не provider recording и не завершённый K1 corpus.
Live-провайдер не вызван: отдельной санкции нет.

**Следующее действие:** независимая реверификация частичного STOP-досье;
для возобновления нужен отдельный узкий мандат на exact scoped chat-import guard
и genuine internal-chat replay route, затем offline-loop red-before-code.


## K1b — принятие STOP и проверка продолжения (2026-11-20)

Пользователь сообщил: D70–D71 выданы, прежний partial_STOP принят как
STOP-рекорд. Это независимая приёмка preflight-протокола, **не приёмка K1**.
Документ аудитора найден: CONTINUE_K1b в мандате, строки120–142;
WORKLOG10566–10595. Текущий мандат19529 B/63676f4d224031aa…/142CRLF;
его прежний11739-B префикс exact. Старое sealed-досье не изменено.

D71 теперь разрешает публичный chat/provides_tools=("chat",): предыдущая
необходимость internal-chat replay больше не является блокером. Новый инструмент
может использовать обычный snapshot_diff → Agent.call без правки replay/checker.
Новые alias не разрешены; BINDINGS4518 B/84LF/50 неизменны.

Повторный source readback выявил **два конфликта требований**, которые нельзя
молча превратить в разрешение на правку:

1. D70.3 (строка130) предписывает добавить chat_gateway в default_ports;
   D70.5 (строка132) одновременно запрещает менять байты bootstrap8451 B.
   Две минимальные вставки (method-local import + port) проверены AST только
   в памяти: исходный и предложенный SHA/bytes различаются. Предложение НЕ
   записано в репозиторий. Это арифметика source delta, не тест нового adapter.
   Требуется явно исключить **только эти вставки** из full-byte freeze;
   остальные принятые bootstrap-байты и все прочие пины остаются защищёнными.
2. D71.2 (строка136) требует result STRING плюс turns_used/actions_executed/
   judge_summary в envelope. Настоящий Agent.call/kernel.result.ok при строковом
   handler-result возвращает только {ok: true, result: STRING}; diagnostic-hook
   нет. Проверен настоящий wrapper с явно synthetic dispatcher-input, без
   регистрации фиктивного chat и без provider. Доступен безопасный вариант
   **result OBJECT {text: STRING, turns_used, actions_executed, judge_summary}**
   по образцу существующего judge.json, но текущая санкция явно говорит STRING.
   Этот вариант НЕ выбран самостоятельно, kernel/Agent не изменены. Требуется
   одно точное решение формы результата; предложение object позволяет не
   расширять общую инфраструктуру.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/agent-loop-K1b-review-20261120/.
Команды: diagnostics/baseline-start/result.json,
diagnostics/boundary-observation-1/result.json,
diagnostics/selfcheck-chat-{1,2}/result.json. Настоящий tools/selfcheck.py
assistant.chat повторно: **blocked / exit2 ×2**; module/unit/corpus
not_implemented; layers/limits/contract/security ok ×2, прежние2warnings.
Менялся только checker.REPORTS runtime во внешнем wrapper, не predicates/код.

K1→K1b до наших правок: то же6063file дерево; изменены только мандат и
аудиторский append-only WORKLOG; остальные bytes/metadata/dirs/links exact.
В этой сессии source/tests/checkers не менялись, сеть/provider не вызывались,
реальный Agent wrapper не активировал runtime_bindings, project inventory exact.
Не заявляются loop red-before-code, adapter/CLI, мутации/full-regression или
secret/state_dir proof новой петли. Прежние selfcheck blocked-прогоны не
переименованы в green. Работы сверх санкции и самостоятельной приёмки нет.

**Следующее действие:** уточнить D70.3/D70.5 (две разрешённые bootstrap-вставки)
и D71.2 (точный object-result либо отдельно санкционированный envelope-hook),
затем продолжить D70 red-before-code; новой общей replay-санкции не требуется.
# K1c — актуальная цель (D70–D73, 2026-11-20)

Публичный read-only `assistant.chat/chat`, не прежняя internal-only заготовка.
Исторические K1/K1b STOP ниже остаются честными partial_STOP, не завершением.
D72 разрешает ровно две вставки в `default_ports`: локальный импорт ChatGateway
и элемент `chat_gateway`. Before8451 B/180LF, SHA256
`2c0643473d82cf54355a34704afe784548506c3438db1d2b77221cbc5c096d41`.
JudgeRead/D65 и остальные байты сохраняются. Измеренный after8592 B/182LF/0CRLF:
`d6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8`.
D73: закрытый обязательный result-object из `text`, `turns_used`,
`actions_executed`, `judge_summary`; финальный domain STRING оборачивает только app.
Kernel/protocol/checkers/native references/runtime bindings не меняются.

Gateway: единственная ленивная активация внутри `ChatGateway.send`, абсолютные
package imports, прежние50 aliases. Shared librarian lock; profile-only API keys,
chat_store/api_history/cache; проверка realpath до IO, восстановление override,
ENV_CONFIG_DIR, cache и parser sample hook в finally, в том числе BaseException.
System = native PRIMING_TEMPLATE, фиксирован на send, обновлён между turns.
API сохраняет user/raw-assistant парами. Native parser split/select; raw DONE
сохранён отдельно. Native judge получает STRING через существующий dispatcher.

Домен допускает только явные READ соответствия к действующим публичным tools,
проверенные по registry.effects; plan (включая synthetic multi-action plan),
write/exec/recursive chat не исполняются. Отказ записи — вежливый финальный текст.
max_turns1..8, budget_chars1..80000, вход/ответ/feedback ограничены. Ошибка API
не исполняет action. CLI normal печатает text, diagnostics через --json.
Offline SSE будет подменять только транспорт в внешнем изолированном процессе;
обычный snapshot_diff вызывает реальный Agent.call, без checker/registry bypass.

Baseline6063 files, accepted K1b seal/ZIP exact, only pre-existing auditor
WORKLOG/mandate changed. Dossier внешне:
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/agent-loop-K1c-20261120/`.
Этап4 K1c: gateway12 genuine RED-final→GREEN, одинаковые ID; оба D72 RED до
bootstrap. After8592B/182LF/0CRLF, SHA256
`d6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8`.
Удаление ровно двух вставок даёт все прежние8451 bytes; D65 сохранён.
Frozen browser runtime guard genuine RED с ChatGateway.send до разрешённого
одно-сайтового расширения (старые два сайта/assertions не ослаблены).
Loop32 fresh RED до реализации; новых корпусных GREEN пока нет.
Следующее действие: синтетический корпус/спецификация, затем loop и same-ID GREEN.
# K1c public loop checkpoint (2026-11-20)

Loop count29, не32 (предыдущая запись — счётная опечатка). Первые RED29;
первый GREEN21pass/8fail сохранён: тесты ошибочно использовали Agent.registry,
вложенный error.kind и заменяли все default READ ports одним портом.
Исправлены только новые тесты; revised29 RED на временно возвращённых наших
четырёх production baseline файлах, затем exact restore receipt и29 same-ID GREEN.
App использует реальный raw ctx.call_tool, не публичный envelope; domain STRING.
Frozen D70 guard same-ID GREEN после единственного разрешённого сайта.
Synthetic corpus10/10×2 через неизменённый snapshot_diff→Agent.call; observations
byte-equal, normalization []. Первый8/10 сохранён: offline harness выбирал прежний
history ID после failed send (native правильно не хранит неполную пару). Исправлен
только external scenario selector; production/goldens не переписаны.
Этап5: следующий шаг CLI RED→code, D73 count-only8files, mutations/full gates.
# K1c CLI/guards checkpoint (2026-11-20)

CLI8 same-ID RED→GREEN, normal text/json diagnostics/repl/tools list/health.
D73 eight-file suite453: RED7failure446pass → GREEN453; ровно7file token deltas,
selector не менялся (ни RED, ни relevant count change не было). Сохранены counts,
имена/order/membership и surrounding bytes; receipt D73-token-only-after.json.
Новый chat.json строго ToolSpec-generated; missing-artifact RED, затем check0.
Security2 finally failures +1 masking pass RED →3 same-ID GREEN: nested finally
восстанавливает globals даже если redacted log сам бросает BaseException.
Initial layers genuine fail: runtime import в нашем module test. Восемь public
тестов без изменения тел перемещены в integration/test_chat.py, не import bypass;
после relocation29 RED на own baseline→exact restore→29same-ID GREEN. Checker
не менялся. Layers/limits/contract/security exit0; следующий шаг4mutants и paired
gates/full frozen/API/native regressions, настоящие selfcheck/probes.

## K1c полный regression checkpoint (2026-11-20)

Все4 submitted-byte mutants killed,0survivors, exact SHA/LF/CRLF restores,
те же ID GREEN; production mutation pins совпадают с нынешними bytes.
Frozen230/API253/project288 ×2 GREEN, membership/order без изменений.
Full2/3:7975collected/7973passed + ровно2 исторических WinError1314 skips ×2;
старые7923 ID сохранены в прежнем порядке,52 новых, setup/call/teardown ровно
по одному на каждый ID, физические bytes/metadata/dirs/links репозитория неизменны.
Full1 неуспешен и сохранён:7 failures и observer INTERNALERROR; raw child exit
не был записан из-за TypeError receipt parser на testcase без classname.
Исправлены только наши fixture generations/package-child caches и observer PATH,
без изменения native parse stats, routing tests/goldens или checker.
D72 дополнительный frozen файл явно назван:
`tests/py/integration/test_resource_ops.py` — genuine RED, затем только вставка
`"chat_gateway"` между `"librarian"`/`"journal"`, same-ID GREEN, остальные bytes exact.
Отдельный own-isolation + unchanged routing прогон:256passed/exit0.
Следующее действие: final paired gates/selfcheck и actual CLI/probes, затем dossier.

## K1c final submitted checks (2026-11-20)

Actual `selfcheck assistant.chat --json` ×2 exit0:
module/layers/limits/contract/security/unit/corpus all **ok**;
644Python files,31contract artifacts/0diff,29unit passed,10corpus/0diff.
Limits: только два прежних warnings split_py11elements/editing8400lines.
Отдельные layers/limits/contract--check/security_audit ×2 exit0.
7 actual public entrypoints exit0: READ probe, write-request polite refusal probe,
CLI chat/text+json, REPL, tools list/json, health. tools/health не активируют native
bindings; physical audit показывает0 forbidden project/addon write attempts.
Corpus и selfcheck native request observations raw-byte equal ×2, normalization[].
Это synthetic offline SSE, **не** реальная модель/сеть или editor-live.

Classification **new**, MODULE_ready=true, independent_acceptance=false.
Result — закрытый required object; domain final STRING, app alone wraps,
native judge STRING неизменён, все4submitted mutants pins/restores действуют.
Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/agent-loop-K1c-20261120/.
Следующее действие: seal LAST, sibling ZIP/full membership+CRC+byte verification,
передать на независимое принятие K1; после принятия продолжить docs/PROGRESS.md.
