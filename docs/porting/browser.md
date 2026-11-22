# B-1 — browser transport и read-only фасад

Статус: **B-1 готов к независимой приёмке**, не ported и не принят. Этап: 6,
transport/facade, двойной корпус, live и собственные мутации проверены. Baseline снята
после восстановления аудитора (2026-11-03). В таблице 44 механик этого
substrate-среза нет; она не меняется.

## Цель и граница

Источник: `D:/vajno/Godot/random-game/addons/godot_agent/python/browser/`.
`browser_manager.py` (193 строки, 12663 B, SHA256
`4afd245fbd4a4ab1cf95cb8be5435a6fc1ae30a788d891bcb2246f781e974d07`) и
`cdp_ws.py` (390 строк, 15867 B, SHA256
`3b5298dd76c061ce082828d9778b006b7fc68ed6dd1442e0bb4b95b5f95d339b`)
переносятся byte-exact как transport-эталон. Native `setup_browser()` не
вызывается: D24 устраняет конфликт native-launch с R-21.

Новый не-verbatim фасад ≤100 строк: pinned launch, процесс с no-focus,
selenium attach, CDP создание/чтение/закрытие своей file:// вкладки, cleanup.
Контракт `contract/browser_stealth.json` уже существует; его значения, в том
числе 10 forbidden techniques, не меняются. B-2/B-3, net_monitor/sites,
парсеры/backends и 44 канонических selfcheck-report остаются byte-exact.

## Решения и diff запуска против native

- D24: фасад владеет process handle; STARTUPINFO + STARTF_USESHOWWINDOW +
  SW_SHOWMINNOACTIVE и close_fds=True. Занятый 9222 → отказ до Popen;
  native attach к неизвестному процессу не переносится. Selenium только
  debuggerAddress, ChromeService popen_kw={"close_fds": True}. Уборка только
  собственного процесса. Маскировка не добавляется, spoof не регистрируется.
- D25: только для live новый пустой sibling-профиль
  `%LOCALAPPDATA%/Godot_AI_Profile_B1_<nonce>`; nonce/listing до/после,
  создание и точечная уборка прогоном. Существующий Godot_AI_Profile не
  читается/не изменяется/не удаляется; production-пин остаётся прежним.
- D26: формальная батарея ниже вместо selfcheck browser. Стражи и
  регистрация модулей не меняются. Решения записаны аудитором в deviations.md.
- D27 (явное разрешение пользователя): только disposable live/oracle добавляет
  --no-first-run, поскольку Chrome156 first-run нарушил no-focus и отказал
  Target.createTarget. Разрешена официальная загрузка ChromeDriver156 с SHA;
  production-контракт, masking и transport bytes не меняются.
- D28 принят независимым аудитом: общий SEC-20 вырезает полные JS // comments.
  После отдельной независимой приёмки SEC-03 текущий tools/security_audit.py
  SHA d4679c4c18bb219d5099fef56f49d82261bc0a41c8e962a8cac86ddc6ba92467 снова
  заморожен в B-1; native-комментарии и contract/browser_stealth.json не меняются.

## Спецификация не-verbatim фасада до кода

`python/substrate/llm/browser/facade.py`: `ReadOnlyBrowser(chrome_path,
driver_path=None, *, live_profile=None)`; публичные операции open/read/close_tab,
close и контекстный менеджер. Read возвращает только title/text фиксированным
CDP-выражением; произвольный JS, внешние URL, отправка и спуф не доступны.

Default profile — строго LOCALAPPDATA/Godot_AI_Profile. Live override допускает
только существующий пустой sibling Godot_AI_Profile_B1_<32 hex>; создаёт и
удаляет его внешний прогон, а не production-фасад. --no-first-run добавляется
только вместе с этим тестовым override (D27). Доступность 9222 подтверждается
exclusive bind 127.0.0.1:9222 (SO_EXCLUSIVEADDRUSE), без listen и owner lookup;
probe закрывается до Popen. Любой OSError означает отказ до Popen, без чтения
чужого endpoint. TCP timeout не доказывает занятость или доступность порта.
После своего Popen PID проверяется по browser
process metadata до Selenium attach: cleanup не отправляет Browser.close
неподтверждённому процессу. Это реализация ownership D24, не новая маскировка.

