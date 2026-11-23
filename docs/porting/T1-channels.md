# T-C — локальные HTTP/MCP и editor-link

## Продолжение: key settings403 / chats list500 (2026-11-23), этап 5

Первый срез проверял неполную native envelope без addon_dir и не охватил
settings/chat controls. По новому пользовательскому логу ADR-0091 и
SEC-HTTP-CONTROL записаны до кода: точная service table, пять discarded
project-policy fields, guarded external config, никаких новых прав/сетевых эффектов.
Новые composition/security tests созданы; actual user chat JSON проверен только
на форму: list20/objects/readable, без вывода/копирования переписки; файлы не меняли.
Пришёл отложенный предыдущий tests/py:5952pass/6fail/2skip (1029.48s).
Три failure на прежнем UID corpus membership, два editor-live ждут port.json
при активном native entry, один TTL denied!=not_found; full GREEN не заявлен.
RED r2 до кода:32failed/14passed, реальные settings403/SessionContextError500,
две linked-key refusal failures200. Первый RED имел fixture client errors2:
исправлен импорт существующих fixture без ослабления asserts, вывод сохранён.
Auth/runtime-only correction готова:14 exact routes/five fields, external config
inputs/outputs guard и redacted AppError403. Native reference bytes не меняли.
Same IDs GREEN46passed. Полный offline lifecycle обнаружил отсутствующий
clear_request_activity: после new следующий rename409. RED3fail/1pass (lifecycle,
cleanup при HTTP-ошибке/исключении, сохранение чужого exchange) → runtime вызывает
существующий thread-owned native cleanup в finally → собственные50passed.
Связанные suites353passed до cleanup и final357passed (300.28s) после него.
Final security/layers/limits/contract exit0, два прежних limits warnings;
genuine selfcheck assistant.write ok/unit43/corpus4/differences0, REPORTS external;
read-only probe ok на отдельном synthetic project.godot. Запечатанные отчёты сохранены.
Offline staged build пересобран после final cleanup; три actual socket-цикла
source/explicit-exe/isolated-zeroarg-exe GREEN с полной panel envelope: settings
save/add200, masked replies и external persistence, существующий chat list200,
new/list/rename/open/model/delete200, browser/status idle. No-key guards проверены
до synthetic key save; configured api/test/refresh не вызывали, provider/browser traffic0.
Auth/Host/Origin403/project409/sensitive-policy403, contender exit2/foreign endpoint
exact, owned shutdown exit0/cleanup, project/token/policy unchanged во всех циклах.
Zeroarg — synthetic deployment с внешним APPDATA и port5000, не живой Godot UI.
С отдельного разрешения пользователя endpoint завершённого PID26668/session
9a273edb903f4a2084c9dbd173d18810 сохранён как http_endpoint.stale-26668-20261123.json;
сверены identity, отсутствие процесса (OpenProcess ERROR_INVALID_PARAMETER) и listener,
bytes exact, token/policy untouched. Автоматическая очистка остаётся запрещена.
Прежний exe сохранён в external control-envelope-exe-backup-20261123; проверенный
staged exe установлен в python/dist/godot_agent_server.exe, SHA256
26de3c038b13f5b44f401df67b3c7110a0f520ee1cfd74b3089f2f87b0165334.
Пользовательский сервер не запускали; ключи/переписка не менялись. Следующее действие:
пользователь перезапускает Godot и проверяет сохранение ключа/список чатов в реальной
панели; previous full6fail остаётся не GREEN, общая приёмка T-F.6 не меняется.

## Коррекция POST 403 (2026-11-23), этап 5: код/проверка

Причина: сохранённый allow_addons=true в общей обёртке POST панели; GET
progress не содержит поля и проходит. ADR-0090/SEC-HTTP-METADATA фиксируют
удаление UI-политики на шести точных служебных путях без повышения прав.
Судьбы legacy server/auth/API tests-map и прежняя приёмка не меняются.
Новые regression/security: 30 failed / 9 passed, ошибка ожидаемого HTTP 403;
без collection errors. ProjectAuth исправлен, native/GDScript неизменны.
Same-ID 39 passed. Связанные suites: 302 passed / 1 failed выявили нарушение
endpoint ownership; ещё четыре security cases genuine RED. Убрана guessed-PID
очистка, восстановлены exclusive create и owned finally. Гейты security/layers/
limits/contract ok, limits содержит два прежних предупреждения.
Окончательные связанные suites307passed; genuine selfcheck assistant.write ok
(unit43/corpus4), read-probe ok на изолированном project.godot. Офлайн exe
пересобран. С разрешения пользователя старый endpoint PID18332 переименован
в http_endpoint.stale-18332-20261123.json; bytes сохранены, токен/настройки нетронуты.
Первый live helper прошёл шесть metadata200/negative-auth403/project409, но
ошибся путём shutdown (/shutdown вместо /server/shutdown); owned child остановлен,
неуспешные logs сохранены, production не правился ради ошибки helper.
Три реальных socket-цикла source/explicit-exe/zeroarg-exe GREEN: шесть POST200,
auth/Host/Origin403/project409/policy-sensitive403, no_key denied; второй процесс
не присваивает endpoint, owned shutdown exit0/cleanup, project/token/policy exact.
Zeroarg в изолированной deployment-копии, port5000/external APPDATA; пользовательский
сервер/Godot UI не запускались. SHA256 exe: a5e8a4206b0d3b644fa6346c131c1ea399cafb1f15d1d8a69326c4f959deadf0.
Launcher read-only check: cached exe отсутствует, manual/onedir/старшие priority
candidates отсутствуют; существующий fallback — пересобранный python/dist exe,
его SHA повторно exact. Cached user setting не менялся. Final gates4/git diff--check ok.
python/modules: 2569passed (40.38s). Отложенный tests/py завершён:
5952passed/6failed/2skipped; GREEN не заявлен, причины перечислены в продолжении выше.
Срез ADR-0090 историчен; следующий шаг по текущему пользовательскому запросу —
проверка новой ADR-0091 сборки в реальной панели, без изменения приёмки T-F.6.


