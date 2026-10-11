# Отчёт канала «Редактор»: перехват переименования ВНУКА корня

**Статус:** канал в scope (решение зафиксировано: вариант 1 — отчёт приложен, из свода канал НЕ убран).
**Предмет:** перехват ручного переименования узла — внука корня сцены — и повторного
переименования при scripts_only (сцена на диске не перезаписывается).

---

## 1. Что было сломано (факт, не предположение)

Сцена-макет: `[node name="PlayerPanel"]` → `[node name="StatsLabel" parent="PlayerPanel"]` →
`[node name="Inner" parent="PlayerPanel/StatsLabel"]`; скрипт: `$PlayerPanel/StatsLabel`,
`%StatsLabel`, `get_node("PlayerPanel/StatsLabel/Inner")`.

Воспроизведение через настоящие маршруты Flask (`main.app.test_client()`); панель шлёт
ровно то, что собрал бы `_node_rename_body`:

| Сценарий | Тело запроса | Ответ сервера |
|---|---|---|
| №1 предок: `PlayerPanel` -> `ActorPanel` | `node_path="PlayerPanel"`, `previous_name="PlayerPanel"` | preview HTTP **200**, file_count=1, refs=3 |
| №2 внук после №1, путь РЕДАКТОРА | `node_path="ActorPanel/StatsLabel"` | preview HTTP **400**: «Узел 'ActorPanel/StatsLabel' не найден в сцене» |
| №2 внук, путь ДИСКА (найденный вручную) | `node_path="PlayerPanel/StatsLabel"` | preview HTTP **200**, но file_count=**0**, refs=0 |

Причина: scripts_only сцену не трогает, а панель запоминала в `_node_disk_names` только
ТОЧНЫЕ пары «путь редактора → путь диска». Для внука точного ключа нет — в истории лежал
лишь предок (`ActorPanel` → `PlayerPanel`): путь внука на диске не находился, узел в
редакторе переименовывался, а ссылки в скрипте оставались старыми — молча.

---

## 2. Фикс

`addons/Godot_agent/godot_agent/agent_panel.gd`, `_node_disk_path_for_sync` (строки 5079-5110):
если точного ключа нет — берётся САМЫЙ ДЛИННЫЙ предок-префикс из истории и в него переносится
остаток пути (`ActorPanel/HpLabel` → `PlayerPanel/HpLabel`); результат проверяется по
фактическому тексту .tscn (`_scene_has_node_path`) и без узла не отдаётся.
Функция общая для preview и apply; их тела по-прежнему собирает один `_node_rename_body`
(agent_panel.gd:5025-5042) — расхождению фаз взяться неоткуда.

Журнал правки: `write_apply` plan_id `826d411729e91fe09ee1d292`, entry_id `dd614bd3cb2b`.
Статический тест на регресс: `test_node_rename_intercept.py` («путь внука переводится
через предка: редактор → диск»), plan_id `2848aa02da99700de9d1a87b`, entry_id `d632545bc591`.

---

## 3. Сверка точек перехвата (file:line на момент отчёта)

| Точка | Файл:строки | Что подтверждает |
|---|---|---|
| снимок имён при смене сцены | `agent_integration_signals.gd:105-111` | `_clear_node_watch()` + `_watch_subtree(root)` |
| рекурсивный обход поддерева | `agent_integration_signals.gd:117-121` | внук корня подписан, а не только прямые дети |
| подписка на `child_entered_tree` | `agent_integration_signals.gd:145-146` + обработчик `:170-174` | узел, добавленный позже, тоже наблюдаем |
| путь узла редактора → путь диска | `agent_panel.gd:5079-5110` | внук предка переводится через префикс |
| запоминание пары после успеха | `agent_panel.gd:5115-5120`, вызов `:5290` | карта `_node_disk_names` |
| тело запроса (общее для фаз) | `agent_panel.gd:5025-5042` | `node_path` = disk_path, `previous_name`, `scripts_only: true` |
| вторая фаза (apply) | `agent_panel.gd:5250` | тот же `_node_rename_body(_node_sync_ctx)` |
| сцена НЕ перезагружается | `agent_panel.gd:5273-5278` | обновляются только скрипты |
| сообщение об успехе | `agent_panel.gd:5279` + ключ `agent_locale.gd:464` (ru) / `:910` (en) | текст `node_rename_intercept_success` |
| отказ apply без preview | `python/main.py:4355-4366` | HTTP 409 |
| путь узла в редакторе | `agent_integration_signals.gd:194-196` | `root.get_path_to(node)` + подстановка ПРЕЖНЕГО листа |

---

## 4. Команды, коды возврата и результат

Все запуски — из каталога `addons/Godot_agent`.