Native find_chrome/_wait_for_debug_port можно использовать как примитивы;
setup_browser/harden_background_tab не вызываются. HTTP readiness читает
только loopback с ProxyHandler({}); service держится для cleanup failed attach.
Созданный target записывается до attach/navigation; ошибка закрывает именно
его, read/close_tab не принимают чужой target. Допустимые CDP-команды:
SystemInfo.getProcessInfo, Target.createTarget/attachToTarget/closeTarget,
Page.enable/navigate, Runtime.evaluate и Browser.close своего процесса.

## Старые тесты / R-17

Все browser-строки tests-map.md:174–202 имеют судьбу deferred. Для B-1
из test_browser_target_binding берутся только кейсы exact target и cleanup
failed connection; из test_v87_1_kimi_cdp — транспортные roundtrip/порядок/
неполный кадр, не код и не внешние HAR/pickle. Парсерные, сетевые мониторы,
отправка сообщений и site spoof остаются B-2/B-3. Строки не удаляются и
deferred всего browser-покрытия не снимается частичной B-1 проверкой.

## Корпус и спецификация

Собственные file:// HTML-страницы без внешних ресурсов и spoof. Native CDP
снимает ожидаемые read-only snapshots; записываемые кадры нормализуют только
случайные target/session IDs и абсолютный корень fixture. Отдельные локальные
WebSocket кадры проверяют fragmentation, masking, ping/pong, length и close.
Публичный ToolSpec отсутствует: это substrate, не новый инструмент.

## Проверка (R-18 для substrate)

1. Focused pytest новых substrate unit/integration + tests/py/security стражей:
   contract missing/shrunk, pinned flags/profile/no-focus, busy-port refusal,
   no spoof, exact target, cleanup/error paths, transport bytes/frames.
2. Неизменённые lint_arch, check_limits, gen_contract --check, security_audit.
3. Двойной fixture-прогон file:// против native-корпуса без расхождений;
   результаты и collect/executed IDs — наружу.
4. Реальный Chrome D24/D25: foreground/window state, честный webdriver=false,
   own targets, no script registration, profile/process/tab cleanup.
5. Собственная мутация → действительный red → byte-exact restore → green.

Отчёты только наружу: исторические проверки в `b1-delivery-20261103/`, финальная
live-стадия в `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/b1-live-20261103/`.
`reports/selfcheck/` не используется. Финальная SHA256-final.json записывается
последней; зелёная батарея — передача аудитору, не самостоятельная приёмка.

## Своя исходная база

3910 files total / 3906 без fixture-cache contents, production cache 0,
pyc 0, существующих UID 86, reports 44, capabilities 28 + template, ADR17,
prompts46. WORKLOG679088 B / SHA256
`3fc80bf8ad2178de798ba31ec376a42f6e44829e5af472e258cd2710fef64d60`.
project335 B / SHA256
`958b3a92d706979e715a7cf77fe4a1d6ac008314bb215c213151ad1476fb3b29`.
Baseline и protected raw bytes во внешнем досье; чужие UID/cache не чистятся.

Чистая baseline возобновления: 3916 files / 3912 вне fixture-cache, UID86,
44 reports, capabilities28 + template, ADR17, prompts47, production cache0,
pyc0. WORKLOG690151 B / SHA256
`a1c322dfbe415111fd1fd270ef303473a7b3c95206e155a9cb14d68d57149732`.
Четыре восстановленных sentinel-файла __pycache__ сверены с запечатанным D28:
bytes/SHA/EOL exact. Эти каталоги не мусор и содержат .gd/.py/.uid, не .pyc.
Исторические досье b1-final, sec20-fix и b1-resume не перезаписываются.

## Следующее действие

