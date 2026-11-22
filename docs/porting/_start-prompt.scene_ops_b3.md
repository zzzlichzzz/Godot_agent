# Задача: фаза B.3 — доказать «один undo на батч» и откат истории

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Фаза B.2 принята: мост
компилируется (`--check-only` по `scene_executor.gd` — exit 0, `B72809EAB395`), `_scan`
честный (моя подложка `zz_break.gd` → живой тест красный и называет файл), живой
`plan → apply` доказан. Осталась **одна дыра, ради которой механика и существует**:
undo-батч не проверен, а мутации `create_action`/`commit_action` живой тест не ловят.

## 0. Факты на старте (замер аудита 2026-10-29, сессия 41)

```
python -m pytest python/modules tests/py --ignore=tests/py/live -q   # exit 0
python -m pytest python/modules tests/py --collect-only -q          # 451 (43 файла)
python -m pytest tests/py/live -q                                   # 2 passed (4.6.3)
python tools/gen_contract.py --check    # ok, артефактов 9, verbs_version = 2
python tools/snapshot_diff.py           # 102/0
python tools/selfcheck.py editing.scene_ops      # ok (unit 25, corpus live)
python tools/selfcheck.py context.editor_context # ok (unit 28)
```
Хеши-опоры: `contract/editor_verbs.json` `EAFF6D5FD17A`, `python/kernel/schema.py`
`629FCE54E6FE`, `scene_executor.gd` `B72809EAB395`, `bridge_probe.gd` `B0F4C4C767BB`.
Файлов 910, `__pycache__` 0. Моя подложка после себя оставила `zz_break.gd.uid` —
удалён; впредь после подложки убирать и `.uid`, сгенерированный движком.

**Из отчёта B.2 (честная граница, которую надо закрыть):**
- M2 (убрать `create_action`) и M2′ (убрать `commit_action`) — живой тест зелёный,
  то есть «ровно одно действие в истории» ничем не проверено;
- undo снаружи не вызывается: в словаре нет `editor_scene_undo` (долг D-4);
- «после сбоя сцена не изменилась» доказано пробой на копии, а не реальным откатом.

## 1. Что сделать

**1.1 Новый примитив `editor_scene_undo` (read-only для модели, write для сцены).**
Контракт `contract/editor_verbs.json`: примитив с `effects: "write"`, `thread: "main"`,
вход `{scene, expected_revision}`, выход `{revision, undone: bool, undo_label}`;
`verbs_version` **2 → 3** и бамп во всех шести зашитых местах (`session.gd`,
`editor_verbs.gd`, `socket_server.gd` port.json, `fake_editor.py` два места,
`test_editor_context_bridge.py`) + копия `PING`/`CONTRACT`-фикстура в
`editor_context/tests/test_core.py` берётся из контракта (уже так — не ломать).
ADR-0007: строка в «Журнал бампов», причина — «нужен откат истории как примитив».

**1.2 Исполнение отката в GDScript.** В `editor/bridge/verbs/scene/` (новый
`scene_undo.gd` или функция в существующем — как чище) — `EditorInterface.
get_editor_undo_redo().undo()` для активной сцены с проверкой `expected_revision`;
ответ `undone: true` и новый `revision` из счётчика моста; при несовпадении ревизии —
`conflict/details.reason="revision_mismatch"`, при пустой истории — `conflict/
details.reason="nothing_to_undo"`. Маркер `# verb: editor_scene_undo` обязателен
(`gen_contract` сверяет три стороны).

**1.3 Доказать «один undo на батч» и «после сбоя сцена не изменилась».**
В `tests/py/live/test_editor_branch_live.py`:
1. два `set_property` в одном плане → `apply` → **`editor_scene_undo`** возвращает
   значение **обоих** свойств к исходному, `undone: true`, `revision` вырос;
2. после `undo` повторный `undo` → `conflict/nothing_to_undo` (не молчание);
3. сбой на второй операции → сцена не изменилась (`revision`/`dirty` те же) **и**
   `editor_scene_undo` отвечает `nothing_to_undo` — то есть батч не оставил записи;
4. число действий в истории: до батча `N`, после батча `N+1` (через
   `get_editor_undo_redo().get_history_undo_redo(id)`, если доступно; если API
   недоступен — зафиксировать это в отчёте как границу, а не выдумывать).

**1.4 Мутации, которые обязаны краснеть** (на сдаваемом файле, последовательно,
`shutil.copyfile`, sha256 до/после): убрать `create_action` → п. 4 краснеет;
убрать `commit_action` → п. 1 краснеет (undo нечего откатывать); убрать сверку
`expected_revision` в undo → п. 2/3 краснеет. Три зелёных мутации = три непокрытых
требования, сдавать нельзя.

**1.5 Не трогать:** `python/kernel/schema.py`, `tools/gen_contract.py`,
`tools/lint_arch.py`, `tools/selfcheck.py`, корпуса, принятые механики,
`corpus="live"` у `scene_ops`.

## 2. Стоп-условия

- В сцену — только внутри одного undo-действия; `ResourceSaver` нет; второй сокет нет.
- Записи в сцену только при `applied`-пути; после любого отказа — ни одного изменения.
- Старый плагин — только чтение, два чужих лога не удалять; временное — в `$env:TEMP`,
  подложки убирать вместе с `.uid` (мой урок).
- Мутации/подложки последовательно, sha256 до/после, `restored identical: True`.
- Прогоны — с `PYTHONDONTWRITEBYTECODE=1` (одного `-B` для `pytest` мало).

## 3. Чем доказывается

`--check-only` по новому/изменённым `.gd` → exit 0; `pytest tests/py/live -v` →
**3+ passed**; `pytest … --ignore=tests/py/live` = сумма `--collect-only`;
`gen_contract --check` ok (**9** артефактов, `verbs_version = 3`); `snapshot_diff`
102/0; `selfcheck` двух механик `ok`; `__pycache__`/`.pytest_cache`/`zz_*`/`*.bak` 0;
`files=` из вывода команды; в отчёте — таблица мутаций с красными тестами и явная
фраза о том, что осталось непроверенным.

## 4. Записи

Лист `docs/porting/editing.scene_ops.md` (undo-примитив, ход работы, блокеры),
`docs/PROGRESS.md` (этап 6, `ported` ставит аудитор), `docs/adr/0007-most-redaktora.md`
(бамп 3), `docs/WORKLOG.md` (сессия). Шапки промптов, `README.md`,
`_audit-handoff.md` — правит аудитор.

## 5. Что проверит аудитор

Свой `--check-only`, свой живой прогон (3+ passed), числа = `--collect-only`,
`gen_contract` 9 и `verbs_version 3`, `snapshot_diff` 102/0, `selfcheck` обеих
механик `ok`, **свою** подложку (undo без батча → `nothing_to_undo`; чужой
`expected_revision` → `conflict`), свои три мутации, побайтовое восстановление,
гигиену (`zz_*` и `.uid` после подложек), старую папку с двумя `??`.
