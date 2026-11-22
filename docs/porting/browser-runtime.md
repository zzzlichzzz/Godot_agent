# Browser runtime — рабочий лист (2026-11-04)

Статус: STOP на первом A live; A не закреплена, B не начата. Parity/PROGRESS не
меняются по явной границе мандата. Это substrate-срез, не публичный ToolSpec.

## §0 — свежая граница

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-runtime-20261104/`.
Полная baseline: 3998 файлов, 852 каталога, tree-before.json и baseline-bytes/.
project.godot: 335 B, SHA256 958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29.
WORKLOG: 728913 B, SHA256 2b70ef1e52d27013fdb8d74c767ec941504515917de2c858109fc632e3d270c4.
Гигиена: reports 44, uid 86, pyc 0; четыре sentinel-файла в трёх fixture
__pycache__ каталогах сохранены (включая ref.gd.uid). Старые досье не меняются.

Расхождение §A.3: browser.md фактически LF (27976 B, 332 LF, 0 CRLF), SHA256
5781b146f203b874e99403f47cb7df907e5d6aa6d7db422b2f7960b5862c52c5.
Его исторический префикс остаётся byte-exact; только новая добавка — CRLF.
Этот новый лист — CRLF. WORKLOG — только append CRLF с prefix-assert.

## A — спецификация до усиления харнесса

Копируется проверенный b1-live-20261103/live_battery.py, не правится оригинал.
Только новый внешний харнесс: четыре OS foreground/window выборки через 0.5 с
после attach; прежние WinEvent и 5ms-sampling остаются. Не меняет focus или
window-state. Никаких retry запуска, новых Chrome-флагов или маскировок.

Критерий зафиксирован до live: суммарное собственное foreground <1.5 с,
никаких новых foreground-интервалов после стартового окна 1.5 с от Popen;
последние две проверочные выборки — чужой foreground и собственные видимые
Chrome-окна iconic. Конечное неразрешённое foreground — fail. Чистый старт и
краткая восстановившаяся гонка различаются в отчёте, не смешиваются.
Серия меньше трёх выборок/интервал меньше 0.45 с — fail. Unit-кейсы харнесса
закрепляют clean, краткий старт, ровно 1.5 с, поздний возврат, устойчивое
foreground, несвёрнутое окно, недостаточную серию и WinEvent-only наблюдение.

Сохраняются busy-port отказ, probe до spawn, launch/driver SHA-пины, ownership,
owned-target polling, честный webdriver=false/native getters, spoof call=0,
cleanup reader/socket/process/profile/listing. Две полные батареи подряд;
каждая содержит четыре запуска Chrome × две file:// проверки (8 наблюдений),
а не восемь запусков. Отдельно записываются 4/4 запуска и 8/8 file-наблюдений.

## B — запланировано, ещё не исполнено

Порядок: inventory девяти native SHA и полного import closure → семь verbatim
парсеров и классовое правило лимита → явная связка/шов → synthetic-тесты →
recorded-site live 127.0.0.1 → мутации и гейты. Server_state и answer_judge
не переносятся. До inventory решения о месте связки, шве и лимите не приняты.
Строки tests-map 174–202 остаются deferred до полностью доказанного покрытия.

## Следующее действие

Получить отдельное решение после STOP: разбор воспроизводимого no-focus Chrome
без ослабления критерия и/или разрешение продолжить независимую часть B.

## A — фактический STOP (2026-11-04)

Классификатор: 8/8 ×2. Первоначальная внешняя pytest-collection упала из-за
importlib-пути foreground; исправлен только путь внешнего теста, ошибка и
оба последующих результата сохранены. Chrome не перезапускался до green.

a-run-1 завершился code 1 в fixture-live-1. Собственный Chrome PID16780,
driver PID10416. Четыре OS-выборки через ~0.501 с: первые три iconic, четвёртая
foreground PID16780/iconic=false. WinEvent+sampling: 2.3900946 с собственного
foreground; late_foreground=true, last_two_checks_recovered=false. Это не
разрешённая стартовая гонка <1.5 с. Два CDP windowState=normal дополнительно
краснят прежний minimized-пин. Причина foreground не локализована; успешное
чтение не является доказательством исправности no-focus или ошибкой фасада.

busy-port refusal 1/1; wire collect/run 35/35; собственные file:// reads 2/2,
webdriver=false, visibility/getters честные, native setup/spoof calls 0.
Owned targets закрыты с сохранением initial; reader/websocket освобождены,
оба process handle завершены, только собственный disposable profile удалён,
listing exact. Реальный Chrome: один запуск, no-focus 0/1. Полная батарея
не завершена; a-run-2 и sandbox-мутация не запускались. 8/8 + 8/8 не достигнуты.

Вердикт A: не закреплена, воспроизведён STOP no-focus/minimized при запуске
Chrome. Вердикт B: не начата, не готова к независимой приёмке. Inventory,
перенос, связка, шов, corpus, recorded-site и B-мутации отсутствуют; строки
tests-map не изменены. Это не отменяет ранее принятую базу B-1/B-2/B-3.

## Read-only проверки после STOP (D26 / R-18)

Вместо неприменимого selfcheck browser — фактическая substrate-батарея D26;
никаких fake module/probe и записей в канонические reports/selfcheck.
Focused существующих B-1/SEC-20/SEC-03/B-2: 182/182 ×2 (в том числе SEC-03
72/72 и B-2 17/17). Full non-live: 5480 collected/executed, 5478 passed,
2 прежних symlink skip (WinError 1314); новых repository-тестов нет.
lint_arch 573/0, check_limits 573/2 прежних warning, contract 28/0;
security_audit ×2 ok/0. Те же четыре гейта были зелёными в preflight.
Проверки не меняли дерево. Production/reference/contract/parity/PROGRESS,
44 отчёта, 86 uid, 0 pyc и четыре sentinel-файла остаются byte-exact.
Доказательства: a-run-1/*, stop-checks.json, full-nonlive-counts.json,
boundary-final.json и SHA256-final.json во внешнем досье.


## A — контролируемый повтор: подготовка (2026-11-04)

Решение пользователя в WORKLOG 7726–7740 заменяет прежнее ожидание решения.
A пока не закреплена; B.0–B.3 и остальные работы B не начинаются до закрытия A.
Только две последовательные полные батареи a-controlled-1 → a-controlled-2;
8 реальных запусков Chrome, цель 8/8 + 8/8 файловых наблюдений. Существующая
аудиторская r4-live 4/4 — третья контрольная серия, не новый запуск портера.
Никаких повторов до green, новых флагов, свёртывания или spoof; нарушение → STOP.

Новое досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-a-controlled-20261104/.
Task-baseline: 3999 файлов/852 каталога, полные task-baseline-bytes/.
WORKLOG-префикс 737119 B / e873be4f63f3f951efe473926b7c715c21f2b379a918c40442b043d081922361.
Историческое STOP-досье проверено по печати: 6128/6128 файлов, без правок.
Харнесс 31768 B / 255120a305ab7af204ef26e45dc75963128275766bd19e32c6b9f44322407700
и классификатор 1521 B / 80a0bbe9b23601118c7c0df0e0a37c72de30c9bf8d86e2bb61e313e42a425527
скопированы byte-exact и совпадают с r4-live. Chrome 156.0.8078.80,
Chrome/driver/facade/project и всё production/reference-дерево остаются pinned.

PROTOCOL.md записан до кода внешнего caller. GetLastInputInfo — только метка
последнего ввода и monotonic-время, без клавиш/текстов/снимков. Parent guard
покрывает обе серии; свежий Python-worker каждой серии сверяет ту же метку.
Изменение метки/API-error запрещает следующие subprocess; начатая работа
проходит прежний owned cleanup. Аргументы/STARTUPINFO/критерий/харнесс не меняются.
Это контроль обязательной среды, не диагностический фазовый срез варианта 2.
Оператор отдельно подтверждает отсутствие ввода и параллельных browser-тестов.

Свежий preflight D26/R-18: focused 182/182 ×2, classifier 8/8 ×2;
финальные offline caller/guard-тесты 22/22 ×2 (первая версия guard 16/16 сохранена).
lint_arch 573/0; limits 573/2 прежних warning; contract 28/0;
security_audit ×2 ok/0. Реальный GetLastInputInfo доступен. Все проверки read-only;
44 canonical reports/86 uid/0 pyc/4 fixture-sentinel остаются byte-exact.
Ни одного нового Chrome-запуска. Live-baseline снимается после этой CRLF-добавки;
никаких repository-правок между батареями. Prefix-assert исключает нормализацию EOL.

### Следующее действие (актуальное)

Получить готовность оператора не трогать рабочий стол и не запускать параллельные
browser-тесты до сообщения о завершении; затем ровно две серии A подряд.
При STOP — остановить A и сдавать факты для отдельного диагностического среза;
при успехе — передать A на независимую приёмку. B остаётся не начатой.


## Результат контролируемого повтора A — 2026-11-04 (актуальная точка)

Этот результат продолжает явное решение WORKLOG:7726–7740 и заменяет только
старое «ждать решения после STOP» как следующее действие. Исторический STOP,
его досье и конфликтующие наблюдения не исправляются и не обесцениваются.

После подтверждения оператора «Готов, начинайте» выполнены ровно две полные
последовательные серии `a-controlled-1` → `a-controlled-2`. Третьей серии у
портёра, замены красной серии и повторов до зелёного нет. Существующая серия
аудитора `r4-live/r4-a-1` (4/4 запуска, 8/8 чтений) — третий контроль, не повтор.
Chrome 156.0.8078.80, driver, inherited harness/classifier, флаги, критерии и
disposable-профили неизменны; все live-пины проверены до/после каждой серии.
Production, reference/native sources, contract, parity, PROGRESS, tests-map,
канонические reports и tools остались byte-exact. B.0–B.3 и все остальные B
не начинались: нет inventory, переноса, alias, шва, corpus, live или мутаций B.

### Live и валидация окружения

| Серия | Реальные Chrome | Own-file observations | Wire | Own foreground |
|---|---|---|---|---|
| a-controlled-1 | 4/4 | 8/8 | 35/35 ×2 | 0.0 с во всех четырёх |
| a-controlled-2 | 4/4 | 8/8 | 35/35 ×2 | 0.0 с во всех четырёх |

Всего ровно восемь новых реальных запусков: по три production и одному после
предписанного восстановления sandbox на серию. Ожидаемая red-мутация — до
Popen, ноль запусков; это не замена неудачного live. В каждой серии:
busy-port real-socket refusal 1/1; mutation red/exact restore/green 1/1;
double fixture 2/2, mismatches 0; снимки обеих серий и r4 совпадают.
Все восемь `own_process_never_foreground=true`: четыре OS-выборки через ~0.5 с,
последние две recovered/iconic; оба CDP windowState=minimized; webdriver=false,
native setup/spoof=0, запрещённых focus/window/script команд нет.
Собственные процессы завершены, reader/websocket и targets освобождены,
исходные targets сохранены, nonce/inode-профили удалены, listing exact 8/8.

Внешний caller проверял только session-local `GetLastInputInfo`: 1007 выборок
родителя непрерывно вокруг обеих серий, 463/462 выборки свежих workers, одна
неизменная метка ввода, API errors 0, environment_valid=true. Метка не менялась;
это наблюдение вместе с подтверждением оператора, не универсальное доказательство
невозможности интерференции. Ни клавиши, ни тексты ввода, ни снимки не собирались;
ввод, переключение окон и принудительное свёртывание не выполнялись.
Guard проверял будущий Popen и не блокировал cleanup; его отказ/остановка второй
серии проверены офлайн. Harness/classifier не изменены. Диагностический фазовый
срез не запускался: повтор зелёный, причина старого STOP остаётся нелокализованной.

### Read-only проверки после live — маршрут D26/R-18

```text
controlled_repeat: exit_code=0, both_completed=true, environment_valid=true, B_started=false
focused: 182 passed x2; classifier: 8 passed x2; external caller: 22 passed x2
full non-live: 5480 collected/executed, 5478 passed, 2 legacy symlink skips
lint_arch: 573 files, 0 violations; check_limits: 573 files, 2 existing warnings
gen_contract --check: 28 artifacts, 0 divergences; security_audit x2: ok, 0 violations
post: all exit 0; repository unchanged; no live Chrome launched
```

Предварительные focused/classifier и гейты также ×2 зелёные; итоговый внешний
caller 22/22 ×2 до и после live (guard 17 кейсов + orchestration 5). Два skip —
прежние Windows symlink/WinError1314; новых skips нет. Два warning — прежние
split_py11 и editing8400 (R-06/D18). Pytest cache отключён, importlib, basetemp и
JUnit наружу; Python 3.14.6 `-B -X utf8`. Неприменимый `selfcheck browser` и
fake probe/module не запускались; D26 даёт настоящий stdout-вердикт батареи,
без записи в 44 canonical reports. Это substrate, не ported/public ToolSpec.

### Граница, досье и раздельные вердикты

В live и post-checks дерево 3999 файлов / 852 каталога неизменно. Доставка —
только CRLF-добавки к WORKLOG, browser.md и этому листу; исходные byte-prefixes
сохранены. 44 reports, 86 UID, 0 pyc и четыре fixture-sentinel в трёх
`__pycache__` (включая ref.gd.uid) byte-exact; project.godot byte-exact.
Исторический seal browser-runtime-20261104 проверен вновь: 6128/6128 exact,
SHA256-final.json 2f98493f885c515b479e609b3591b2d16aba39d778e9236c2872bbf665d1255f.

Новое досье:
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-a-controlled-20261104/`.
`A-results.json` содержит матрицу восьми запусков и guard-метаданные; рядом raw
live, environment, logs/XML, full baseline bytes, pin/tree и prefix-доказательства.
`boundary-final.json` и `HANDOFF.md` фиксируют доставку; `SHA256-final.json`
создаётся последним, контрольная сумма выдаётся при передаче.

