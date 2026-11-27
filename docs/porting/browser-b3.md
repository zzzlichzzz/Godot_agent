# B-3 — sites / live_input / ai_studio_net / qwen_net / browser_backend

**Статус:** этап 6, готов к независимой приёмке B-3 reference slice; не ported/accepted.
**Обновлено:** 2026-11-04.
Мандат: `docs/porting/_start-prompt.browser_b3.md`. Таблица 44 механик и
`docs/PROGRESS.md` заморожены; internal substrate проверяется по D26, без
фиктивного MODULE/ToolSpec/capability и без `selfcheck browser`.

## Цель

Перенести пять native-файлов byte-exact, доказать их offline-поведение и
SEC-19/R-21 без запуска сайта, ввода или новой маскировки. Live с записанным
сайтом требует отдельного разрешения; offline-корпус не подменяет live.
По дополнительной просьбе пользователя сначала проверить слабые решения B-2.

## Старый код

Источники `D:/vajno/Godot/тест-плагина-ии/addons/Godot_agent/godot_agent/python/`
и `D:/vajno/Godot/random-game/addons/godot_agent/python/` совпали по всем 8
browser/backend-файлам. B-1/B-2 production exact против обоих источников.

| Native-файл | B / строки | SHA256 |
|---|---|---|
| `browser/sites.py` | 9906 / 214 | `06da927025fd18253b9e4a820b276ae8e2db834314938e2a2bd8b4993285dd41` |
| `browser/live_input.py` | 4437 / 83 | `cd2c6ccfc12c371b9cbce0905addeb27d60264decaabbce2b2310b23b9f13e80` |
| `browser/ai_studio_net.py` | 9735 / 224 | `3d9a3fb4b62a1071c7e769b91e70947036f05f0e67b74e4642379ef585db710c` |
| `browser/qwen_net.py` | 12199 / 238 | `57d1ab2bfaea6226c478ffe3b05ba46badd49c67427ed6e3575791f13457b751` |
| `backends/browser_backend.py` | 3380 / 57 | `21e5e911d139b4d136ef619a44ea401a757b27b83befe5907b37cfccee0a48b1` |

Backend — 57, не 58 строк по raw splitlines; размер/SHA совпали. Размещение по
мандату совместимо с `parity.md`/`NOTES.md`/`mapping.md`: browser + backends
внутри `substrate/llm/browser`. В preflight sites был заглушкой, остальные
4 файла/backends отсутствовали. Теперь все5пути созданы byte-exact, без
добавления постороннего production-кода или runtime-связывания.

## Старые тесты

Инвентарь по `docs/tests-map.md`, строки не меняются:

| Файл | Судьба | Область кейсов / оставшаяся граница |
|---|---|---|
| `test_v105_spoof_per_site.py` | deferred Q-08 | все site flags и unknown=False; вызовы browser_manager не переносить в новый runtime |
| `test_v88_0_aistudio.py` | deferred Q-08 | protobuf JSON, thought/answer/finish, UTF-8/partial/gzip; тесты не запускать и не копировать |
| `test_v88_6_qwen_net.py` | deferred Q-08 | SSE/partial/thought/answer/finish |
| `test_qwen_dual_response.py` | deferred Q-08 | ветви response_id/index, разделение ответов |
| `test_v88_8_net_first.py`, `test_v88_12_net_confirm.py` | deferred Q-08 | network counters/state; parser-level поведение вне 5 файлов |
| `test_net_monitor_lifecycle.py` | deferred Q-08 | accepted B-2 lifecycle regression; production frozen |
| `test_rate_limit_sleep.py` | replaced, host-flask | только кейс последовательного pop 429→None (строки151–155); rate_limit/Flask вне среза |
| `test_v88_11_live_input.py` | deferred Q-08, live | mirror callbacks/busy/seq offline; реальный набор требует parsers и live |
| `test_browser_target_binding.py`, `test_aistudio_send_acceptance.py`, `test_arena_parser.py` | deferred Q-08 | парсеры/target binding/send acceptance не реализованы этими 5 файлами; нельзя объявить закрытыми |

Судьба файлов остаётся deferred: соответствующие кейсы эталонов представлены
в корпусе ниже, parser/server/live-остатки не объявляются закрытыми.

## Корпус

Создан `fixtures/corpus/browser/b3/manifest.json`:32 native observations на
инертном CDP/callback-портах, отдельные JSON inputs с bytes/SHA и provenance.
Это новые synthetic minimal frames, не запись настоящего сайта и не старый
test code. Актуальные наблюдения: corrected mirror capture + AI inventory;
первый native-observations.json оставлен как исторический ошибочный capture.
AiStudio JSON step1/7/full, gzip, tail, stream/buffered/body fallback; Qwen
SSE/Unicode/thought replacement, dual switch/no-id/service/tail/codec absent;
site flags/host quirks/missing parser; mirror seq/cache/busy/callback errors;
backend dict/string/empty/missing parser; самостоятельные public pop calls.
В этих файлах нет DOM-селекторов или CDP Input-команд: live_input вызывает
`parser.mirror_input`, browser_backend передаёт один prompt парсеру. По D31
не выдумываем отсутствующие selectors/Input/message-history механики.

