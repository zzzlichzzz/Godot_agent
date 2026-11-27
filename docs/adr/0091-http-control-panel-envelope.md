# ADR-0091 — полная обёртка служебных запросов панели

2026-11-23. Продолжение исправления сервера по пользовательскому логу.

## Дефект и решение до кода

ADR-0090 исправил только шесть путей и проверял неполную обёртку: без addon_dir.
Пользовательский /api/settings/set всё ещё403; /chats/list теперь500.
Native _policy_body передаёт пять полей политики всем служебным POST, включая
каталог, настройку ключа и управление перепиской. Native discovery рассчитан
на старое расположение server_state/onedir exe; diagnostic addon_dir вызывает
SessionContextError. API-ключ не имеет отношения к разрешению редактировать addons.

Одна точная таблица project-policy-neutral POST: /sites/list, /api/providers,
/api/settings/set, /api/models/refresh, /api/models/scan, /api/test,
/browser/status, /chats/list, /chats/new, /chats/open, /chats/model,
/chats/rename, /chats/delete, /project/api_cache_status.
После auth/Host/Origin/JSON/лимита и project/userdata binding удалить пять полей:
allow_addons, allow_self_edit, addon_dir, rename_mode, rename_unverified.
Они не изменяют project policy ни здесь, ни в последующем native scope.
Это не read-only исключение: settings/chat mutations сохраняют существующие
эффекты внешнего состояния; browser/API transport остаётся прежним, без нового
вызова/обхода no_key или расширения stealth. Не использовать префиксные маски.

Перед native dispatch проверять обычность api_config и ожидаемых файлов/temporary
targets через ExternalPanelState: секреты только в привязанном внешнем userdata,
нет symlink/reparse/hardlink обхода. Native API/чат reference bytes, GDScript,
ToolSpec/контракт, Agent/PathPolicy и write funnel не изменяются.
Все остальные пути, включая init/chat/tools/preview/apply, сохраняют запрет
HTTP elevation; addon_dir не выбирает серверный корень. ADR-0090 историчен,
его шесть путей — подмножество этой таблицы, его результаты не подменяются.

## Проверка и границы

Новые реальные composition tests с полной native envelope и synthetic keys:
save/add/list/reload, существующий chat list, весь API-chat lifecycle offline.
Security: точная таблица/removal-before-dispatch, чужие проекты/токены/origin,
project-sensitive denial, linked config/temp refusal, no raw key response.
Genuine RED до кода → same IDs GREEN, связанные suites, actual selfcheck/probe,
гейты, offline exe rebuild и source/exe sockets в изолированных проектах.
Не читать/выводить пользовательские ключи/переписку, не менять их файлы;
не останавливать PID26668 и не заменять занятый exe без отдельного разрешения.
Новая общая приёмка T-F.6 не заявляется.

## Дополнение: завершение native-запроса

Офлайн-последовательность `settings/set → chats/new → list → rename → open → model → delete`
обнаружила ещё один дефект композиции: после успешного `new` следующий `rename`
получает 409, потому что runtime не вызывает уже существующий native
`clear_request_activity`. Native-файлы не меняются: runtime вызывает этот
thread-owned cleanup при выходе из своего scope, включая ошибки. Чужое
exchange/navigation не освобождается. До правки получен RED lifecycle (1 failed);
добавлены проверки cleanup после отказа/исключения и сохранения чужого exchange.

## Измеренный результат

RED32fail/14pass→GREEN46; navigation RED3fail/1pass→own50pass; final related357pass.
Гейты4/selfcheck assistant.write (unit43/corpus4)/read-probe ok. Final offline
staged rebuild и source/exe/isolated-zeroarg sockets GREEN: полный envelope,
synthetic save/add/masking/persistence и API-chat lifecycle без provider requests.
Configured api/test/refresh не вызывались. Final exe установлен с сохранением
предыдущего; SHA256 26de3c038b13f5b44f401df67b3c7110a0f520ee1cfd74b3089f2f87b0165334.
User server не запускали, UI/live provider и общая T-F.6 приёмка не заявлены;
предыдущий расширенный tests/py имеет6fail и не объявляется GREEN.
Единственное изменение external user data — отдельно разрешённое переименование
endpoint уже завершённого PID26668 в same-folder backup с exact bytes;
токен/политика/ключи/переписка не изменялись. Автоматического stale cleanup нет.
