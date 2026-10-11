# ЗАДАНИЕ 2: чтение и разведка в MCP

**Проект:** Godot Agent — плагин ИИ-ассистента для редактора Godot 4
**Корень:** `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`
**Движок:** Godot 4.6.3-stable
**Объём:** 1 день
**Совместимость:** задание 1 правит тот же `agent_bridge.py` — делайте **по очереди**, не параллельно

---

## 1. Проблема

Плагин даёт три канала доступа: нейросеть в чате, MCP-мост для внешних агентов, кнопки редактора.

**У нейросети есть разведка перед правкой, у MCP — нет.** Модель может прочитать только нужные функции, посмотреть структуру сцены, найти все использования символа и получить предпросмотр переименования до применения. Внешний агент в Cline этого не может — ему приходится читать файлы целиком и угадывать.

Это **не** архитектурное ограничение. Все четыре операции реализованы готовыми функциями в модулях и работают без редактора.

---

## 2. Что отсутствует и где лежит логика

| Возможность | Функция | Файл:строка |
|---|---|---|
| структура сцены (дерево узлов, скрипты, связи) | `describe_scene` | `python/godot_tools/project_tools.py:1010` |
| чтение только нужных функций из `.gd` | `read_project_file` + `list_functions` + `extract_functions` | `project_tools.py:541`, `python/godot_tools/gd_functions.py:20` и `:30` |
| поиск использований символа | `find_references` | `python/godot_tools/symbol_refactor.py:1309` |
| предпросмотр переименования | `analyze_rename` | `python/godot_tools/symbol_refactor.py:1412` |

**Почему задача дешёвая.** Оркестрация в `main.py` эти функции только вызывает и форматирует вывод (`main.py:1142`, `main.py:1297`, `main.py:3345`). Вынос в модули не нужен — мост вызывает те же функции напрямую.

Редактор не требуется: все четыре — чистый Python, разбор текста `.gd` и `.tscn`.

---

## 3. Что сделать

### 3.1. Команды моста

Файл: `python/tools/agent_bridge.py`.

Добавить в словарь `_COMMANDS` (строка 1579) четыре команды по образцу `cmd_read` (строка 354) и `cmd_ask` (строка 445):

| Команда | Что делает | Возвращает |
|---|---|---|
| `scene` | структура сцены | дерево узлов с типами, скрипты, инстансы, связи |
| `functions` | функции из `.gd` | список имён или тела запрошенных |
| `usages` | использования символа | `файл:строка:колонка`, тип связи, уверенность |
| `analyze_rename` | предпросмотр переименования | что и где изменится, риски |

Все четыре — **read-only**, ничего не пишут на диск.

Обновите строку `_USAGE` (строка 1593), чтобы новые команды попали в подсказку.

### 3.2. MCP-инструменты

Файл: `python/tools/godot_agent_mcp.py`.

Добавить четыре инструмента по образцу `read` и `ask` (строки 193-201):

```
scene(path)                                             — структура .tscn
functions(path, names)                                  — функции из .gd, пустой names даёт список всех
usages(declaration, name)                               — где используется символ
analyze_rename(kind, declaration, old_name, new_name)   — предпросмотр
```

## 4. Как проверять

### 4.1. Мост вызывается из терминала — MCP-клиент не нужен

```powershell
cd 'D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python'

# структура сцены
python tools\agent_bridge.py --root "D:\vajno\Godot\тест-плагина-ии" scene --path "res://src/refactor_lab/scenes/lab_root.tscn"

# список функций файла
python tools\agent_bridge.py --root "D:\vajno\Godot\тест-плагина-ии" functions --path "res://src/refactor_lab/scripts/lab_entity.gd"

# где используется символ
python tools\agent_bridge.py --root "D:\vajno\Godot\тест-плагина-ии" usages --declaration "res://src/refactor_lab/scripts/lab_entity.gd:35" --name "take_damage"

# предпросмотр переименования
python tools\agent_bridge.py --root "D:\vajno\Godot\тест-плагина-ии" analyze_rename --kind function --declaration "res://src/refactor_lab/scripts/lab_entity.gd:35" --old-name "take_damage" --new-name "apply_damage"
```

**Точные имена флагов уточните** по тому, как устроен разбор аргументов у существующих команд. Пример выше показывает смысл, а не буквальный синтаксис.

**Ожидается:** код возврата 0 и осмысленный вывод. Для `usages` — что `take_damage` находится в трёх файлах:

| Файл:строка | Что там |
|---|---|
| `lab_entity.gd:35` | объявление |
| `lab_turret.gd:38` | `super.take_damage` — уверенность `probable`, тип ресивера не доказан |
| `lab_turret.gd:56` | self-вызов — уверенность `proven` |
| `lab_root.gd:76-77` | **имя метода строкой** — `dynamic`, и это место должно попасть в отчёт с пометкой |

Объявление override в `lab_turret.gd:37` в список не входит — движок переименования обрабатывает override отдельно от ссылок.

### 4.2. Тестовая среда

`res://src/refactor_lab/` — полигон рефакторинга. Для этой задачи полезны:

- `scripts/lab_entity.gd` — базовый класс, методы `take_damage`, `heal`, `describe`, `reset_state`;
- `scripts/lab_turret.gd` — наследник с `super.take_damage` и `Array[LabEntity]`;
- `scenes/lab_root.tscn` — 9 узлов, 2 инстанса, блоки `[connection]`.

Подробности — в `src/refactor_lab/LAB.md`.

### 4.3. Проверка, что ничего не изменено

```powershell
cd 'D:\vajno\Godot\тест-плагина-ии'
Copy-Item -Recurse src\refactor_lab src\refactor_lab_check
# файлы должны совпадать побайтово
Get-ChildItem src\refactor_lab -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Replace((Get-Location).Path + '\src\refactor_lab\', '')
  $other = Join-Path 'src\refactor_lab_check' $rel
  if ((Get-FileHash $_.FullName).Hash -ne (Get-FileHash $other).Hash) { "ИЗМЕНЁН: $rel" }
}
Remove-Item -Recurse -Force src\refactor_lab_check
```

Read-only команды не должны менять ни одного файла. Пустой вывод — правильно.

### 4.4. Тесты проекта

```powershell
cd 'D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python'
cmd /c "python tests\test_agent_bridge.py > out.txt 2>&1"
Get-Content out.txt -Tail 3
Remove-Item out.txt

cmd /c "python tests\test_gdscript_wiring.py > out2.txt 2>&1"
Get-Content out2.txt -Tail 1        # ожидается: ИТОГО: 109/109
Remove-Item out2.txt
```

Зафиксируйте `test_agent_bridge.py` **до** правок, чтобы отличать свои поломки от чужих.

**Полный прогон:** `python tests\run_integration_regressions.py` → 110/114. Четыре падения существуют до этой работы, они не ваши.

---

## 5. Критерии приёмки

1. Четыре команды моста работают и вызываются из терминала.
2. Четыре MCP-инструмента объявлены с понятными описаниями.
3. Все четыре **не меняют** файлы — проверено по 4.3.
4. `usages` на `take_damage` в лаборатории находит места в трёх файлах.
5. `scene` на `lab_root.tscn` показывает 9 узлов и связи из `[connection]`.
6. Политика `allow_addons` соблюдается.
7. `test_gdscript_wiring.py` — 109/109.
8. `test_agent_bridge.py` дополнен случаями.
9. Ни один существующий тест не сломан.

---

## 6. Чего НЕ делать

| Нельзя | Почему |
|---|---|
| Выносить что-либо из `main.py` | функции уже в модулях, вынос не нужен |
| Менять `symbol_refactor.py`, `project_tools.py`, `gd_functions.py` | они работают; задача — вызвать их из моста |
| Добавлять команды, которые пишут на диск | запись уже есть: `write preview` / `write apply` |
| Обещать операции со сценами и ресурсами | они требуют редактора, это отдельная тема |

---

## 7. Форма отчёта

```
ЧТО СДЕЛАНО: <файлы и изменения>
ПРОВЕРКА scene: <команда и вывод>
ПРОВЕРКА functions: <команда и вывод>
ПРОВЕРКА usages: <команда и вывод, сколько мест найдено>
ПРОВЕРКА analyze_rename: <команда и вывод>
ФАЙЛЫ НЕ ИЗМЕНЕНЫ (4.3): <пусто / список изменённых>
test_gdscript_wiring: <дословно ИТОГО: N/N>
test_agent_bridge: <было до / стало после>
НЕ ДОДЕЛАНО: <что осталось и почему>
ВРЕМЕННЫЕ ФАЙЛЫ: <что создавали, удалили ли>
```

Оставленный временный `.gd` в папке аддона ломает 109 проверок — убирайте за собой.

---
В описании каждого указать: **операция только читает**, подтверждения не требует.

### 3.3. Учесть политику доступа

Все четыре читают файлы проекта, поэтому должны уважать `allow_addons` — как это делает `cmd_read`. Посмотрите его устройство и повторите.

---