Независимый аудитор проверяет SHA/tree/границы и выполняет собственную B-1
батарею, включая реальный live-повтор; вердикт ACCEPTED/STOP записывает он.
До приёмки этап7/ported не заявлять и B-2/B-3 не начинать. Production-фасад,
native, принятые стражи и44таблица не менялись.

Независимая приёмка SEC-03 записана аудитором сессии78 в WORKLOG/deviations/README;
STOP снят, мелкий долг независимого reflection-mutation покрытия остаётся вне B-1.
Continuation checkpoint 2026-11-04 не заменяет прежние baseline:3937files,
44reports/86UID; WORKLOG699814B/SHA256
`7943712aa5557530807d0b7d6dadaadc454f8236f2a4a0d41909a1e15aad1ea5`.
Четыре auditor-doc изменения и пустой tools/__pycache__ исследованы и сохранены;
sealed SEC-03 dossier1543/1543 exact, его WORKLOG-prefix точен. Досье новой стадии:
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/b1-live-20261103/`.

## Шаг 6 — финальная live-батарея портера (2026-11-04)

- External bounded wait: собственные6пинов дали6expectedfail до helper,
  затем6/6green,0errors/skips. Таймаут/потеря initial/чужой page не скрываются;
  исчезновение owned проверяется среди всех target types, не фиксированным sleep.
- Два wire replay35/35 каждый и собственные plain/lines2/2 каждый совпали с
  замороженным native-корпусом; нормализованные snapshots всех4live одинаковы.
- Реальный Chrome156.0.8078.74/официальный driver156.0.8078.80: основные live3/3,
  плюс sandbox-restored live1/1. Selenium только debuggerAddress; webdriverFalse,
  native webdriver/hasFocus/hidden/visibility/toString, own descriptors отсутствуют.
- STARTUPINFO{dwFlags:1,wShowWindow:7}/close_fdsTrue; CDP и OS окна minimized/iconic;
  WinEvent hook+5ms sampling: свои foreground hits0. Owned close bounded polls
  [1,1,1,2]; initial pages сохранены до Browser.close. Свои8handles exit0,
  reader stopped/socket released;6собственных nonce profiles убраны/listing exact.
- Занятый9222: реальный свой exclusive bound socket без listen; facade отказал
  до Popen/readiness/HTTP/owner query (все0), held socket закрыт, пустой profile убран.
- Live-мутация фактического sandbox-файла: убрана одна SO_EXCLUSIVEADDRUSE строка,
  реальный bind прошёл с OSexclusive0, пин красный до Popen (Chrome0). Copyfile
  restore100LF/SHA6abe81d…b0b98 exact; восстановленный sandbox прошёл настоящий live.
  Production-фасад не мутировался в этой стадии; прежняя actual-file profile
  mutation-bind93/91pass/2expectedfail/exactrestore/restored93green сохранена.
- Неизменённые lint_arch/check_limits/gen_contract --check/security_audit ok/0;
  audit stdout дважды exact. Focused93collect=execute=pass; full security239
  collected/executed,237pass/2прежних symlink skips/0fail/error; JUnit IDs exact.
- Native transport bytes/SHA/EOL и весь production/корпус/contract exact;
  reports44/UID86/четыре fixture-cache sentinels сохранены, pyc0. Setup/harden0,
  script registration/focus/bounds spoof0; внешние сайты/чужой profile не трогались.
- Машинные сводки: live-battery-summary.json, live-evidence-verification.json,
  live-mutation-restore-proof.json, gates-summary.json. WORKLOG только ab+CRLF
  с точным699814B prefix; FINAL.md/AUDIT.md и SHA256-final.json последним наружу.

Вердикт портера: **готов к независимой приёмке B-1**. Этап6, не accepted/ported;
приёмку всей browser-ветки, B-2/B-3 и независимую проверку не подменяет.

## Исправление port-probe — red до правки фасада

Первый fixture-1-live честно отказал до Popen: TCP connect 127.0.0.1:9222
timeout, Chrome/Selenium не запускались. Собственный пустой профиль удалён,
listing exact. Диагностика: listeners9222=0, TCP connect0.2/2.0 оба timeout,
exclusive bind проходит; listen/HTTP/owner lookup отсутствуют.
Два новых кейса требуют exclusive bind и отказ при PermissionError.
Первый red-bind93executed/29fail недостоверен: fake socket установлен перед
ленивым Selenium Chrome import. Он сохранён. После исправления только порядка
подмен фикстуры red-bind-fixed-fixture:93collect=executed,91pass/2expectedfail,
errors/skips0; фасад всё ещё использовал TCP probe. Это local D24 fail-closed
repair, не изменение native транспорта, launch-пинов или masking.

Текущий фасад после repair:100LF, SHA256
`6abe81d207c963d9fa58775974aa1bf0828ae9d16edd6bdb7031055b1dcb0b98`.
Green-bind93/93; actual-file mutation-bind91pass/2expectedfail,errors/skips0;
copyfile restore byte-exact (proof наружу); restored-bind93/93.
Набор теперь77новых B-1 +16принятых D28. Предыдущие91-case результаты ниже
исторические, не финальная батарея bind-варианта. TCP probe в фасаде отсутствует,
любой OSError exclusive socket/bind даёт RuntimeError9222 до Popen.

Повтор bind-батареи: lint_arch/check_limits/gen_contract --check = ok;
замороженный security_audit = fail, ровно SEC-03 на `.bind()` фасада. AST
подтверждает setsockopt+bind, listen-вызовов0. Guard не менялся; обхода regex нет.
Отдельно full security:168 collected/executed,166pass,2 прежних skip,0fail/error.
Wire fixture-bind-1 =35/35. Реальный Chrome156.0.8078.74 + driver156.0.8078.80
подключились; свои plain/lines =2/2 с честным webdriverFalse и native getters.
Но fixture-bind-1-live =fail: после двух успешных closeTarget немедленный
getTargets ещё содержит один свой закрываемый target. Eventual disappearance
до Browser.close не подтверждён; окно OS enumeration и второй/третий live
не завершены. Нужна bounded readiness-проверка в harness, не изменение native
или focus/spoof; повтор допустим только после снятия SEC-03 STOP.
Cleanup подтверждён:reader stopped/socket released, свои chrome/driver exit0,
profile nonce8f1295b4681c432cada35076e1e8525a удалён, sibling listing exact;
foreground попаданий своих PID0, setup/harden0. Чужой профиль не читался.
Доказательства: внешний `bind-stop-diagnostics.json` и сырые bind-артефакты
в активном b1-delivery-20261103. Reports44/UID86/non-B-1 byte-exact.
Этап5, независимой приёмки и ported нет; финальная успешная батарея не заявлена.

## Шаги 4–5 — transport, фасад, green и собственная мутация

Два transport-файла доставлены `shutil.copyfile`: bytes/SHA/EOL exact против
native; смешанный EOL browser_manager сохранён. Native setup не выполнялся.
Фасад ровно100строк, SHA256
`b4c03319082699de95adb0548d0905dac6c5dcf3a4a3b5da3c7bde139e6d74ae`.
Все backend handles/state приватные; публичные операции только open/read/
close_tab/close/context manager. Это исправление собственного дефекта против
спецификации read-only, не улучшение native. Дополнительный пин дал red-private
91 executed / 1 expected fail до переименования полей; public mutation surface
закрыт. Предварительные 90-кейсные прогоны сохранены, но не финальная батарея.

Сдаваемый focused набор: 75 новых B-1 + 16 принятых D28 = 91.
Green-final91/91; на фактическом сдаваемом facade удалён только profile-аргумент
Popen → mutation-final89pass/2fail (production-pin и disposable-pin), errors/
skips0; backup/restore `shutil.copyfile`, SHA и100LF byte-exact. После restore
91/91green. Native, contract, accepted SEC-20 и44reports не мутировались.
Выводы и proof наружу; это пока unit/mutation, не Selenium live и не приёмка.

## Шаг 3 — корпус и red до production-кода

Own wire-корпус `fixtures/corpus/browser/b1/wire.json`: native MiniWebSocket
6 receive / 4 send и Connect 4 кейса, без реальных сокетов/Chrome. Unicode,
fragmentation/ping/pong, masked input, длины126/127, close, порядок/incomplete/
bad JSON. Native close-frame особенность (после remote close последующий close
не вызывает socket.close) сохранена как наблюдение, не исправляется в эталоне.

Focused red-final: 90 collected/executed, 28 pass / 62 expected fail,
errors/skips0. Это 74 новых B-1 кейса + 16 неизменённых принятых D28.
Предварительный red на 88 кейсах сохранён отдельно; перед production добавлены
два случая (wake pending on reader close / navigation errorText), сдаваемый
набор — 90.

Общие inert fixtures только в `tests/py/conftest.py`; новые unit-файлы
`test_browser_b1_transport.py`, `test_browser_b1_facade.py` и security-файл
`test_browser_b1_guards.py`. basetemp/JUnit/stdout наружу. Contract missing/
shrunk forbidden-list, все10tokens, pinned site flags и own-process/no-focus/
profile/read-only-target стражи записаны до transport/facade.

## Шаг 4 — финальная live-стадия B-1 (постановка аудитора, 2026-11-03, сессия 78)

Последняя стадия перед передачей приёмке. Цель — доказать живой фасад
end-to-end по D24/D25/D26/D27 на file://-фикстурах. Всё то же: внешние сайты,
пользовательские сессии и профиль Godot_AI_Profile запрещены.

1. External live harness — новый файл `tests/py/live/test_browser_b1_live.py`
   (или внешнее досье-исполнение с записью в лист, но не production-код).
   Дважды (R-07/R-08), результаты обоих прогонов сохранены.
2. Обязательные live-проверки каждого прогона:
   - запуск через фасад: exclusive-bind-отказ при занятом 9222 (fail-closed);
   - disposable-профиль `Godot_AI_Profile_B1_<nonce>` создан до и удалён после
     (listing %LOCALAPPDATA% до/после идентичен, D25);
   - `--no-first-run` только с тестовым override (D27);
   - webdriver честно `false` (Selenium через debuggerAddress);
   - окно минимизировано и никогда не foreground (PID-sampling);
   - file://-вкладка открыта/прочитана (title/text)/закрыта;
   - после closeTarget — **bounded wait** исчезновения owned Target
     (poll с таймаутом), фиксированный sleep доказательством не считается;
   - cleanup: убит только собственный процесс (PID подтверждён до attach),
     returncode записан, исходные вкладки/окна Chrome не тронуты.
3. Live-мутация (R-22): в sandbox-копии фасада удалить `SW_SHOWMINNOACTIVE`
   (или SO_EXCLUSIVEADDRUSE) → соответствующий live-пин красный →
   byte-exact restore → зелёный.
4. Записи: досье `%TEMP%\opencode\c8_audit\b1-live-20261103\`; лист —
   этот раздел дополнить результатами; WORKLOG append (префикс на момент
   постановки 698 282 B, SHA `1db6d0ac3605f009f11a11fa6ac2231d2f67ba9f729b8759639cac3a7fe16739`).
5. Вердикт портера — «готов к независимой приёмке B-1». Не заявлять ported/
   accepted: приёмку делает аудитор своей батареей, включая собственный
   live-повтор и сверку границ.

Стоп-условия прежние (§6, стражи/R-21 не ослаблять, verbatim-конфликт —
стоп-вопрос). После приёмки B-1 портер переходит к B-2 (net_monitor, 456
строк — заранее готовить предложение по отклонению R-06).


## Собственные результаты шага 1 / STOP SEC-20

После D27 native-CDP oracle: 2/2 snapshots, честный webdriver=false и native
getter, native hasFocus, нет own visibility/hidden descriptor; окно minimized,
own Chrome никогда foreground (PID-sampling), own targets созданы и закрыты,
исходные page-targets сохранены. Process returncode0, disposable profile удалён,
listing %LOCALAPPDATA% exact. `native-corpus-live-3.json` в досье. Это ещё не
Selenium/facade live и не двойной fixture-прогон. ChromeDriver156.0.8078.80
получен из официального Chrome for Testing в external dependencies, SHA256
`95ae04aebd7daf845dce58d42139f0acbf1a5172fd480db328ea70bdc6301790`.

Перед копированием в production выполнен external preview: оба native-файла
скопированы byte-exact только в sandbox; неизменённый check_browser_stealth
дал ровно 2 отказа — hasFocus и toString из JS-комментариев строки71–73:
«hasFocus НЕ подменяем», «document.hasFocus.toString()». Python # комментарии
страж убирает, JS // внутри raw literal — нет. `sec20-native-preview.json`.
Это подтверждённый конфликт verbatim и обязательного зелёного SEC-20, а не
реальная новая подмена. Аудитор/source/контракт не ослаблены, native не правлен.
На момент исторического STOP transport оставался заглушками; фасад, новые
pytest-стражи, мутация и двойной прогон не были начаты. D28 снял этот STOP;
актуальное следующее действие записано выше. Пины контракт-данных не менялись.

## Приёмка B-1 аудитом (2026-11-04, сессия 78)

Независимая приёмка этапа 6 (финальная live-стадия): досье `b1-live-20261103` 450/450
byte-exact (печать cbf7cb9e…); tree-final 3937 файлов против репо — 0 реальных расхождений;
граница стадии подтверждена (только лист/parity/WORKLOG, +3298/+146/+3987 B, хвосты CRLF).
Свои прогоны: focused 93/93; полный tests/py/security 237 pass / 0 fail / 2 прежних skip;
lint_arch 569/0, check_limits ok/2 (прежние), gen_contract --check 28/0, security_audit ×2 ok/0.
Двойная собственная live-батарея (копия проверенного харнесса в sibling-досье, baseline —
запечатанный tree-final портера): busy-port refusal ок, двойной wire 35/35 + file:// 2/2,
live 3/3 + restored sandbox live 1/1 (4 запуска Chrome), live-мутация
SO_EXCLUSIVEADDRUSE → red до Popen → byte-exact restore → green; boundary-check до/после —
репо неизменен. Результат: **B-1 базис принят** (transport-эталоны byte-exact, фасад 100 строк,
стражи SEC-03/SEC-19/SEC-20 + D24–D28). Это не ported всего browser.

Замечание (не блокер, перенесено в parity): в первом live-прогоне аудита Chrome кратко
(~0.4 с) вышел в foreground и к моменту OS-снимка не был свёрнут (fresh disposable-профиль,
pinned запуск, ноль правок фасада; события EVENT_SYSTEM_FOREGROUND pid=свой browser-процесс).
Полный повтор батареи — 3/3 + 1/1 чисто; у портера 4/4. Итого 7/8 чисто — гонка старта Chrome,
а не механика фасада. Детерминизм no-focus (retry/verify-усиление) закрепить отдельным
разрешённым срезом до B-2 или внутри B-2; unit-пины детерминированы и не страдают.

Следующий шаг: B-2 — `net_monitor.py` (456 строк, выше потолка R-06; готовить отклонение
лимита или разбиение на подготовительном срезе), затем sites/live_input/парсеры (B-3).


## No-focus детерминизм — STOP, не закреплён (2026-11-04)

Отдельный разрешённый runtime-срез: внешний accepted B-1 harness скопирован,
добавлены четыре foreground/OS-window выборки через ~0.5 с и классификатор
<1.5 с с восстановлением minimization; production/facade/эталоны не менялись.
Unit-классификатор 8/8 ×2. Первый live: wire 35/35, file reads 2/2,
busy-port refusal 1/1, webdriver=false, spoof/setup 0, полный cleanup exact.
Но собственный Chrome foreground 2.3900946 с; четвёртая OS-выборка own PID /
iconic=false, CDP windowState=normal. Критерий провален; STOP без retry до green.
Полная батарея ×2 и цель 8/8 + 8/8 не достигнуты, повтор и sandbox не запускались.
A не закреплена, B не начата. Это не отзыв прежней независимой приёмки B-1.
Исторический LF-префикс сохранён byte-exact; только добавка CRLF (§A.3 имел
неверное предположение о старом EOL). См. browser-runtime.md и внешнее досье
C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-runtime-20261104/.


## Контролируемый повтор A — passed, независимая приёмка впереди (2026-11-04)

По отдельному решению WORKLOG:7726–7740, после подтверждения нулевой активности
оператора выполнены ровно `a-controlled-1` → `a-controlled-2`: 4/4 + 4/4
реальных Chrome, 8/8 + 8/8 own-file observations, wire 35/35 ×2 на серию,
mismatches 0. Все восемь own foreground=0.0 с, own_process_never_foreground=true,
четыре OS-выборки, последние две iconic/recovered; CDP minimized, webdriver=false,
native setup/spoof=0, busy refusal и red/exact restore/green ×2, cleanup exact.
GetLastInputInfo parent1007/worker463+462: одна неизменная метка, API errors0.
Harness/classifier/Chrome/driver byte-pins unchanged; новых флагов/спуфов,
принудительного minimization, повторов и третьей porter-серии нет. Существующий
r4-live 4/4 + 8/8 — третий контроль, не повторялся. Исторический STOP выше
сохранён: причина не локализована, невозможность Chrome-race не утверждается.

D26/R-18 post: focused182 ×2, classifier8 ×2, external caller22 ×2;
full non-live5478 passed +2 legacy skips; lint573/0, limits573/2 прежних warning,
contract28/0, security ×2 ok/0. Repo неизменен в обеих live и post-checks;
финальная доставка — CRLF-добавки только в три разрешённых документа,
исторические prefixes byte-exact; production/references/native/44 reports,
contract/parity/PROGRESS/tests-map/project/UID/sentinels frozen, pyc0.

A controlled-repeat passed и передаётся на повторную независимую приёмку;
acceptance не заявлена. B.0–B.3/все B не начинались и ждут закрытия A.
См. актуальный browser-runtime.md и новое внешнее досье
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-a-controlled-20261104/`.
Следующее действие: независимый вердикт по sealed A; B пока не начинать.
2026-11-04 · Аудит (сессия 78): долг «детерминизм no-focus» закрыт —
контролируемый повтор части A принят независимой приёмкой: 8/8 реальных
запусков Chrome без нарушений (own foreground 0,0 с, окна minimized, тик ввода
неизменен) плюс контрольная серия аудитора r4-live (4/4). Критерий усиленного
live-харнесса подтверждён; честная граница: не доказана невозможность гонки
Chrome во всех окружениях. Детали приёмки — лист browser-runtime.md.


## 2026-11-04 — B runtime partial / STOP (не приёмка)

A остаётся принятой независимым аудитором, её no-focus debt закрыт; повторных
A батарей не было. В B перенесены7native parser files byte-exact, добавлены
explicit runtime_bindings и owned runtime_owner.wait_driver; публичные профили/
bootstrap/tools не регистрировались. 102native corpus cases×2, focused141×2,
full non-live5619passed/2legacy skips, gates×2/security×2ok.
B4: один local launch; startup4/4minimized, после Selenium выбора oracle-tab
own foreground/iconic=false,2.5859494с, STOP. HTTP replay0, mirror/submit0;
cleanup и input guard104samples allok. Повтор/forced-minimize/новые flags/
спуфинг/подгонка expectations не делались. Arena unconditional answer_judge и
STATE branches deferred, без fake judge. B5 mutations не начаты из-за STOP.
Полный след: docs/porting/browser-runtime.md и external dossier
C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/browser-b-runtime-20261104/.
Не accepted/ported; PROGRESS/parity/tests-map/44reports frozen по D26/мандату.
Следующее действие — независимый разбор sealed STOP и явное решение до нового live.