**A:** controlled repeat passed, 8/8 + 8/8; готово к повторной независимой
приёмке, но acceptance_claimed=false. Это не доказательство невозможности гонки
Chrome и не основание чинить фасад; старые противоречивые результаты остаются.
**B:** не начата / не предъявляется к приёмке. Финальное закрытие A — за
независимым аудитором; до этого B и дополнительные porter-live не запускать.

**Следующее действие:** передать sealed досье A независимому аудитору для
решения о закрытии A с учётом уже существующего r4-контроля; B не начинать.
2026-11-04 · Аудит (сессия 78): часть A принята независимой приёмкой по
результатам контролируемого повтора. Печать досье browser-a-controlled-20261104
проверена аудиторски: 6489/6489 файлов, 0 расхождений; tree-diff — ровно 3
документа (WORKLOG, browser.md, browser-runtime.md), префиксы byte-exact,
добавки CRLF-чистые; production и замороженные эталоны не изменены (facade
6abe81d2…, browser_manager 4afd245f…, cdp_ws 3b5298dd…, net_monitor 54167afb…,
sites 06da9270…, live_input cd2c6ccf…, ai_studio_net 3d9a3fb4…, qwen_net
57d1ab2b…, browser_backend 21e5e911…, security_audit c59e4faf…, project.godot
958b3a92…); репо совпадает с tree-after-task 3999/3999.
Контролируемый повтор: 8/8 реальных запусков Chrome, own foreground 0,0 с во
всех запусках, own_process_never_foreground=true, CDP windowState=minimized во
всех выборках, файловые чтения 8/8+8/8, owned cleanup точный, повторов и третьей
серии портёра нет; input-guard: тик GetLastInputInfo неизменен (65188484) на
всём интервале, юнит 17/17; классификатор 8×2; focused 182×2; full non-live
5478 pass/2 legacy skip; гейты lint 573/0, limits ok/2, contract 28/0, security
×2 ok/0. Ранее — независимая аудиторская серия r4-live: 4/4 чистых запуска.
Итог: часть A принята; честная граница — успех не доказывает невозможность
стартовой гонки Chrome во всех окружениях; критерий усиленного харнесса
(<1,5 с, устойчивые серии) подтверждён в двух независимых сериях. Часть B не
начата; следующий шаг — B по регламенту промпта.

