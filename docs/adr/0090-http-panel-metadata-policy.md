# ADR-0090 — сохранённая политика панели не блокирует служебные списки

2026-11-23. Коррекция по запросу пользователя о POST 403.

## Наблюдение

`agent_panel_part1.gd::_policy_body` добавляет `allow_addons` и
`allow_self_edit` ко всем POST. В текущем внешнем user data сохранено
`godot_agent_policy.txt = 1`. ProjectAuth отвергает такой запрос ещё до
обработчика, включая списки и статус кэша. GET progress тела не имеет и проходит.
Сервер из пользовательского лога уже остановлен; живой ответ не выдаётся за
снятый. Токен не читается в отчёт и не пересоздаётся.

## Решение до кода

Только шесть точных POST-путей: `/chats/list`, `/sites/list`, `/api/providers`,
`/api/models/refresh`, `/api/models/scan`, `/project/api_cache_status`.
После проверки токена, JSON и привязки проекта ProjectAuth удаляет из тела
оба поля политики перед последующими обработчиками. Это служебные запросы,
которые не выбирают права доступа к файлам проекта. Refresh/scan сохраняют
проверку ключа, ограничение транспорта и внешнего состояния SEC-TF6.

Все остальные пути, включая `/init`, `/chat`, `/tools/call`, preview/apply,
по-прежнему отвергают попытку поднять права. Префиксы и похожие пути не
получают исключения. Host/Origin, токен, лимит, привязка проекта и WAL неизменны.
Ни GDScript, ни native reference, ни ToolSpec/контракт не меняются.

Прежний тест `test_new_panel_routes_auth_host_and_escalation_before_dispatch`
меняет только ожидание для `/project/api_cache_status`: успешное чтение вместо
403. Остальные проверки и ID сохраняются. Дополнительный тест проверяет тело,
дошедшее до обработчика: полей повышения прав в нём нет.

## Проверка

Новые regression/security cases до исправления, затем те же ID после;
полные channels_t1/panel_tf и связанные security, четыре статических гейта,
настоящий selfcheck и probe. Офлайн пересборка установленным PyInstaller и
изолированный реальный socket smoke; без ключей/провайдеров и чужих процессов.
Пользовательский токен и настройки не меняются. Отдельно разрешённая пользователем
резервная копия старого endpoint описана ниже. Общая приёмка T-F.6 не заявляется.

## Найденное при регрессии: владение endpoint

Связанные suites выявили отдельный настоящий RED:
`test_preexisting_claim_is_not_adopted_or_removed` (302 passed / 1 failed).
Listener до исправления удалял существующий endpoint по guessed PID или ошибке JSON,
в обход SEC-T1-LOCAL-04. Это дефект уже принятого правила, не новое решение:
восстановить эксклюзивное создание и отказ при чужом файле. Не убивать процессы,
не удалять существующий endpoint пользователя. Новые четыре security cases
проверяют malformed/missing/zero/dead PID и закрытие собственного socket при отказе.

## Измеренные результаты

- Metadata cases: genuine RED30fail/9pass → same-ID GREEN39pass.
- Endpoint security: genuine RED4fail → восстановлен exclusive create;
  связанные channels/panel/security suites307passed.
- Security/layers/limits/contract: четыре exit0; два прежних limits warnings.
- Genuine selfcheck `assistant.write`: verdict=ok, unit43passed/corpus4;
  только REPORTS перенесён во внешний temp, запечатанные repo reports не тронуты.
  Read-only CLI probe на изолированном project.godot: ok.
- Offline PyInstaller6.21.0 rebuild: `python/dist/godot_agent_server.exe`,
  SHA256 `a5e8a4206b0d3b644fa6346c131c1ea399cafb1f15d1d8a69326c4f959deadf0`.
  Старый exe сохранён во внешнем `http403-exe-backup-20261123/`.
- Реальные socket source/explicit-exe/zeroarg-exe: все шесть POST200, GET progress200;
  no_key остаётся denied без provider traffic; invalid token/Host/Origin403,
  foreign project409, policy-sensitive POST403. Второй запуск не трогает endpoint;
  owned shutdown exit0/endpoint removed, project/token/policy exact.
  Zeroarg в копии изолированного проекта, APPDATA external, port5000;
  живой Godot UI и пользовательский сервер не запускались.
- Первый socket helper ошибся путём `/shutdown`; сохранён fail/logs, исправлен
  только helper на существующий `/server/shutdown`, затем три цикла GREEN.

С разрешения пользователя и после отсутствия процесса/listener endpoint
PID18332/session2ab852d3fab4478ca5d6ea8bc4303de9 переименован в том же external
userdata в `http_endpoint.stale-18332-20261123.json`; original bytes сохранены,
токен/настройки нетронуты. Это ручная recovery-операция, не правило auto-cleanup.
Все временные проверки/логи — во внешнем `%TEMP%/opencode/http403-*`.
