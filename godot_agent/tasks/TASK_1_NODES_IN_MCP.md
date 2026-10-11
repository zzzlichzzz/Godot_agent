# ЗАДАНИЕ 1: узлы сцены в MCP

**Проект:** Godot Agent — плагин ИИ-ассистента для редактора Godot 4
**Корень:** `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`
**Движок:** Godot 4.6.3-stable, бинарник `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`
**Объём:** 1-2 дня

---

## 1. Проблема

Плагин даёт три канала доступа к функционалу: нейросеть в чате (браузер и API), MCP-мост для внешних агентов (Cline, Cursor) и кнопки редактора.

**Переименование, перемещение и удаление узлов сцены доступны нейросети, но НЕ доступны через MCP.** Внешний агент не может переименовать узел в сцене — при том что это ровно та задача, для которой мост и делался.

Это не архитектурное ограничение. Операции уже реализованы в чистом Python и работают без редактора. Их просто не подключили к мосту.

---

## 2. Доказательства, что работа выполнима

**Операция не требует редактора.** В `python/main.py:3053` действие применяется так:

```python
result = node_refactor.apply_prepared_node_refactor(
    project_root, prepared, *_current_chat_info(), **_access_kwargs())
```

Ни одного обращения к GDScript-исполнителям. Всё делает `python/godot_tools/node_refactor.py` разбором текста `.tscn`.

**Операция работает.** Проверено прогоном на живой сцене:

```
reference_count = 4
affected_paths  = ['res://src/refactor_lab/scenes/lab_root.tscn',
                   'res://src/refactor_lab/scripts/lab_root.gd']

сцена:   [node name="PlayerPanel" ...]  →  [node name="PlayerPanels" ...]
сцена:   parent="PlayerPanel"           →  parent="PlayerPanels"
скрипт:  = $PlayerPanel                 →  = $PlayerPanels
```

Правятся: имя узла, ссылки на него как на родителя у дочерних узлов, пути `$Node` / `%Unique` / `get_node()` в прикреплённых скриптах.

**Чего не хватает.** Мост `python/tools/agent_bridge.py` в функции `_make_prepared` (строка 1235) обрабатывает шесть видов записи:

```
repair_scene, rename_symbol, move_file,
create_file, patch_file, transaction
```

Узлов среди них нет.

---

## 3. Что сделать

### 3.1. Добавить ветки в `_make_prepared`

Файл: `python/tools/agent_bridge.py`, функция начинается на строке 1235.

Добавить три действия **по образцу существующих** `rename_symbol` (строка 1240) и `move_file` (строка 1244):

| Действие | Функция подготовки | Поля запроса |
|---|---|---|
| `rename_node` | `node_refactor.prepare_node_rename` | `scene`, `node`, `new_name` |
| `reparent_node` | `node_refactor.prepare_node_reparent` | `scene`, `node`, `new_parent` |
| `delete_node` | `node_refactor.prepare_node_deletion` | `scene`, `node` |

Сигнатуры — в самом модуле `python/godot_tools/node_refactor.py`, функции на строках 225, 500, 758.

После подготовки обязательно вызвать `_assert_prepared_access(root, prepared, policy)` — как у соседних веток.

### 3.2. Разрешить применение

Проверить, что `apply` умеет применять эти подготовленные транзакции. В `main.py:3053` для этого служит `node_refactor.apply_prepared_node_refactor`. Если в мосте своя ветка применения — добавить туда же.

### 3.3. Обновить текст отказа

В `_as_transaction` (около строки 867):

```python
raise ValueError("write request must be create_file, patch_file, move_file, or transaction")
```

Новые действия идут не через транзакции, а через отдельные ветки `_make_prepared`. Проверьте, что они до неё доходят, и обновите текст отказа, чтобы он перечислял все поддерживаемые виды.

### 3.4. MCP-инструменты

Файл: `python/tools/godot_agent_mcp.py`.

Добавить инструменты по образцу `write_preview` / `write_apply` (строки 229-245). Ожидаемые имена:

```
node_rename_preview(scene, node, new_name)
node_reparent_preview(scene, node, new_parent)
node_delete_preview(scene, node)
```

Каждый — обёртка над `write preview` с нужным `action`. **Только preview:** применение идёт общим `write_apply(plan_id)`, отдельные инструменты для apply не нужны.

В описании каждого указать: операция правит `.tscn` и прикреплённые скрипты, файлы не меняются до `write_apply`.

---
## 4. Как проверять

### 4.1. Мост запускается вручную, MCP-клиент не нужен