## B — свежий kickoff после независимого закрытия A (2026-11-04)

A принята аудитором; A-батареи не повторяются. B начата, не принята.
Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-b-runtime-20261104/.
Следующее действие B: снять native-derived synthetic корпус, затем независимые
red-тесты связки/шва/лимита и parser-кейсы; лишь затем переносить production.
PROGRESS/parity/44 reports frozen по явному substrate-мандату, стадия B ведётся здесь.

### §0 B — фактические пины до первой правки

3999 файлов / 852 каталога; reports44 / uid86 / pyc0; четыре fixture-сентинела
в трёх __pycache__ каталогах byte-exact. tree-before.json + baseline-bytes/ —
полная fresh проекция, native-before.json — read-only проекция источника.
project.godot находится ../../project.godot:335B, SHA256
958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29.
WORKLOG744413B, SHA256
6acb67e2ad3ad92a1eab5abdeb9a606ef76c0963e278a4b417178b3801abdd50.
Лист runtime21457B/958cd50414b0b8aedc3bdff246435eca0a88db7382ed5d6a5151c15a059fb48f;
browser32511B/5c990cf941314e965cead2ed6537510ac9225412e3607b9e4a28af86880e8fce.
Все полные pins/EOL в baseline-summary.json. Исторические префиксы документов
не нормализуются; каждая новая добавка CRLF с prefix-assert.
Первый external baseline-summary завершился KeyError из-за поиска project.godot
в аддоне; полные inventories/backup уже были сняты. Исправлен только путь,
проекции не перезаписаны; Chrome/production не затрагивались.
Принятая A печать70445274dd3ecd3ef55b667bee87f4f534787f0e48bf4771593c85bfa8c82e76
сохранена; старый A verifier не используется как новая baseline.