Этап 7 (локальный offline transport scope), 2026-11-21. Мандат T1. Native `server/*` — byte-exact references;
`tools/godot_agent_mcp.py` — semantic sample, не автоматический whole-host port. Активные каналы переводят
протокол в один rebuild Agent, без бизнес-логики и импорта чужого domain.
Native main/selfcheck/agent_bridge — только семантические источники.
Loopback 127.0.0.1, bounded JSON, no credentials in artifacts, offline tests.

Unsubmitted prototype `T1-T-C-work-20261121/`: channels61GREEN×2, actual package
MCP pipes/HTTP help, finite/bounded JSON, project/source external profile,
Host/Origin before dispatch, session-owned typed browser read seam, raw-content/
identity endpoint inverse. Synthetic tests: no provider/browser/socket traffic.
Eleven native server references byte-exact; seven already accepted owners stay
unchanged. Native port_guard paired-reference-only: measured orphan termination
lacks ownership and is never activated. Two new native caps exact SHA/path only;
nine own cases RED2fail/7pass→GREEN×2, four candidate gates passed. All observer
faults retained. Это не production port/independent acceptance.
Следующее действие: после B publication — corpus/own production RED, registered
ADR/D/security, integrate current frozen B source, mutants/full/gates/clients×2.
## Production step: entries/reference lane/native caps

Own four missing-entry/routing RED IDs plus native-cap9(2fail/7pass) captured before
implementation. Production28GREEN×2, actual native-auth5 corpus×2/0diff. New native
server copies exact; accepted seven refs/K1/bootstrap unchanged. Rejected first
SEC fixture missing mkdir and reference observer tuple-order mistakes retained;
both fixed only in owned tests/replay, not native behavior. ADR0085/SEC-T1-LOCAL.
Next: complete production channel cases and current-byte mutants, genuine gates/
full pairs/clients; seal LAST. Package/live/independent acceptance not yet claimed.
## Production complete selected suite

Production69 ordered GREEN×2, five native-auth cases×2/0diff, actual layers/limits/
security/contract gates exit0. Two own HTTP source-profile RED cases fixed before
token IO; no source files/credentials created. Three current production mutants
(Host gate/raw endpoint proof/native SHA gate) killed and copyfile-restored exact
bytes/SHA/LF/CRLF, same-ID GREEN. No prototype-only mutation counted.
Next: fresh complete regressions/gates+six mechanic selfchecks/client pairs;
production frozen during final verification, then truthful docs/seal LAST/ZIP.
Listener owned lifecycle: genuine two-ID RED1fail/1pass→production71GREEN×2 and
native5corpus×2/gates. Finally releases only its session gateway/facade; injected
no-gateway sessions do not touch a global browser. Current listener raw-proof and
owned-close mutants killed/exact copyfile restored/same IDs GREEN. Earlier33-line
listener mutation retained but not substituted for final38-line source evidence.
Next fresh verification bound additionally to every published B ordered ID; no
production source changes during final pair. Six mechanic selfchecks plus actual
channel clients; channels are transport, not a duplicate feature MODULE.
## Final paired evidence readback and closure

Final full8193passed+ровно два historical WinError1314 skips×2; все ordered
A/K1/published-B IDs и setup/call/teardown сохранены. Frozen230/API253/project288
каждый GREEN×2. Четыре genuine static gates×2 и шесть genuine mechanic selfchecks
×2: verdict ok/exit0; assistant.write unit43/corpus4,687Python/35artifacts,
два прежних limits warnings. Complete accepted K1 offline helper/config retained.

Настоящие MCP child pipes и native-composed in-process WSGI clients×2:
plan→denied bare apply→explicit confirm→rollback; files/directories exactly
restored, real socket/provider/browser traffic0. Four current submitted-byte
mutants (Host/SHA/raw endpoint proof/owned gateway close) killed/exact restored;
older listener mutation retained, not substituted for current source evidence.

C-saved-final-readback.json independently reads saved raw receipts/JUnit/phases/
selfchecks/clients/mutation restorations back and binds them to the unchanged
final regression inventory. Its initial duplicate receipt-key helper error is
retained; correction changed no production/test/golden/checker predicates.
Historical stage2/69/71 checkpoints above remain historical, not current status.
Следующее действие: docs-only delta verification, seal LAST/full sibling ZIP;
then T-D production structural/UI integration. Independent acceptance false;
real HTTP socket smoke/provider/browser/editor semantic apply not claimed here.
