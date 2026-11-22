# Задача: фаза B.2 — оживить `editing.scene_ops` в настоящем редакторе

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Часть B сдана как **этап 5**
(не 6): код и фейк-сценарии приняты, но **живой `editor_scene_plan`/`editor_scene_apply`
не работал ни разу**. Аудит нашёл причину и подтвердил её движком — это первый шаг.

## 0. Факты на старте (замер аудита 2026-10-28, сессия 40)

```
python -B -m pytest python/modules tests/py --ignore=tests/py/live -q   # exit 0
python -B -m pytest ... --collect-only -q                              # 449
python -B -m pytest tests/py/live -q                                   # 2 passed (4.6.3)
python tools/gen_contract.py --check        # ok, артефактов 9, verbs_version = 2
python tools/snapshot_diff.py               # 102/0
python tools/selfcheck.py editing.scene_ops # ok (unit 25, corpus «корпус live»)
```
Движок: `D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe`
(`4.6.3.stable.official.7d41c59c4`). Файлов 909, `__pycache__` 0.
Хеши-опоры: `contract/editor_verbs.json` `EAFF6D5FD17A`, `python/kernel/schema.py`
`629FCE54E6FE`, `editor/bridge/verbs/scene/scene_verbs.gd` `60B98CCA9666` — **не трогать**.

**Доказательство D-1 (моё, не по отчёту):**
```
godot --headless --path D:\vajno\Godot\agent-rebuild --check-only \
      -s res://addons/godot_agent/editor/bridge/verbs/scene/scene_executor.gd
→ SCRIPT ERROR: Parse Error: Cannot get return value of call to "commit_action()"
  because it returns "void".
```
Отсюда: `scene_executor.gd` **не компилируется**, каскад `Failed to compile depended
scripts` валит `scene_verbs.gd` → `endpoints.gd` → `socket_server.gd` → `lifecycle.gd`
→ `plugin.gd`, и мост живым клиентом отвечает `engine_down/truncated`.

## 1. Что сделать

**1.1 Скомпилировать `scene_executor.gd` (D-1).** Две ошибки, обе в сданном файле:

| Строка | Сейчас | Почему падает |
|---|---|---|
| `scene_executor.gd:101` | `if not undo.commit_action():` | у `EditorInterface.get_editor_undo_redo()` (класс `EditorUndoRedoManager`) `commit_action()` возвращает **void**, а не `bool` |
| `scene_executor.gd:177` | `var keys := value.keys()` | `value` — нетипизированный `Variant`, вывод типа из `keys()` невозможен |

Правка минимальная, без смены поведения: убрать использование возврата
`commit_action()` (если признака отказа у `EditorUndoRedoManager` нет — отказ `apply`
остаётся на `abort_undo`), и типизировать `var keys: Array = value.keys()`.
**Не переписывать** `scene_executor.gd` целиком, не менять операции и undo-политику.

**1.2 Сделать `_scan` в `editor/harness/bridge_probe.gd` честным (D-2).** Сейчас
скрипт с parse-ошибкой грузится (`load(...) != null`), поэтому `scripts.broken == []`
**врал**. Битым считать скрипт, у которого `can_instantiate() == false` или `load()`
вернул `null`; проверить подложкой: временно внести parse-ошибку в любой `.gd` под
`editor/`, показать `broken` непустым и красный живой тест, затем восстановить файл
побайтово и показать `broken == []`.

**1.3 Доказать живой `plan → apply → undo`.** В `tests/py/live/test_editor_branch_live.py`
добавить сценарий на временной сцене (файл `res://zz_scene_ops_probe.tscn`, удаляемый
в `finally`; никаких `zz_*` после прогона):

1. `editor_scene_plan` (одна операция `set_property` на существующем узле) → `ok`,
   `plan_digest` есть, `would_change` непуст, `revision` сцены **не изменился**;