Главное удобство: мост — обычный CLI. Его можно вызвать из терминала и увидеть результат. Заводить Cline и прописывать конфиг **не требуется**.

Создайте файл запроса:

```powershell
cd 'D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python'
'{"action":"rename_node","scene":"res://src/refactor_lab/scenes/lab_root.tscn","node":"PlayerPanel","new_name":"ActorPanel"}' |
  Set-Content ..\req.json -Encoding utf8
```

Проверка без изменения файлов:

```powershell
python tools\agent_bridge.py --root "D:\vajno\Godot\тест-плагина-ии" write preview --request ..\req.json
```

**Ожидается:** код возврата 0, `plan_id`, диффы по `.tscn` и скрипту. Файлы на диске не меняются — проверьте глазами, что `$PlayerPanel` на месте.

### 4.2. Тестовая среда

`res://src/refactor_lab/` — полигон под проверку рефакторинга. Там специально собраны:

| Что | Где |
|---|---|
| три способа обратиться к узлу (`$PlayerPanel`, `%HealthLabel`, `get_node("Panel/Stats")`) | `scripts/lab_root.gd` |
| блок `[connection]` в сцене | `scenes/lab_root.tscn` |
| дочерний узел с `parent="PlayerPanel"` | `scenes/lab_root.tscn` |
| описание всех заданий | `src/refactor_lab/LAB.md` |

Перед экспериментами сделайте копию: `Copy-Item -Recurse src\refactor_lab src\refactor_lab_backup`.

### 4.3. Проверка целостности после применения

```powershell
$godot = 'D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe'
cd 'D:\vajno\Godot\тест-плагина-ии'
& $godot --headless --editor --quit-after 250 > chk.txt 2>&1
Select-String -Path chk.txt -Pattern 'SCRIPT ERROR|Parse Error'
Remove-Item chk.txt
```

**Пусто — всё цело.** Есть строки — операция оставила висячую ссылку.

### 4.4. Тесты проекта

```powershell
cd 'D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python'
cmd /c "python tests\test_gdscript_wiring.py > out.txt 2>&1"
Get-Content out.txt -Tail 1        # ожидается: ИТОГО: 109/109
Remove-Item out.txt

cmd /c "python tests\test_agent_bridge.py > out2.txt 2>&1"
Get-Content out2.txt -Tail 3
Remove-Item out2.txt
```

Базовая линия: **109/109** в первом. Во втором до правок тоже всё зелёное — зафиксируйте результат **до** изменений, чтобы отличать свои поломки от чужих.

**Дополнительно:** `python tests\run_integration_regressions.py` — полный прогон, 110/114. Четыре падения существовали до этой работы, они не ваши.

---

## 5. Критерии приёмки

1. `write preview` принимает `rename_node`, `reparent_node`, `delete_node` и возвращает корректные диффы.
2. Файлы не меняются до `write_apply`.
3. `write_apply` по `plan_id` применяет изменение.
4. `$PlayerPanel` в `scripts/lab_root.gd` обновляется при переименовании узла.
5. `parent="PlayerPanel"` у дочернего узла в `.tscn` обновляется.
6. Проверка 4.3 проходит без ошибок.
7. `test_gdscript_wiring.py` — 109/109.
8. `test_agent_bridge.py` дополнен случаями для трёх новых действий.
9. Ни один существующий тест не сломан.

---

## 6. Чего НЕ делать

| Нельзя | Почему |
|---|---|
| Менять `node_refactor.py` | он работает и проверен; задача — только подключение |
| Делать отдельные инструменты для apply | двухфазная запись общая, `write_apply(plan_id)` |
| Обещать в описании инструмента работу со сценами, ресурсами, настройками | они требуют редактора и в MCP недоступны — отдельная задача |
| Удалять `plugin_universal.gd` | точка отката плагина |

---

## 7. Форма отчёта

```
ЧТО СДЕЛАНО: <файлы и изменения>
ПРОВЕРКА preview: <команда и вывод, диффы>
ПРОВЕРКА apply: <команда и вывод>
ЦЕЛОСТНОСТЬ (4.3): <пусто / текст ошибок>
test_gdscript_wiring: <дословно ИТОГО: N/N>
test_agent_bridge: <было до / стало после>
НЕ ДОДЕЛАНО: <что осталось и почему>
ВРЕМЕННЫЕ ФАЙЛЫ: <что создавали, удалили ли>
```

Последний пункт обязателен: `test_gdscript_wiring.py` делает `glob` по всем `.gd` в папке аддона, и любой оставленный временный `.gd` ломает 109 проверок.

---