### B.0 — фактическое замыкание и честные deferred

Все девять размеров/SHA совпали с B.0; полный AST inventory включает lazy imports.
parser_base3352 строки; arena1247; ai739; qwen664; kimi485; deepseek336; sanitize52.
Шесть рабочих компонентов замыкаются на stdlib, selenium и browser-эталоны,
но дополнительно parser_base имеет optional json_repair (lazy except),
browser/net_monitor имеет optional brotli. Отсутствие optional codec не скрывается.
AiStudio импортирует kimi_parser, parser_base lazy импортирует browser_manager
и sites — эти зависимости обязаны быть в явной топологической таблице.

Native arena_parser:19 делает БЕЗУСЛОВНЫЙ from answer_judge import ...;
671/837/850/1182 lazy импортируют server_state.STATE и серверные помощники.
Поэтому ожидаемое «импорт Arena инертен» не соответствует источнику.
Семь parser-файлов допустимо перенести byte-exact, но arena_parser НЕ включается
в таблицу рабочих алиасов; её честный ModuleNotFoundError(answer_judge) проверяется
отдельно, не считается runtime-success. Judge/STATE-ветви deferred. Никаких
fake answer_judge, fake STATE, перехватов импортов или подмены результата judge.
Для полной B-приёмки эта несовместимость требует отдельного решения; текущий
мандат разрешает частичный вердикт, а не самовольное расширение переноса.
answer_judge не переносится: gd_api_check/gd_lint/minilich/project_tools/tscn_lint/
symbol_refactor/high_level_actions/runtime_debug/runtime_checks и lazy
scene_actions/project_settings_actions/resource_actions/transaction_actions.
server_state не переносится: history_manager/chat_store/project_tools/runtime_debug/
agent_prompts, их транзитивная серверная/Flask/редакторская подсистема deferred.
Native сбор не исполняет старые тесты, не запускает _bootstrap и не пишет native.

### Спецификация B.2 ДО кода: явная связка

