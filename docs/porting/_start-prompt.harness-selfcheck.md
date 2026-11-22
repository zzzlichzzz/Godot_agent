# Задача: фаза A.1.1 — харнесс моста доказывает сам себя (или честно говорит, что ждёт клиента)

**Статус:** часть A принята как `ported` с долгом. Живой прогон на настоящем движке
(`D:\vajno\Godot\Godot v4.6.3\...console.exe`, 4.6.3) **есть и проходит по проводу**, но
доказательство в отчёте снято не с той команды. Это надо закрыть до части B.

## 0. Что проверено аудитом (2026-10-28, воспроизводится)

1. Команда из промпта §2.1, дословно:

    godot --headless --path D:\vajno\Godot\agent-rebuild -s res://addons/godot_agent/editor/harness/bridge_probe.gd

   даёт **`ok:false`**, `failure.reason = "timeout"`, `served: []`, `elapsed_s ≈ 20.0`,
   exit 1. Два прогона подряд, разные порты (`59839`, `59958`), результат один.
2. Та же команда **с внешним клиентом** (Python `EditorClient` по `port`/`token` из
   `BRIDGE_PORT`) даёт `ok:true`, все три примитива отвечают, exit 0, `harness_result.json`
   с `verbs: editor_ping/editor_selection/editor_state`.
3. `tests/py/live/test_bridge_live.py` (1 тест, `pytest tests/py/live -v` → passed) —
   он **сам является клиентом**: поднимает харнесс, читает `BRIDGE_PORT`, зовёт три
   примитива, валидирует их схемами и сверяет с `harness_result.json`. То есть провод
   доказан, и доказательство лежит в pytest-прогоне, а не в «одиночном» запуске.
4. Следствие: `harness_result.json` с тремя ответами, приведённый в отчёте рядом с
   командой `-s ...`, получен во время pytest-прогона. Отчёт склеил команду и результат
   из разных запусков (R-22, «доказательство со сданного файла»).

## 1. Что сделать

**1.1 Решить и записать одно из двух (по умолчанию — вариант «а»):**

- **а) харнесс честно ждёт клиента.** `bridge_probe.gd` в одиночном режиме печатает
  `BRIDGE_PORT {...}`, ждёт до `TIMEOUT_MS`, и если запросов не было — пишет
  `ok:false, failure.reason = "no_client", served: []` (не `timeout`), exit 1, а в
  `detail` — подсказку: «запусти `python -m pytest tests/py/live -v` или подключись
  `EditorClient`». Приёмкой считается **pytest-прогон**; в листе и PROGRESS команда
  приёмки — pytest, а не `-s`.
- **б) харнесс сам себе клиент.** Внутри GDScript поднимается TCP-клиент, шлёт три кадра,
  сверяет ответы схемой и только потом пишет `ok:true`. Тогда одиночная команда даёт
  `ok:true` сама. Дороже: свой клиент в GDScript — это транспорт в `harness/`, не в
  `editor/bridge/**` (R-14 не нарушается, но код дублирует `substrate/editor/client.py`).

**1.2 Привести документацию к факту:** в `docs/porting/context.editor_context.md`
(раздел «Проверки») и в `docs/PROGRESS.md` (строка `context.editor_context`) написать
дословно: «живой прогон: `python -m pytest tests/py/live -v` → 1 passed, движок
`4.6.3-stable`, три примитива, `harness_result.json.ok = true`; одиночный `-s` без
клиента даёт `ok:false/no_client` — это норма, а не провал».

**1.3 Не трогать:** `editor/bridge/**` (там только что починены BE-кадр, `_owners`,
`has_editor` — регресс не нужен), контракт, `verbs_version` (остаётся 1), `tools/*`,
`python/kernel/schema.py`, принятые механики, часть B.

## 2. Чем это доказывается

- `python -m pytest tests/py/live -v` → `1 passed`, в выводе — версия движка.
- одиночная команда → `ok:false` с причиной `no_client` (вариант «а») или `ok:true`
  (вариант «б»), **и то же самое написано в отчёте**.
- `pytest python/modules tests/py` = `--collect-only` (**было 418**, 40 файлов);
  `snapshot_diff` 102/0; `gen_contract --check` ok (8); `selfcheck context.editor_context`
  ok (unit 27); `lint_arch` / `check_limits` 453/0; `security_audit` ok; `__pycache__` 0.
- Мутация по R-22 (одна, последовательно): сломать `has_editor()` → `context_snapshot.gd`
  и убедиться, что **живой** тест остаётся зелёным (режим `-s` в редакторскую ветку не
  заходит) — то есть зафиксировать, что редакторская ветка этим тестом не покрыта;
  файл восстановить байтово (`shutil.copyfile`, `sha256` до/после).

## 3. Что проверит аудитор

| Что | Как |
|---|---|
| одиночная команда не врёт | повторю её сам: `ok:false/no_client` (а) или `ok:true` (б), и текст в отчёте совпадает с выводом |
| провод живой | `pytest tests/py/live -v` у меня → passed, движок 4.6.3, три примитива, `harness_result.json.ok = true` |
| регресс | 418 = `--collect-only`, 102/0, 8 артефактов, 453/0, `selfcheck` ok, `__pycache__` 0 |
| границы | `editor/bridge/**`, контракт, `verbs_version`, `tools/*`, `schema.py` — без изменений (сверю `sha256`) |

## 4. Записи

`docs/porting/context.editor_context.md` — «Проверки» и «Блокеры» (редакторская ветка:
что именно не покрыто и какой командой закрывать: `godot --headless --editor --path <проект>`),
`docs/PROGRESS.md` — строка `context.editor_context`, `docs/WORKLOG.md` — сессия с выводом
обеих команд. Шапки промптов, `README.md` и `_audit-handoff.md` правит аудитор.
