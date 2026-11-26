# T-F.5 — нативный вход панели (2026-11-22)

## Цель и границы

Мандат: `_start-prompt.TF5-panel-ui.md`. Только переключение `plugin.cfg`
на `editor/native/agent_entry.gd`; `plugin.gd`/`editor/t1_panel.gd` остаются.
Пустой `fixtures/.gdignore` уже добавлен аудитором до начала, сохраняется.
Нативный GDScript, все T-A…T-E/K1c/librarian/J1 и exe не редактируются.
Установленная копия и прежние sealed-досье — только чтение, без git/синхронизации.

## Старый код и судьба тестов

`editor/native/agent_entry.gd`: 24233 B, SHA256
`fea207f0296d429d372a9465c854cee3480b97da2ca5d09150357460a832f31f`.
Старый native `plugin.cfg` v0.9.1 подключал `agent_entry.gd`; устаревший
docstring frozen-файла не исправляется. `_report_entry_ready` печатает
реальный результат `_dock != null`, число интеграций и подключение сигналов.
`tests-map.md:137–140,161`: lifecycle/context menu/tool menu и транспорт —
`replaced`, живая проверка и контракты нового уровня, не копирование тестов.
Новых capabilities/ToolSpec нет: существующий editor/core меняет entry.

## Инварианты и доказательства

- Только один production diff: значение `script` в `plugin.cfg`.
- Полная исходная identity, raw bytes/SHA256/EOL, внешние резервные копии.
- WORKLOG: binary append-only CRLF, prefix 1103888 B / `bcada22bc9bc89b0`.
- Live: синтетическая копия `plugin.cfg` + `plugin.gd` + `editor/**`, внешнее
  состояние, headless editor `--quit-after 40` ×2, actual native dock print.
- Native entry/первые `agent_*` зависимости: `--check-only`; не stub/fake.
- Панель↔неизменный exe: настоящий startup/provider UI, user:// token,
  сигнал подтверждения панели → localhost `/chat/confirm_action` → WAL.
- Без внешней сети: только localhost; updater использует свежий штатный
  userdata-cache в синтетике. Токены не публикуются в досье/логе/ZIP.
- Полный predecessor 8427 IDs + свои, ×2; гейты/selfcheck ×2.
- Seal LAST; ZIP/проверка/receipt только в отдельном sibling postseal.

## Состояние и следующее действие

Этап 7 — executor checkpoint (независимая приёмка ещё не заявлена): baseline pins в
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/tf5-20261122/`.
До начала уже есть дополнительные fixture `.gd.uid` и `.pytest_cache`:
сохранены как чужая исходная работа, удаление/откат не выполняется.
Entry-контракт: настоящий RED 1fail/5pass на исходном `plugin.cfg`.
Config-only switch/D101 выполнены; native activation с реальным dock ×2 и
25 native agent_* check-only ×2 прошли. Реальные UI↔exe раунды 19/20 прошли:
OpenRouter (not configured), user:// token, кнопка/HTTPRequest confirm_action,
physical WAL COMMITTED → rollback raw bytes, owned exe shutdown/lineage 0/0.
Первый full pair: 4 failures ×2, не GREEN. D102 меняет только устаревшее T1
ожидание config при сохранённом node ID. D103 не меняет frozen C.21 tests,
fixtures/manifests/goldens: materialization исходного input revision плюс
25 новых unfiltered current-input кейсов с точными пинами 7 чужих UID.
Прямой pytest без объявленного D103 adapter сохраняет три membership RED;
финальная команда явно включает `-p tf5_corpus`, никаких skip/xfail для них.
Focused GREEN получен. Финальный регресс завершён: 8458 IDs×2,
8456passed+2historic skips каждый; все8427 predecessor IDs/order и
setup/call/teardown exact. `regression/paired-summary.json`, JUnit и raw phases.

Closure detail: дополнительный C.21 selfcheck дал corpus=ok (25/0diff), но
unit=fail из-за коллизии exclusive receipt в двух отдельных pytest-процессах
collect-count/run. RED сохранён; D103 фиксирует только PID в имени receipt,
не тесты/predicates. Полный `gate/selfcheck-closure-*` pair завершён:
4 gates×2 exit0 и 8 genuine selfcheck×2 verdict=ok. D104 выполнен: raw FSCTL/
target/identities capture → detach246 только своих junction entries; исходные
87384 ordinary files/94958 dirs exact, targets preserved, links0.

D105: read-only installed inventory выявила 181 отсутствующий fixture UID
относительно стартового снимка (причина не доказана); других file/dir/link
изменений нет. Executor туда не писал/не синхронизировал, чужое не восстановил.
Начальные пины и наблюдаемый стабильный снимок сохранены отдельно; не заявляем
installed exact к старту. Rebuild foreign UID/cache/frozen + native backup exact
подтверждены source-only inspector; финальная identity ещё после full pair.

Следующее действие: executor handoff → final identity/token scan → seal LAST
(`tf5-20261122/SHA256-final.json`) → sibling ZIP и полная проверка каждого member.
Итог публикации после seal фиксируется только снаружи:
`tf5-20261122-postseal/publication.json`; actual SHA/counts берутся оттуда,
не дописываются в sealed-досье/дерево. Затем независимый аудит D101–D105.
Installed sync/git/пересборка exe не выполняются. NN не запускалась; runtime/
editor execution, protected split Apply и automatic post-move sync остаются
unsupported по принятому T-F, включение прежнего UI не закрывает их.

### D123 — оформление рабочего дока (после переноса)

Точка возврата D122: `d32ecda` в `experiment`. Цель: компактная навигация
сверху, штатные поля и фокус, спокойные поверхности сообщений и заметные
решения о доступе. Проверить ширину узкого дока, светлую/тёмную тему и
сигналы кнопок в изолированном Godot, без подключения провайдера.

Результат: список сверху вместо центрированных больших кнопок, поле ввода и
иконки из темы редактора. Сообщения различаются подписью и фоном; вопросы
доступа — отдельной полосой и кнопками, детали действия остаются видны.
При первой проверке переписки широкая кнопка разрешения растягивала док за
250 px. Подписи сокращены; Godot 4.6.3 отрисовал главную и чат без выхода
элементов за край при 250 и 420 px в обеих темах. Сигналы навигации, выбор
и отзыв разрешений проверены. [Снимки](../../.github/dock-preview/README.md).
Следующее действие: открыть док в рабочем проекте и оценить оформление.

### D124 — второй вариант оформления

По отзыву пользователя вместо плоского списка D123 — главный экран с графикой
узлов и отдельным входом в историю. В диалоге дать больше места тексту ответа,
визуально разделить реплики, детали доступа оставить раскрытыми. Проверить
обе темы и узкий док в Godot; сохранить снимки реальных контролов.

Результат: «Мастерская проекта» с векторной схемой узлов, заметной кнопкой
истории и отдельными плитками браузера и API. Вопрос пользователя в плашке;
ответ агента использует ширину дока. В двух профилях Godot 4.6.3 проверены
ширины 250/420 px, контраст, фокус и три перехода. [Снимки](../../.github/dock-preview/README.md).