python/substrate/llm/runtime_bindings.py, не-verbatim, <=60 строк.
Явный import runtime_bindings вызывает register(); package __init__, профили,
каналы и bootstrap НЕ импортируют связку. Никаких sys.path/meta_path/PathHook.
Явная топологическая таблица: cdp_ws, net_monitor, sites, browser_manager,
ai_studio_net, qwen_net, text_sanitize, parser_base, kimi_parser, ai_parser,
qwen_parser, deepseek_parser; server_state указывает на runtime_owner, НЕ native.
Каждый sys.modules[legacy] is canonical substrate module. Повторная register()
идемпотентна; чужой alias — RuntimeError, не перезапись; отсутствующий эталон —
явный ImportError; aliases, созданные неуспешной регистрацией, снимаются.
Канонические модули, загруженные до ошибки, могут остаться в import-кэше;
это не транзакция Python-import и не скрытое исправление байтов эталонов.
arena/answer_judge/server STATE не регистрируются.

### Спецификация B.2 ДО кода: wait_driver ownership seam

python/substrate/llm/runtime_owner.py — минимальный server_state alias только
для browser_backend.wait_driver; серверные STATE/история/Flask отсутствуют.
set_browser_booter(fn) регистрирует trusted zero-arg callable без выполнения.
При первом wait_driver ensure_browser_booting запускает его в daemon thread
ровно один раз под Lock; повторов/новых Chrome flags/встроенного launch нет.
Callable обязан вернуть настоящий ReadOnlyBrowser: _owned true, _process жив,
_driver не None. bind_owner публикует только такой owner, не произвольный driver.
Чужой/закрытый owner не публикуется; ошибка booter сохраняется в holder.
wait_driver(timeout=90.0): native wall-clock deadline, poll holder каждые0.25с,
driver имеет приоритет над driver_error; timeout<=0 всегда native timeout даже
если driver готов. Ошибка: «Браузер агента не запустился: %s»; deadline:
«Браузер агента ещё запускается — подождите пару секунд и повторите.»
Готовый driver возвращается по identity, только пока владелец жив/owned.
release_owner(owner) снимает исключительно того же владельца, не закрывает
чужой Chrome; caller обязан закрывать facade. После release/закрытия stale
driver не возвращается; новый boot за процесс не разрешается.
Не переносится native server API; шов явный и тестируется отдельно от launch.

### B.1 — классовый предел эталонов ДО правки стража

D32: только python/substrate/llm/parsers/ получает FILE_MAX3400 (parser_base3352).
browser600 и остальные400/entry-limits/area limits прежние. Red boundary-пины:
3352 и3400 под parsers допустимы после правила;3401 красен;601 под browser
красен;401 вне обоих каталогов красен. Прежние два warning обязаны сохраниться.
Семь файлов копируются байтами, смешанный native EOL не нормализуется.

### B.3 — корпус/инварианты до production

fixtures/corpus/browser/runtime/manifest.json: только новые synthetic JSON
inputs + bytes/SHA/provenance и фактическая native observation; существующие
B-1/B-2/B-3 corpus bytes frozen. B-3 кадры переиспользуются как pinned данные,
не как код тестов; фиксированные harness-dispatch функции не eval/exec данных.
Покрытие: AI protobuf/step/thought/answer/finish/UTF8/partial/gzip/tail;
Qwen SSE/Unicode/thought/dual; Kimi Connect events/tool/main/DOM fallback;
DeepSeek DOM extraction/confirm_sent; sanitize; incomplete refs/DONE;
parse_action_json/refs/schema; structural best/stable tie; DOM silence/deadline/
anti-stale/cancel; fresh-response readiness отдельно от sent-request counter.
Ошибочные parser samples только во внешнем tmp через GODOT_AGENT_CORPUS_DIR;
Kimi debug-writing finalizer не вызывается на tool-only fixtures. Это данные
test-runtime, не публичные effectful инструменты и не production-регистрация.
Новые tests runtime_* не копируют native tests. tests-map174–202 пока deferred:
часть кейсов != закрытие целого legacy-файла; соответствие записывается в листе.

### B.4/B.5 — ещё не исполнены

Recorded-site live только127.0.0.1, disposable sibling-profile, frozen facade;
не повторяет A. Оракул отдаёт pinned B-3 bytes и не подменяет native endpoint
фильтры: нужные URL suffix воспроизводятся на127.0.0.1. Native parser extraction
через actual Network events; Selenium/mirror по native против fixture DOM,
без clipboard пользователя/OS input/новых spoof/forced-minimize. Расхождение — STOP.
Мутации >=2 new binding/seam/oracle и>=1 parser reference; каждый restore exact.
Focused x2/full non-live/4 gates/security x2, tree/prefix/sentinels proof наружу.
Обычный selfcheck browser не владеет substrate-срезом и пишет canonical report;
только external substrate selfcheck с raw выводом, не 44 reports.
При прерывании следующий шаг одной конкретной строкой здесь, без принятия B.


### B.1–B.3 checkpoint (2026-11-04, не приёмка)