## Спецификация

- Пять native-байтов неизменны; B-1/B-2/stealth/gates frozen.
- Нет public capabilities/entrypoint/bootstrap; проверка по D26 батареями.
- Flags aistudio/deepseek/qwen=True, kimi/arena/arena_battle=False; unknown=False.
- Старые абсолютные импорты `from net_monitor import BaseNetMonitor` и
  `from server_state import wait_driver` не превращать в скрытый sys.path/sys.modules
  runtime-хак. В новом дереве старый server_state отсутствует.
- Браузер/сайты/профили не запускаются и не читаются; данные корпуса не код/JS.

## Решения по ходу

Пользователь после воспроизведения STOP разрешил: отдельный узкий ремонт
SEC-19/SEC-20 (лист `browser-sec19.md`); B-3 только эталонный срез с инертными
зависимостями, без runtime-связывания и без закрытия всей ветки; две точные
документационные правки README/parity. Native byte-exact не отменён.

Fresh external baseline до первой repository-правки:3954files/850dirs/44reports/
86UID/4fixture sentinels/pyc0. `WORKLOG.md`715783B/SHA256
`2666a6785005749672a6c74891cc6765be5e35e12bea860a960297aab8a4ac83`;
prompt prefix713456B/SHAddc65356…29b65 exact, auditor append2327B без bare LF.
Project335B/SHA958b3a92…b3b29; facadeSHA6abe81d…b0b98/100LF,
security_auditSHAd4679c…2467 exact. Старые baselines/dossiers не переснимались.
B-2 seal покрывает ровно3root files; его work/ не запечатан, это предел
доказательства, а не проверка всей рабочей папки. Ничего там не менялось.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/b3-delivery-20261104/`.
В preflight README66 указывал отсутствующий `docs/porting/browser_b3.md`,
а parity168 сохранял «не accepted» после приёмки B-2. Разрешённые точные правки
выполнены: README token → `_start-prompt.browser_b3.md`, B2status → принят;
историческая приёмка не снимается и остальные записи не переписываются.

## Ход работы

| Дата | Шаг | Результат |
|---|---|---|
| 2026-11-04 | 1. baseline + лист | pins подтверждены; scoped review перед корпусом/кодом |
| 2026-11-04 | 2. STOP → D30/D31 | guard repair и reference-only отдельно разрешены |
| 2026-11-04 | 3. corpus/red | native29, свой harness red→green, B3red42/37fail |
| 2026-11-04 | 4. verbatim | пять raw-copy/SHA exact; green42 |
| 2026-11-04 | 5. mutations + inventory | site/Qwen/CRLFguard red→exact restore→green; corpus32 |
| 2026-11-04 | 6. battery/boundary/handoff | focused45×2/corpus32×2/full5478; ready for independent audit |

## Проверки

`preflight.py`: status ok,3954files,44reports/86UID/pyc0,readonly delta пустая.
`selfcheck browser` не запускается по явному D26-мандату;44report bytes frozen.
`review_probes.py`: confirmed_stop; три multiline-подмены не ловятся, три imports
не находят net_monitor/net_monitor/server_state. Public pop production/native:
[None,429,None,None,503,None,None]; отдельная deletion mutation поймана.
Новая regression:109/109 ×2, security237 passed/2 genuine Windows skips,
все четыре гейта exit0; native/production unchanged, pyc0/reports44.

## Следующее действие

Независимому аудитору выполнить `python -B C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/b3-delivery-20261104/verify_delivery.py`, затем в своей новой папке повторить offline corpus/guard mutation; статус приёмки меняет только аудитор.

## Продолжение 2026-11-04 — восстановленный checkpoint

Resume-tree снят отдельно, исходный tree-before не перезаписан. Изменены только
согласованные docs/invariants/guard и добавлены свои листы/tests/corpus; удалений
нет, pyc0, reports44. D30 уже прошёл red28/19fail → green28 и sandbox mutation;
после этого EOL guard возвращён в343CRLF/0bareLF, SHA c59e4faf…8167f4.
На этом checkpoint требовались новые прогоны именно финальных байтов;
ниже записаны их фактические результаты и byte-exact sandbox restore.

Обнаружен дефект собственного corpus harness: `apply(text, seq)` вместо native
`apply(seq, text)`. Три mirror ожидания не доказывают заявленные seq/text кейсы;
их исходная запись сохранена в досье. Исправление только своего harness/корпуса,
native и пять production эталонов пока неизменны. Прочие26 observations frozen.

Независимый order-pin:1executed/1expected failure → исправление на keyword
`seq=…, text=…` →1passed. Native29 пересняты: только3mirror observations отличаются;
input bytes всех29 и foreign26 exact. Patch manifest сверяется с механически
записанным manifest-order-corrected.json до red/production. Первое применение
patch перепутало позиции двух results; assertion выявил это до production,
исправлено по native evidence, не сменой поведения native.

Инвентарь AST, не запуск старых тестов: aistudio9 функций (7monitor/2parser),
qwen7 (3monitor/4parser+fs), dual4, live_input13 (8mirror/5parser+server),
net_first11, net_confirm5, lifecycle15, target_binding4, send_acceptance8,
arena31 — не29 в промпте; один sites-case относится к5эталонам, остальные30
остаются parser-deferred. v105 — inline checks, не pytest functions: первые7
site checks относятся кregistry, остальные browser_manager/parser. Старые
fates не меняются; synthetic корпус не объявляет все эти файлы закрытыми.

B-3 red до production:42executed,37expected failures/5passed/0errors/0skips
(missing files/stub/dependency names); финальный D30 guard green28/28.

transfer_b3.py: five files byte-exact against both roots/current external native
copies; raw EOL unchanged (sites193CRLF+21LF/backend57CRLF/other LF). B-3green42/42,
0errors/0skips. Никакие runtime aliases/bootstrap/capabilities не добавлены.

Sequential own mutations finished: site kimi False→True gives audit SEC-20red1
and corpus+bytepin2reds; Qwen answer append→overwrite gives8behavior reds+bytepin.
Both production files restored byte-exact, focused42/42 after each restore.
Final343CRLF guard sandbox: remove only D30call→28executed/19reds/9passed;
raw restore to c59e4faf…8167f4 and green28/28; production guard unchanged.

Первый полный final_battery:42/42×2, корпус29/29×2 diff0, regression109×2,
security267executed=265passed+2Windows skips×2, четыре гейта exit0/audit×2ok.
Full non-live actual collected=executed5475,5473passed/2skips/0errors/failures;
repository delta empty. Не приписываем исторические5225 этому новому прогону.

Завершение inventory выявило необходимость трёх независимых AI cases:
ложный finish, cleanup обрезанного wire и gzip wire no-replay. Сняты только с
native, до записи fixtures; production не меняется. Корпус32, прежние29observations
exact. Старые7monitor cases теперь имеют соответствующие offline projections;
2parser cases остаются deferred. Boundary-пин README также выявил LF у одной
правленной строки66; восстановлен её исходный CRLF, вся правка README теперь
побайтно равна единственной разрешённой замене path token (82CRLF/0LF).

## Финальный вердикт D26/D31

`expanded_battery.py` exit0; два focused прогона45/45, два native/reference
прогона32/32 diff0. B1+B2regression109/109×2; full security267executed=
265passed+2genuine WinError1314skips×2. Full non-live collected=executed5478,
5476passed/2genuine skips/0failures/errors. Оба readonly battery delta пустые.
Гейты: lint573/0, limits573/2прежних warnings, contract28/0; audit×2ok/0.

Boundary:3996files/852dirs, added42/removed0; только согласованный набор правок.
Guard343CRLF SHAc59e4faf…8167f4 без D30helper+call byte-exact прежнему;
native8/two roots/B1/B2/stealth/PROGRESS/table44/tests-map/44reports/UID86/
four sentinels/project335B/pyc0 и все чужие repository bytes неизменны.
WORKLOG дополняется только CRLF append к715783B, prefix713456B также exact.
Досье запечатывается SHA256-final.json последним файлом; pytest tmp folders
явно исключены, остальные свои артефакты и delivery-bytes охвачены печатью.

Вердикт портера: **готов к независимой приёмке B-3 reference slice и отдельного
D30 SEC19/20 repair**. Не accepted/whole-browser ported. D26 не требует fake
selfcheck/probe для internal substrate; canonical reports не регенерировались.

Public one-shot pop case независим от деструктивного snapshot и закрывает
указанный B2test debt; его deletion sandbox probe красный, production B2 frozen.

## Блокеры

| Риск | Кто решает |
|---|---|
| Multiline flag escape | D30repair выполнен; ожидается независимая приёмка guard |
| Старые top-level net_monitor/server_state imports отсутствуют | D31reference-only; рабочая интеграция требует нового мандата |
| Parsers не входят в5файлов | вне D31; whole-browser closure не заявляется |
| Recorded-site production live | не выполнен, нужен отдельный мандат и разрешённый сайт |


## Приёмка B-3 эталонного среза аудитом (2026-11-04, сессия 78)

Пять эталонов byte-exact vs native; корпус 32×2 без расхождений; фокус 45×2;
полный non-live 5476 pass/2 skip; гейты lint 573/0, limits ok/2 (прежние), contract 28/0,
audit ×2 ok/0. Свои мутации: kimi False→True в production sites.py — byte-pin и corpus
красные 2, production-страж SEC-20 red 1, restore ok/0; удаление D30-call из
check_browser_stealth — ровно 19/28 sec19-красных, restore ok/0. D30 принят; D31 принята
с ограничением (эталон ≠ рабочий runtime; parsers/server_state/recorded-site live —
отдельный мандат).