2. `editor_scene_apply` с этим `plan_digest` и `expected_revision` → `ok`,
   `applied_revision` > `revision`, свойство действительно изменилось (видно через
   `editor_state`/`editor_selection` или повторный `plan`);
3. `undo` → значение вернулось, `revision` вырос, повторный `apply` того же плана →
   `stale_plan`;
4. сбой на второй операции (несуществующий узел) → типизированный отказ, сцена
   **не изменилась** (сверка `revision` и `dirty` до/после).

**1.4 Не трогать:** контракт `editor_scene_plan`/`editor_scene_apply` (`verbs_version`
остаётся 2), `contract/**`, `python/kernel/schema.py`, `tools/gen_contract.py`,
`tools/lint_arch.py`, `python/modules/editing/scene_ops/domain/core.py`,
`corpus="live"` у `scene_ops` (решение фазы B.1 принято).

## 2. Стоп-условия

- Ничего не писать в сцену вне `undo`-батча; `ResourceSaver` нет; `expected_revision`
  обязателен; второй сокет/HTTP не поднимать.
- **Старый плагин — только чтение** (`python -B`), два чужих лога
  (`python/_ref2.log`, `python/godot_tools/_excl.log`) не удалять, новых дампов не
  создавать (временное — в `$env:TEMP`).
- Не поднимать этап механики самому и не подменять вердикт `selfcheck`
  (`corpus` для `scene_ops` = `live`, он и должен быть `ok`).
- Не править `tools/*`; если правка инструмента всё же нужна — только с тестом и
  мутацией (R-22) и с записью в `PROGRESS.md → Долги`.
- Мутации и подложки — **строго последовательно**, бэкап `shutil.copyfile`, sha256
  до/после, `restored identical: True` в отчёте.

## 3. Чем доказывается

| Что | Команда |
|---|---|
| компиляция моста | `--check-only -s scene_executor.gd` → exit 0, без `Parse Error` |
| живой срез | `python -B -m pytest tests/py/live -v` → **3+ passed** |
| регресс | `pytest python/modules tests/py --ignore=tests/py/live` = сумма `--collect-only` (449 + новые) |
| контракт | `gen_contract --check` ok (9), `verbs_version = 2`, `snapshot_diff` 102/0 |
| вердикты | `selfcheck editing.scene_ops` ok, `context.editor_context` ok, `blocked` нет |
| гигиена | `__pycache__` 0 (запускай с `PYTHONDONTWRITEBYTECODE=1` — одного `-B` для `pytest` **не хватает**, проверено), `.pytest_cache` 0, `*.bak/tmp/orig` 0, `zz_*.tscn` нет |

Мутации (на сдаваемом файле): снять сверку `expected_revision` в executor → живой
plan/apply краснеет; применить батч без `create_action` → краснеет «после сбоя сцена
не изменилась»; вернуть `load(...) != null` в `_scan` → подложка с parse-ошибкой снова
не видна (тест на D-2 это ловит).

## 4. Записи

Лист `docs/porting/editing.scene_ops.md` (Ход работы, Блокеры: D-1/D-2), `docs/PROGRESS.md`
(этап по факту: `ok` + живой apply = 6; `ported` ставит аудитор), `docs/WORKLOG.md`
(сессия). Шапки `_start-prompt.*`, `README.md`, `_audit-handoff.md` — правит аудитор.

## 5. Что проверит аудитор

`--check-only` по `scene_executor.gd` (сейчас падает — должен стать чистым),
`pytest tests/py/live -v` (3+ passed), числа = `--collect-only`, `gen_contract` 9,
`snapshot_diff` 102/0, `selfcheck` двух механик `ok`, свои подложки (parse-ошибка в
`.gd` → `broken` непуст; чужой `plan_digest` → `stale_plan`; сбой на второй операции →
сцена не изменилась), побайтовое восстановление (sha256), `__pycache__` 0 и старая
папка с теми же двумя `??`.