102 native-derived synthetic cases сняты двойным прогоном (204/204); старые
tests не исполнялись. Перед production —139 red/1green из140 (17 setup errors
на отсутствующей связке), исходный log сохранён. Пять limit-пинов исправлены
на фактический zero-arg guard API ДО правки production; чистый red2/green3.
Семь parser-файлов byte-exact, explicit bindings44 строки, runtime_owner86 строк.
Новый focused140/140; lint583/0; limits583/0 + ровно прежние2warning;
contract28/0; security0. Это offline parity, не B acceptance и не site-live.
Deferred Arena import/STATE/judge сохранён без fake judge, tests-map неизменен.

Спецификация B.4 oracle: pinned AI/Qwen B-3 bodies отдаёт ephemeral HTTP server
только127.0.0.1; новый oracle.html — trusted fixture code с CSP connect-src
только127.0.0.1 и без внешних ресурсов. Полные bytes/SHA/provenance оракула в
B4-live-pins.json, тело ответов остаётся pinned B-3 data. Fetch и Network callbacks
реальные; native monitors на реальном owned page CDP, не fake stream.
AI auto-attach проверяется по Selenium target ID; Qwen monitor явным local-CDP
port binding (native host-discovery требует внешний hostname, здесь не имитируется).
Сверка state/thought/text/finish и actual parser extraction с прежними expectations.
DeepSeek native mirror_input/submit/confirm_sent проверяются на fixture textarea;
полный send/paste не вызывается, clipboard пользователя не читается/не меняется.
SW_SHOWMINNOACTIVE7, frozen launch flags, webdriver/visibility native honesty,
metadata-only foreground/input guard; устойчивый foreground или input change STOP.
Ни одного нового A запуска/новой маскировки/forced-minimize. Cleanup только own
Chrome/driver handles и свежего profile с nonce+inode, после process exit.
Следующее действие B: один записанный local-site live запуск AI/Qwen + native
mirror/Selenium против oracle.html, затем мутации/двойной focused/full regression.


### B.4 STOP — новая runtime-операция, не откат принятой A (2026-11-04)

Ровно один local recorded-site launch, повторов нет. Startup4/4: чужой foreground,
свой visible Chrome iconic=true. После выбора новой oracle-вкладки Selenium
на oracle-target-0 свой PID27112 оказался foreground, iconic=false. Классификатор
принятого A harness: fail, late_foreground=true, собственный foreground2.5859494с.
Это не startup race с восстановлением: native window-selection/runtime операция
нарушила критерий. B4-recorded-live.json и raw log сохраняют первоначальный red.
Код/критерий/expectations не подгоняются, маскировка/forced-minimize/новые flags
не добавляются; следующий live и перенос B.5 остановлены явным STOP-условием.
Сервер получил0POST; AI/Qwen live Network→parser и mirror/submit не исполнялись.
Input guard104 samples, environment_valid=true, failure=null, user input не менялся.
Cleanup readers/own processes/profile/listing/server всеtrue. Принятая A, frozen
facade/transport/browser/reference/native bytes и статус A не изменяются.
Новый B runtime effect пока needs_live; Arena/judge/STATE также deferred.
Следующее действие B: независимое рассмотрение этого STOP (Selenium target-selection
на background owned tab) и разрешённого без-фокусного local oracle-среза; до нового
явного решения никаких повторных Chrome запусков, новых механик или B.5 мутаций.
Сейчас допустимы только post-STOP read-only regression, tree/prefix verification,
CRLF итог WORKLOG и внешняя последняя seal; это не завершение/приёмка B.


### B — итог post-STOP регрессии (2026-11-04; partial, не acceptance)

Focused после STOP141/141 ×2; полный non-live5619passed/2legacy skips,
collected=executed5621, needs_live и tests/py/live исключены. Четыре реальных
gate ×2: lint583/0; limits583/0 и точные прежние split_py11/editing8400 warning;
contract28/0; SEC01–08/SEC20 allok ×2. Raw logs/JUnit/argv/exit_code в досье.
Исходный clean red-limit2/3 и дефект первого red harness сохранены, не заменены.
Полная B.0 AST классификация теперь44native dependency files,9candidates,
0ambiguous aliases: исходный stem-only42 inventory сохранён, dotted packages
досняты read-only. execute_script/execute_cdp_cmd классифицированы как browser
primitives, не dynamic Python exec. server_state/answer_judge не переносились.
Корпус102cases×2native,7byte-exact parser pins, explicit bindings44lines.
Новый local oracle pinned отдельно, но live replay0: initial B4 STOP не закрыт.
Мутации B.5:0 execution,0 restore claim — запрещено продолжать после live STOP;
их обязательное требование НЕ выполнено/НЕ выдано за долг принятой механики.
R-18/D26: внешний substrate selfcheck даёт needs_live, не fake module/probe,
44canonical reports не перезаписываются. Не утверждается public/runtime profile
или PyInstaller release: package __init__/bootstrap/channels не регистрируют bindings.
Документы historical prefixes проверяются целиком; new additions CRLF; frozen
PROGRESS/parity/tests-map/contract/facade/reference/transport/native не меняются.
Следующее действие: независимый разбор sealed B STOP, затем отдельное явное
решение о допустимом local CDP-only oracle и судьбе Arena; до него новых live
запусков, мутаций, production-profile интеграции или release packaging нет.
## D34 — двухфазный критерий no-focus для B.4 (разбор STOP, аудит 2026-11-04)

