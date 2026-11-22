# Задача: фаза B.1 — убрать расхождения версии словаря и решить судьбу корпуса для редакторных механик

**Статус:** часть B сдана как **этап 4** (не `ported`): `selfcheck editing.scene_ops` →
`blocked`, единственный провал — `corpus` (`not_implemented`, «нет корпуса механики»),
остальные чеки `ok` (unit 25). Аудит 2026-10-28 принял код и мутации M1–M3, но нашёл два
расхождения версии и незакрытый вопрос корпуса. Эта фаза — про них, не про новую функциональность.

## 0. База (замер аудита 2026-10-28, сессия 38)

```
python -m pytest python/modules tests/py --ignore=tests/py/live   # 442 passed == --collect-only
python -m pytest tests/py/live -v                                 # 2 passed (4.6.3)
python tools/snapshot_diff.py                                     # 102/0
python tools/gen_contract.py --check                              # ok, артефактов 9, verbs_version 2, verbs 5
python tools/selfcheck.py editing.scene_ops                       # blocked (только corpus), unit 25
```

`contract/editor_verbs.json` `EAFF6D5F…`, `scene_verbs.gd` `60B98CCA9666` (маркеров 5),
`scene_ops/domain/core.py` `6309DF88DA21`, `capabilities/scene_ops.json` `7A4EEF5F0031`;
незыблемое: `kernel/schema.py` `629FCE54…`, `tools/gen_contract.py` `FA7E6E91…`,
`tools/lint_arch.py` `1FAD8E74…`. Файлов 908, `__pycache__` 0.

## 1. Что сделать

**1.1 Две копии `verbs_version: 1` при контракте 2.** Факт (проверено грепом):

- `python/modules/context/editor_context/tests/test_core.py:13` — `PING = {"godot": "4.6",
  "verbs_version": 1, "protocol": 1, …}`: фикстура доказывает ответ несуществующей версии;
- `editor/harness/bridge_probe.gd:134` — `payload := {"ok": ok, …, "verbs_version": 1}`:
  `harness_result.json` врёт о версии моста;
- `tests/py/live/test_bridge_live.py:174` — `assert payload["protocol"] == 1 and
  payload["verbs_version"] == 1` **закрепляет** это враньё.

Сделать: тест вклада сверяет `PING["verbs_version"]` с контрактом (читать
`contract/editor_verbs.json` в тесте — как `tests/py/kernel/test_schema_union.py`), харнесс
берёт версию из `SocketServerScript.VERBS_VERSION` (или из контракта), живой тест требует
`payload["verbs_version"] == verbs_catalog.version()`. Ни одного литерала `1` в этих трёх местах
не остаётся.

**1.2 Судьба корпуса для механик, которые исполняются в GDScript.** Сейчас `corpus`
недостижим: `tools/snapshot_record.py` берёт эталон через `tools/_reference_runner.py`
(Python-функции эталона), а у сцены эталона Python-функции нет — исполнение в GDScript.
Выбрать **один** вариант и закрепить машинно, а не текстом:

- **A (предпочтительно, если правила позволяют):** признать «корпус только для Python-механик»
  явным флагом: `corpus: "live"` в `ModuleSpec` (или `corpus_policy` в манифесте), `selfcheck`
  печатает это в `detail` и **не** считает провалом только при наличии живого теста
  (`tests/py/live/*` с этим `module_id`); тест в `tests/py/tools/test_selfcheck_readiness.py`
  (положительный + отрицательный случай: флаг без живого теста → `not_implemented`);
- **B:** добавить ветку `editing.scene_ops` в `REFERENCES` и корпус на фейке (эталон поведения —
  эталонный GDScript читать нельзя как Python; корпус строится по нашим же сценариям, тогда
  это фиксация, а не эталон).

Выбор записать в лист и в `docs/NOTES.md` одной строкой с причиной; `selfcheck` после правки
обязан давать `editing.scene_ops` → `ok` **или** `blocked` с причиной, закреплённой тестом
(вердикт не подкручивать руками).

**1.3 Не трогать:** `editor/bridge/verbs/scene/**` (кроме строки версии в харнессе),
`contract/**` (только чтение), `python/kernel/schema.py`, принятые механики, корпуса.
`verbs_version` остаётся 2 — бампа в этой фазе нет.

## 2. Стоп-условия

- Ничего не писать в сцену, не добавлять примитивы, не менять `result_schema`.
- Не «делать зелёным» через удаление чека `corpus` — только флаг с тестом или корпус.
- Правка `tools/selfcheck.py` — с новым тестом и мутацией (R-22); `tools/gen_contract.py`
  и `tools/lint_arch.py` не трогать.
- Старый плагин — только чтение; два чужих лога не удалять; дампы — в `%TEMP%`.

## 3. Чем доказывается

`pytest` (число = `--collect-only`), `tests/py/live -v` → 2 passed, `snapshot_diff` 102/0,
`gen_contract --check` ok (9), `selfcheck editing.scene_ops` → ожидаемый вердикт из §1.2,
`security_audit`, `lint_arch`, `check_limits`, `__pycache__` 0, `files=` из вывода.
В отчёт — грепы, доказывающие отсутствие литералов `verbs_version: 1` (кроме `protocol: 1`),
таблица мутаций (минимум: `selfcheck`-флаг снять → тест краснеет; версию вернуть на 1 →
живой тест краснеет), `sha256` восстановленных файлов.

## 4. Записи

Лист `docs/porting/editing.scene_ops.md` («Инструменты проверки», «Блокеры»),
`docs/PROGRESS.md` (этап механики — по факту вердикта), `docs/NOTES.md` (решение по корпусу),
`docs/WORKLOG.md` (сессия). README, `_audit-handoff.md`, шапки — правит аудитор.

## 5. Что проверит аудитор

Своими прогонами: `442+N` = `--collect-only`, живые 2 passed, `selfcheck editing.scene_ops`
даёт ровно тот вердикт, который закреплён тестом; грепом — что литералов `verbs_version: 1`
в коде/тестах/харнессе нет; подложит обратно `1` в харнесс → живой тест обязан краснеть;
снимет флаг/ветку корпуса → соответствующий тест краснеет; корпус 102/0, 9 артефактов,
`__pycache__` 0, старый плагин — те же две `??`.
