# Задача: фаза 0.5 — стража слоёв и доказательств (`lint_arch`), до части A

Ты в `D:\vajno\Godot\agent-rebuild\addons\godot_agent`. Фаза 1 принята аудитом:
`context.gather` — этап 7, `editing.symbol_rename` — модуль-вклад (этап 6, инструмента
нет по ADR-0004), 377 тестов, корпус 102/0, 8 артефактов контракта.

Перед срезом прочитай: `AGENTS.md`, `RULES.md` (**R-22 — новое, читать целиком**),
`docs/PROGRESS.md → Долги`, `docs/porting/_audit-handoff.md` §4, `docs/architecture.md`,
`tools/lint_arch.py` (162 строки, читать целиком), `tests/py/tools/`.

## 0. Факты на старте (проверено аудитом 2026-10-27; числа — только из вывода команд)

База для сверки: `pytest python/modules tests/py` → **377 passed** (сумма
`--collect-only` = 377), `snapshot_diff` → **102/0**, `gen_contract --check` → `ok`
(артефактов 8, «мост: 0 обработчиков из 3»), `lint_arch` → 453/0, `__pycache__` 0,
файлов 889, `python/kernel/schema.py` sha256 `629FCE54…4067`.

Что проверяет `lint_arch` сегодня: только межмодульные рёбра и циклы
(`LAYERS`, `ALLOWED`, `check_edges`, `check_cycles`). Про IO в домене там **нет ни
строки**, хотя отчёты фаз 1 ссылались на него как на доказательство R-11.

Воспроизведи две дыры у себя (обязательно, до правок):

```
1) положить в начало python/modules/context/gather/domain/core.py строку `import os`
   → python tools/lint_arch.py   ⇒ {"status":"ok","detail":"файлов 453, нарушений нет"}  exit 0
2) положить туда же `from python.modules import scene_model`
   → python tools/lint_arch.py   ⇒ снова ok, exit 0
```

Обе подложки — на копии/с бэкапом (`shutil.copyfile`), после проверки файл вернуть
и подтвердить `Get-FileHash` = `F08F2D4B64B9…` (полный хеш сними сам до правки).

## 1. Что сделать

**1.1 Правило «в домене нет IO» — только `python/modules/*/*/domain/**`.**
Запрещённые импорты (и `import X`, и `from X import …`): `os`, `io`, `pathlib`,
`shutil`, `json`, `subprocess`, `socket`, `tempfile`, `sqlite3`, `urllib`, `http`.
Сообщение обязано называть файл (`python/modules/…/domain/core.py:8`) и модуль;
вердикт — `fail`, exit 1. `kernel/` **не покрывается**: там законно
`kernel/paths.py:12 import os` и `kernel/write_plan.py:12 import json`.

**1.2 Сузить `_same_feature` (`tools/lint_arch.py:109-110`).** Сейчас
`if len(mine) < 4 or len(theirs) < 4: return True` пропускает импорт корня чужой
области. Требуется: сравнивать первые четыре сегмента (`python.modules.<area>.<feature>`),
`shared` разрешать как и раньше, а `from python.modules import scene_model` из
`context/gather/domain` — нарушение с внятным сообщением.

**1.3 Тесты — по два на правило, и каждый обязан ломаться мутацией.**

- `tests/py/tools/test_lint_arch_guard.py` (новый файл, `tmp_path` + `monkeypatch`
  на корень, как в существующих тестах инструментов):
  1. `domain/core.py` с `import os` → нарушение с путём файла;
  2. `app.py` с `import os` в том же модуле → **не** нарушение (граница правила);
  3. `domain/core.py` с `from python.modules import scene_model` → нарушение;
  4. `domain/core.py` с `from python.modules.context.shared import x` → не нарушение.
- Мутации: убрать правило IO → тест 1 краснеет; вернуть `len < 4 → True` → тест 3
  краснеет. Файл `tools/lint_arch.py` вернуть побайтово, `sha256` до/после.

**1.4 Отчётность (R-22):** в финальном прогоне печатать `files=<N>` и список новых
файлов; для каждого правленого файла — `lf=<> crlf=<>` до/после (эталон правится
байтовым патчем, а не пересохранением); каждое число в отчёте — из приложенного
вывода.

## 2. Границы

| В срезе | Не в срезе |
|---|---|
| `tools/lint_arch.py` (два правила) + новый тест-файл | любая правка `python/**`, кроме фикстур внутри теста |
| `RULES.md` читать, не менять; записи — WORKLOG, PROGRESS (долг), handoff | `docs/porting/_start-prompt.*` не править — это пишет аудитор |
| прогон `lint_arch`/`selfcheck`/корпуса как регресс | корпуса, контракты, `gen_contract`, `selfcheck`, `snapshot_diff` (только запуск) |

## 3. Стоп-условия

- Не вводить whitelist файлов и не «глушить» правило флагами: исключений нет.
- Не менять `LAYERS`/`ALLOWED` и семантику существующих нарушений — только два
  перечисленных правила.
- Не трогать `python/**` ради «чтобы тесты проходили».
- Старый плагин — только чтение (`python -B`); два чужих лога
  (`python/_ref2.log`, `python/godot_tools/_excl.log`) не твои: не удаляй.
- Не ставить `ported`/не менять этапы механик: срез инструментальный.

## 4. Что проверит аудитор (своими прогонами)

| Что | Как |
|---|---|
| правило IO работает | подложить `import os` в `modules/context/gather/domain/core.py` → `lint_arch` = `fail`, exit 1, в сообщении путь; вернуть → ok, sha совпал |
| граница правила | `import os` в `app.py` того же модуля → ok |
| лазейка закрыта | `from python.modules import scene_model` в `domain/` → fail |
| нет ложных | репозиторный `lint_arch` = `ok`, 453 файла, 0 нарушений (число может вырасти только на новый тест-файл) |
| мутации | обе краснеют ровно те тесты, что заявлены; файл восстановлен побайтово (`sha256`), EOL не изменился |
| регресс | `pytest` = `--collect-only` (377 + новые), корпус 102/0, `gen_contract` ok (8), `selfcheck context.gather`/`editing.symbol_rename` ok, `security_audit` ok |
| гигиена | `__pycache__` 0, `*.bak/tmp/orig` 0, `files=` из вывода, старый плагин не тронут |

## 5. Записи после сдачи

`docs/WORKLOG.md` — сессия; `docs/PROGRESS.md → Долги` — строку про непокрытую
IO-границу помечаешь «выполнено» со ссылкой на прогон и мутацию; в
`docs/porting/_audit-handoff.md` ничего не пишешь (правит аудитор). Лист механики не
нужен: это инструмент, а не механика.