STOP B.4 разобран независимо (read-only, досье browser-b-runtime-20261104):
input-guard показал единственный тик ввода (68366984) на всех выборках —
интерференция пользователя ИСКЛЮЧЕНА, в отличие от STOP части A. Причина
локализована: 4 пре-активационные проверки чисты (Chrome minimized, foreground =
терминал), первый own-foreground наступил при выборе oracle-вкладки — native
`switch_to_site_window` использует `driver.switch_to.window(handle)`, а chromedriver
реализует это через CDP `Target.activateTarget`, который ПО КОНСТРУКЦИИ Chrome
поднимает окно. Это нативная семантика взаимодействия, не дефект фасада;
подавление потребовало бы запрещённого спуфа. Grep production (parsers/server/
browser) на SetForeground/ShowWindow/win32-подъёмы — пуст; самоподъёмов нет.

Критерий B.4 уточняется БЕЗ ослабления A-инварианта:
1) фаза launch/attach (до первой явной активации вкладки) — прежний критерий A
   (own foreground 0, устойчиво minimized) — уже доказан;
2) фаза взаимодействия — собственный foreground допустим ТОЛЬКО как прямое
   следствие явной нативной активации: каждый own-foreground-интервал обязан
   коррелировать с activation-командой в таймлайне CDP/Selenium (допуск 2 с);
   foreground вне activation = red; после взаимодействия окно остаётся как есть
   (принудительное сворачивание запрещено);
3) статический пин: ноль win32/форс-фокус вызовов в production (существующий
   grep-пин).

Статус B: B.0–B.3 выполнены и проверены (7 парсеров byte-exact, corpus + oracle,
141 тест ×2, full non-live 5619 pass/2 legacy skip, гейты зелёные); B.4 — live
replay по D34 не выполнен; B.5 (свои мутации) — не завершён; tests-map 174–202
остаются deferred честно (частичные кейсы не закрывают legacy-файлы — D33).
Окончательная приёмка B — после B.4 по D34 и B.5.


### B.4 D34 — свежая baseline и спецификация внешнего classifier ДО кода

A и B.0–B.3 приняты независимым аудитором; старое STOP-досье не изменяется.
Новый внешний каталог: c8_audit/browser-b-d34-20261104. Fresh baseline4119/855,
reports44/UID86/pyc0/4sentinels; семь парсеров byte-exact vs native, всё native
дерево unchanged. С прежним tree-after отличаются ровно три аудиторских документа.
Baseline gates: lint583/0, limits583/2 прежних warning, contract28/0, securityok/0.
PROGRESS/parity/tests-map и accepted production остаются frozen по substrate-мандату.

Внешний D34 classifier объединяет WinEvent и 5ms samples в непрерывные интервалы
по foreground HWND/PID. Launch-срез до первой successful owned activation:
прежний A classifier + строгий D34 own foreground0 и четыре startup checks.
Interaction: каждый новый own интервал начинается не раньше реальной команды
Selenium switchToWindow и не позже2с после её начала; команда successful и
принадлежит текущему facade-driver/owned target/Chrome PID. Длительность уже
разрешённого непрерывного интервала не ограничивается; новое возвращение без
свежей корреляции red. Future/failed/foreign commands не оправдывают foreground.
Пустой timeline/ошибка observer/недостаточные startup checks — fail closed.
WebDriver.execute обёрнут только во внешнем harness: timestamps до/после
реального execute; без дополнительных activation, focus или window-state команд.
Скрипт не активирует Target через CDP и не подавляет native Selenium семантику.
Метаданные ввода и cleanup сохранены; после взаимодействия forced-minimize нет.

Тесты classifier до live: clean/minimized startup, own pre-activation red,
2с inclusive/2с+1ns red, будущая/failed/foreign activation red, WinEvent-only,
непрерывный долгий foreground green, повторный unrelated interval red,
разные HWND/PID и недостаточная серия. Accepted corpus/expectations неизменны.
Следующее действие B: external D34 tests×2 → pin новой копии recorded_live.py →
один local-site replay по D34; при успехе B.5 mutations≥2new+≥1reference.

### B.4 D34 — classifier и instrument проверены, перед единственным live

Внешние unit `d34-unit-1` и `d34-unit-2`: collected=executed=25, passed25,
failed/errors/skipped0 каждый. Проверены не только синтетические интервалы, но
и execute-delegation: одна настоящая команда между timestamps, ответ identity,
исключение не становится success, чужие driver/target отказывают ДО execute,
не-activation команда не создаёт записи и дополнительных вызовов.
Пины изменённого внешнего harness и frozen oracle: `B4-live-pins.json`;
original pins и diff сохранены отдельно. Observer failure fail-closed без
прерывания owned cleanup. Runtime/reference/facade/transport/corpus не менялись.
Следующее действие: ровно один `recorded_live.py` с loopback AI/Qwen replay,
native mirror/Selenium и D34; любой red — STOP с сохранением отчёта, без rerun.

