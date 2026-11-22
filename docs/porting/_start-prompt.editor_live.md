# Задача: фаза B.0 — мост внутри настоящего редактора (без записи в сцену)

> **Выполнено, аудит принял 2026-10-28 (сессия 36).** Мост поднимается плагином
> (`plugin.gd` — `@tool`, `editor/core/lifecycle.gd`, `[editor_plugins]` в
> `project.godot`); живой тест `tests/py/live/test_editor_branch_live.py` зелёный на
> 4.6.3 (`pytest tests/py/live -v` → 2 passed, ~12 с): `editor_available is True`,
> `open_scenes == 1`, `active_scene` непуст, `validate(...) == []`, `port.json`
> удалён после выхода. Мутации M1 (`has_editor → false`), M2 (`→ true`) и M3
> (без удаления `port.json`) краснят тест — проверка не пустая.
> Не доказано: выделение с непустыми `properties`, GUI-режим (только `--headless`).

**Статус:** часть A принята (`ported`), провод моста доказан живым прогоном на 4.6.3
(`pytest tests/py/live -v` → 1 passed; соло `-s` даёт `ok:false`, `reason="no_client"` —
это норма). Остался единственный долг: **редакторская ветка не проверена** — в `-s`-режиме
`Engine.is_editor_hint() = false`, `EditorInterface` — заглушка. Часть B (запись в сцену,
`_start-prompt.scene_ops_b.md`) без этого среза не принимается: писать в сцену, которую
нельзя открыть, нечем проверять.

## 0. База (замер аудита 2026-10-28)

```
python -m pytest python/modules tests/py            # 418 passed == --collect-only, 40 файлов
python -m pytest tests/py/live -v                   # 1 passed (движок 4.6.3)
python tools/snapshot_diff.py                       # 102/0
python tools/gen_contract.py --check                # ok, артефактов 8, verbs_version 1
python tools/selfcheck.py context.editor_context    # ok (unit 27)
```

Файлов — **901**, `__pycache__` 0. Незыблемое: `contract/editor_verbs.json` `F73AB2D8…B1E4`
(6747 Б, `verbs_version: 1`), `python/kernel/schema.py` `629FCE54…4067` (147 строк, CRLF),
`editor/harness/bridge_probe.gd` `2C17211A…D4D7`. Движок:
`D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe` (4.6.3).

## 1. Что сделать

**1.1 Поднять мост из плагина.** `editor/plugin.gd` сейчас `extends EditorPlugin` + TODO;
`editor/core/lifecycle.gd` не подключён. Нужно: `_enter_tree()` → старт моста
(`bridge/server/socket_server.gd`), запись `user://godot_agent/port.json`
(`port`, `token`, `pid`, `protocol`, `verbs_version`); `_exit_tree()` → `stop()` и удаление
`port.json`. Один экземпляр: повторный вход не поднимает второй сервер, адрес только
`127.0.0.1`, порт случайный, токен в каждом кадре (SEC-03 — без изменений).

**1.2 Живой тест редакторской ветки.** Новый `tests/py/live/test_editor_branch_live.py`
(маркер `needs_live`, по образцу `test_bridge_live.py`): запуск
`godot --headless --editor --path D:\vajno\Godot\agent-rebuild`, чтение
`user://godot_agent/port.json`, клиент `EditorClient`, затем проверки:

- `editor_ping`: `editor_available is True`, `open_scenes >= 0`, `godot` начинается с `"4."`;
- `editor_state`: `open_scenes` — список, `project_hash` — непустая строка,
  `active_scene` либо `None`, либо строка; снимок совпадает с `EditorInterface.get_open_scenes()`
  по количеству (0 при пустом редакторе — это норма, не пропуск теста);
- `editor_selection`: форма `{node_path, scene, script, properties}` валидна при пустом выделении;
- обе схемы проходят `verbs_catalog.result_schema` без проблем (`validate(...) == []`);
- после `terminate` — `port.json` удалён (или перезаписан следующим запуском — зафиксировать, что).

Процесс редактора гасить по таймауту (`--quit-after` или `terminate`), тест не должен
висеть: общий лимит ≤ 90 с.

**1.3 Мутации (R-22, строго последовательно, байтовый бэкап, `sha256` до/после):**

- M1 `has_editor()` → `return false` в `context_snapshot.gd`: **новый** тест обязан
  краснеть (сейчас, при `-s`-тесте, он зелёный — это и была дыра);
- M2 `has_editor()` → `return true`: в соло-режиме должен быть отказ, а не падение моста;
- M3 не удалять `port.json` в `_exit_tree()`: если тест это проверяет — красный; если нет,
  проверку добавить.

**1.4 Не трогать:** `editor/bridge/**` (кроме точки старта, если без неё нельзя),
`contract/**`, `verbs_version` (остаётся 1), `tools/*`, `python/kernel/schema.py`,
`python/protocol/**`, принятые механики, `pyproject.toml`-маркеры.

## 2. Стоп-условия

- Ничего не писать в сцену: ни `ResourceSaver`, ни `begin_undo`, ни `scene_apply_batch` — это B.
- Не добавлять примитивы и не менять `result_schema`; не бампать `verbs_version`.
- Не «делать тест зелёным» через skip при найденном движке: если редактор не поднимается —
  это провал среза, а не skip.
- Не править `editor/harness/bridge_probe.gd` (он принят), не пересохранять файлы целиком
  без нужды (концы строк сохранять; `WORKLOG.md` уже выравнивали — не повторять).
- Старый плагин — только чтение; два чужих лога не удалять.

## 3. Чем доказывается

```
python -m pytest tests/py/live -v            # 2 passed (мост + редакторская ветка)
python -m pytest python/modules tests/py     # 418 + N, == --collect-only
python tools/gen_contract.py --check         # ok (8), verbs_version 1
python tools/selfcheck.py context.editor_context
python tools/security_audit.py --json; python tools/lint_arch.py; python tools/check_limits.py
```

В отчёт — версия движка, вывод теста, таблица мутаций с именами красных тестов, `sha256`
восстановленных файлов, `pytest` рядом с `--collect-only`, `files=`/EOL затронутых файлов.

## 4. Записи

Лист `docs/porting/context.editor_context.md` — «Проверки» (редакторская ветка: доказана
каким тестом) и «Блокеры» (что осталось: `undo`/`expected_revision` — это B);
`docs/PROGRESS.md` — строка `context.editor_context`; `docs/WORKLOG.md` — сессия.
Шапки промптов, `README.md`, `_audit-handoff.md` правит аудитор.

## 5. Что проверит аудитор

Повторит живой тест сам (движок у него есть), подложит M1 (`has_editor → false`) и убедится,
что тест **красный** (в отличие от нынешней ситуации), проверит, что `port.json` ведёт себя
как заявлено, что `editor_state` не выдумывает сцены (`open_scenes == []` без открытой сцены),
что регресс 418+N = `--collect-only`, корпус 102/0, 8 артефактов, `verbs_version: 1`,
`__pycache__` 0, старый плагин — те же две `??`.