| Команда | rc | Фактический вывод |
|---|---|---|
| `python -B godot_agent/python/tests/test_node_rename_intercept.py` | **0** | СТАТИКА: 39 проверок, 0 провалов |
| `python -B godot_agent/python/tests/test_node_refactor_flow.py` | **0** | Ran 7 tests in 0.521s — OK |
| `python -B godot_agent/python/tests/test_panel_short_channel.py` | **0** | СТАТИКА: 15 проверок, 0 провалов |
| `check` для `agent_panel.gd`, `agent_integration_signals.gd` | headless **passed** | gd_lint/gd_api_check чисто, checked 2/2 |

Живой кейс F через маршруты сервера (проект-макет, реальное содержимое
`src/refactor_lab`, узел `ActorPanel/HpLabel` — внук корня):

```
POST /scene/refactor/node/preview  rc(HTTP)=200  file_count=1  refs=2  scripts_only=True
      affected_paths=["res://.../scripts/lab_root.gd"]
POST /scene/refactor/node/apply    rc(HTTP)=200  changed=["res://.../scripts/lab_root.gd"]
      entry_id=f3a5e8f1162d
POST /scene/refactor/node/apply без preview -> rc(HTTP)=409
```

Проверки результата кейса F:

* `%HpLabel` → `%HpLabelX` в `lab_root.gd` — да (рабочая строка 25).
* `$ActorPanel` и `get_node("Panel/Numbers")` не затронуты — да (переименован именно внук).
* `.tscn` на диске байт-в-байт НЕ изменён (`read_bytes()` до/после равны) — да.
* уведомление пользователю — ключ `node_rename_intercept_success` есть и в ru, и в en.
* `node_path` известен РЕДАКТОРУ (`ActorPanel/HpLabel`), а не выдуман: панель считает его из
  `root.get_path_to(node)` (`agent_integration_signals.gd:194`), `previous_name` — из снимка имён.

---

## 5. Что осталось за границей этой проверки

Живой редактор (F2 в дереве сцены, реальный сигнал `Node.renamed`) в этом прогоне не
участвовал: проверены серверная логика, тело запроса и статика подписок. Итоговое слово — за
прогоном `python -B godot_agent/python/tests/test_remaining_work_steps.py --godot`
с запущенным Godot (команда человека: запустить редактор и прожать F2).

---

## 6. Сверка идентификаторов журнала, координат и постановки

### 6.1. Записи журнала (проверено по `user://agent_history/journal.json`)

| entry_id | plan_id | Файл | after_hash == sha256 на диске |
|---|---|---|---|
| `dd614bd3cb2b` | `826d411729e91fe09ee1d292` | `agent_panel.gd` | да |
| `d632545bc591` | `2848aa02da99700de9d1a87b` | `python/tests/test_node_rename_intercept.py` | да |
| `d009712aa84d` | `91c0962b2bdb705ad33d35f4` | этот отчёт | да |

Снято как неверное: `plan_id c1c947e7474d98926f8a3dac` (фигурировал в своде как id правки отчёта).
В журнале проекта (50 записей, `chat_id`: mcp-alpha) такого id нет; 16 hex-символов — формат `plan_id`,
а не 12-символьного `entry_id`. Пара отчёта — `91c0962b2bdb705ad33d35f4` / `d009712aa84d`.

### 6.2. Актуальные координаты вставок

Таблица раздела 3 снята на момент отчёта; после последующих вставок координаты сдвинулись.
Актуальные (grep по `agent_panel.gd`, 5513 строк): `_node_rename_body` :5025, `_send_node_rename_sync` :5045,
`_node_disk_path_for_sync` :5079-5110, `_note_node_disk_name` :5115, `_scene_node_paths` :5125,
`_tscn_attr` :5155, `_scene_has_node_path` :5167, `_scene_node_name_count` :5176, `_node_path_with_leaf` :5187, `_on_node_rename_sync_response` :5221.
sha256 `fc747d98d834ac3e9f19d6a28aaf2c4998792b7c4076c2dfda811b4e1d1045a` (7864 байта) — состояние файла на момент записи в журнал (`d009712aa84d`), то есть до добавления этого раздела; после него файл длиннее.

### 6.3. Постановка (преемственность)

Основание работы — `tasks/TASK_3_NODE_RENAME_INTERCEPT.md` (разделы 4.1-4.4 и проверка 5.2)
и `THREE_CHANNEL_AUDIT.md` § 5 «ЗАДАЧА 3. Перехват переименования узлов человеком».
Переход от раннего раунда (каналы без входных данных) к текущему — новое задание, выданное через шину каналов.

### 6.4. Решение по лимитам петель

Лимит этапа — **3 итерации** (`cycle_limit`) для всех четырёх каналов: `store.cycle_ch.<канал>`,
`cycle_limit: n >= 3` (`n8n/schemas/template_v2_core_4_channels.json:1494,1507,1520,1533`; узел :1536).
`attempt_limit` (порог 4 в шаге «Причина», :1960/3413/3588/3763) — служебный счётчик заходов, а не лимит этапа:
«Продолжать этап?» требует `nothing_to_do = NO` И `attempt_limit = NO`. Пункт «лимит петель» из «осталось» снимается.