### B.4 D34 — STOP на Qwen terminal-state, не на фокусе (2026-11-04)

Единственный D34 recorded-site launch: startup4/4 foreign/iconic, startup own
foreground0; реальный успешный `WebDriver.execute switchToWindow` own target
at70897685871600ns, own interval start70897722359000ns (36.4874ms после команды).
Foreground5.9142365s непрерывно коррелирован с этой активацией: D34 ok; никаких
дополнительных activation/window-state/spoof команд. Это не повтор A батареи.
AI live: ответ256B/SHA8d05687c…, native text/thought/finish/status полностью совпали.
Qwen: сервер отдал795B/SHAf0bf41ec…; проверка receipt795 прошла; настоящий
Network.streamResourceContent buffered462B. Native answer «Читаю сцену 🦔»,
thought «Размышление 1\n\nРазмышление 2», finished=true/generating=false/count1,
но terminal status FAILED вместо corpus FINISHED. В stdout до teardown:
`loadingFailed: net::ERR_ABORTED (canceled=True)`. Assertion state mismatch
сохранён в B4-recorded-live.json; это красный live, не успешно закрытый Qwen.
Первопричина canceled transport ещё НЕ доказана; нет права подгонять ожидание,
чинить native/frozen runtime, повторять launch или начинать B.5 после red.
Native mirror/submit не достигнуты; B.5 mutations0. Input guard valid/single tick,
observer error=null; readers/owned processes/profile/listing/server cleanup true.
Original STOP/A/B.0–B.3 evidence не изменяются. Далее разрешены лишь read-only
post-STOP regression/gates, byte-prefix/tree/seal доказательства и CRLF отчёт.
Следующее действие: независимый разбор Qwen canceled/FAILED, затем отдельное
явное разрешение на диагностический срез/следующий live; до него B.4/B.5 STOP.

### B.4 D34 — post-STOP regression и частичный машинный вердикт

Без нового launch/мутаций: external D34 classifier+execute instrument25×2;
runtime focused141×2; full non-live collected=executed5621:5619passed/2legacy skip.
Гейты lint_arch583/0, check_limits583/0 (ровно2 прежних warnings), contract28/0,
security SEC01–08/20 ok, все четыре post-STOP×2 (fresh baseline также green).
D26 external substrate selfcheck: status=needs_live, independently_accepted=false,
mutation_execution_count=0; stdout и итоговый JSON находятся во внешнем досье.
Это проверка STOP, НЕ закрытие B.4/B.5 и НЕ приёмка части B.
Fresh4119files/855dirs: все production/reference/contract/corpus/tests/reports
не изменены; native whole tree и7парсеров byte-exact;44reports/86UID/0pyc,
4fixture sentinels сохранены. Разрешённые repo изменения только CRLF append
browser-runtime.md/WORKLOG.md/porting README, без изменения исторических префиксов.
PROGRESS/parity/tests-map174–202 и Arena/judge/server STATE остаются deferred/frozen.
Evidence: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-b-d34-20261104/:
B4-recorded-live.json (первый red, неизменён), B4-D34-STOP-summary.json,
B4-live-pins.json/B4-harness.diff, D34unit×2, post-STOP regressions/gates,
tree-boundary-proof.json, substrate-selfcheck.json/stdout.log, финальный SHA256 seal.
Event transcript помечен как transcription tool stdout, НЕ raw CDP event log.
Следующее действие: аудитор должен разобрать canceled Qwen/FAILED и выдать
отдельное разрешение на диагностику/следующий live; без него STOP B.4/B.5.

### Решение пользователя: отложить ручной разбор Qwen, не отменять перенос

2026-11-04: пользователь решил не останавливать общий перенос плагина ради
текущей live-проблемы Qwen. Её диагностика/исправление отложены до полного
переноса: причину пользователь сможет выяснить вручную в работающем плагине.
Точная фиксация: Qwen НЕ прошёл текущую recorded-site проверку (terminal FAILED
вместо FINISHED, net::ERR_ABORTED); первопричина неизвестна. Это НЕ доказательство
невозможности сделать Qwen работающим и НЕ утверждение, что отменён весь перенос.
Сохранены red-отчёт, пины и sealed browser-b-d34-20261104; код/корпус не меняются.
B.4 остаётся needs_live/deferred; mirror/submit не проверены, B.5 не выполнен.
Условия окончательной live-приёмки не ослабляются, ported/accepted не назначаются.
Нет нового разрешения на Chrome, B.5 мутации, productionprofile/bootstrap,
releasepackaging или Arena/judge/STATE; прочие механики идут по своим мандатам.
Следующее действие по этой проблеме: после полного переноса пользователь вручную
диагностирует Qwen loadingFailed/FAILED, затем отдельно возвращается к live-паритету.
