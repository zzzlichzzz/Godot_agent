> Промпт для новой сессии. Скопировать целиком в чат модели-портера.
> Аудитор (предыдущая сессия) сверяет результат по разделу 5.

# Задача: первый вертикальный срез — механика `project_text.search`

Ты — инженер переноса проекта Godot Agent. Репозиторий: `D:\vajno\Godot\agent-rebuild`,
код плагина: `D:\vajno\Godot\agent-rebuild\addons\godot_agent`.
Архитектура уже принята (6 ADR), правил 21 (R-01…R-21). Ты не меняешь архитектуру —
ты выполняешь первый срез и закрываешь **одну** механику. Всё остальное — не твоя
работа сейчас, даже если «по пути видно улучшение».

## 1. Прочитать до первой правки (по порядку, целиком)

1. `addons/godot_agent/AGENTS.md` — стоп-условия и порядок работы (главный файл).
2. `RULES.md` — 21 правило. Нарушение правила = брак, даже если код работает.
3. `docs/architecture.md` — слои, зависимости, воронка записи.
4. `docs/PORTING.md` — §0 (три источника истины), §1 (шаги), §5 (DoD), §8 (инструменты), §9 (статус).
5. `docs/parity.md` — строка `search`; `docs/mapping.md` — старый код поиска.
6. `docs/tests-map.md` — строка `test_search_quality.py` и семейство `test_project*`.
7. `docs/PROGRESS.md` и `docs/porting/_template.md`.
8. `docs/WORKLOG.md` (последняя сессия) и `docs/NOTES.md` (Q-19, Q-21, Q-23).
9. `docs/adr/0003` (порты и `ModuleContext`), `docs/adr/0006` (`ToolSpec` → контракт).

Файла нет — это дефект репозитория: сказать, а не работать по памяти.

## 2. Состояние, которое ты получаешь (проверено фактами, не гадай)

- 44 модуля в `python/modules/` — **0 строк логики**: `module.py`, `tools.py`,
  `app.py`, `domain/core.py` — шаблоны с `TODO`.
- Каркас — **заглушки по 100–200 байт**: `python/runtime/bootstrap.py`,
  `python/protocol/{registry,dispatch,validation}.py`,
  `python/channels/mcp/{server,stdio}.py`. Их предстоит написать: это единственное
  разрешённое место писать «по спецификации» (ADR-0003), а не по памяти о старом коде.
- Работают: `tools/selfcheck.py`, `tools/probe.py`, `tools/security_audit.py`.
- **Заглушки** (только `TODO`): `tools/lint_arch.py`, `check_limits.py`,
  `gen_contract.py`, `snapshot_record.py`, `snapshot_diff.py`,
  `scaffold_module.py`, `package.py`. Поэтому `selfcheck` сейчас честно даёт
  `blocked` — и это надо исправить в рамках работы (шаг M6), иначе вердикта не будет.
- `pytest` **не установлен** (Python 3.14.6). Q-23 решается в M6: добавить `pytest`
  в dev-зависимости `pyproject.toml` и запускать `python -m pytest`; решение записать
  в `docs/NOTES.md`.
- Эталон (старый плагин): `D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent`
  — **только чтение, ни байта записи** (R-08). Запускать его код только с `python -B`,
  иначе он насыпет `__pycache__` в эталон.

Эталонный поиск запускается так (проверено, работает на Python 3.14):

```powershell
$O='D:\vajno\Godot\тест-плагина-ии\addons\Godot_agent\godot_agent\python'
python -B -c "import sys; sys.dont_write_bytecode=True; sys.path[:0]=[r'$O', r'$O\parsers', r'$O\godot_tools']; from godot_tools import project_tools as pt; print(pt.search_project_text(r'<путь к мини-проекту>', 'func _ready', max_results=5))"
```

Сигнатура эталона:
`search_project_text(project_root, query, max_results=30, context_lines=2, exclude_rel_prefixes=None, case_insensitive=False, needles=None, allow_addons=False, allow_self_edit=False, addon_dir=None)`
→ `(matches, truncated)`. Также смотри `SEARCH_EXTS`, `search_extensions_for`,
`AGENT_ONLY_SEARCH_EXTS` и политику путей (`can_read`, `is_addon`, `is_agent`).

## 3. Порядок работ (жёсткий; каждый шаг = запись в лист механики)

Порядок нельзя переставлять: код, написанный до корпуса, проверяется по памяти
автора, а корпус, снятый после кода, незаметно подгоняется под него (PORTING §1).

**M0. Лист и чтение.**
Создать `docs/porting/project_text.search.md` по шаблону `_template.md`; в
`docs/PROGRESS.md` поставить этап `1`. Прочитать `godot_tools/project_tools.py`
(поиск и политику) и `python/tests/test_search_quality.py`. Записать в лист:
что делает механика, как делим старый файл.

**M1. Корпус (до кода!).**
Создать настоящий мини-проект `fixtures/projects/minimal/` (`project.godot` +
3–5 файлов `.gd`/`.tscn`/`.md`, маленький и стабильный). Снять эталон прогоном
старого агента в `fixtures/corpus/project_text/search/*.json` + `manifest.json`
(R-07): на входе аргументы вызова, на выходе `{matches, truncated}`; пути
нормализованы (`<PROJECT>/scenes/player.tscn`), абсолютных путей нет (SEC-13).
Обязательные кейсы: happy path; пустой результат; кириллица/юникод;
`case_insensitive=true`; `exclude_rel_prefixes`; `max_results=1`;
файл с BOM; файл с CRLF; файл вне допустимых расширений.
Решить Q-19 (где хранить корпус) и Q-21 (формат записи) и записать решение в лист.

**M2. Спецификация.**
`modules/project_text/search/tools.py`: `ToolSpec(name="search")` — аргументы,
результат, `effects="read"`, `idempotent=True`,
`errors=["invalid_input","not_found","denied"]`, `availability="*"`. Источник
правды — `ToolSpec`, `contract/*.json` — генерируемый артефакт (ADR-0006).

**M3. Тесты до кода.**
`modules/project_text/search/tests/test_core.py` — домен на `MemoryFS`, без IO и
без Godot; `tests/py/contract/test_search_contract.py` — схема, набор `kind`,
отсутствие путей и стектрейсов в ошибках.

**M4. Код модуля.**
`ports.py` (нужен только `fs`: обход и чтение) → `domain/core.py` (фильтры
расширений, `case_insensitive`, `exclude_rel_prefixes`, контекст, квота) →
`app.py` ≤ 80 строк (валидация → домен → результат) → `module.py`
(`ModuleSpec`, `provides_tools=["search"]`, `requires_ports=["fs"]`).

**M5. Каркас (минимум под `search`).**
`runtime/bootstrap.py` (реестр портов, чтение `modules/*/*/module.py`,
узкий `ModuleContext`, ADR-0003); `substrate/fs/{disk_fs,memory_fs}.py`;
`protocol/registry.py` (сбор `ToolSpec`, дубль имени → конфликт);
`protocol/validation.py`; `protocol/dispatch.py` (валидация → вызов → маппинг
ошибок по R-15); `channels/mcp/{server,stdio}.py` (JSON-RPC `tools/list`,
`tools/call`). Не делать заранее: профили, `health`, `teardown`, recovery,
HTTP-канал, панель, воронку записи — `search` этого не требует.

**M6. Инструменты проверки (без них нет вердикта, R-18).**
`tools/lint_arch.py` (R-11: импорты только внутрь; модуль не лезет в
`substrate`/`protocol`/`channels`/`editor`), `tools/check_limits.py` (R-06),
`tools/gen_contract.py` + `--check`, `tools/snapshot_record.py`,
`tools/snapshot_diff.py`. Все — общие, без привязки к `search`.
Контракт вердикта: последняя строка stdout — JSON
`{"status": "ok"|"fail"|"not_implemented", "detail": "..."}`.

**M7. Вердикт.**
`python tools/selfcheck.py project_text.search` — нужен exit `0`. Любой `1` или
`2` = работа не закончена; `needs_live` для read-only механики не принимается.

**M8. Живая проверка.**
`python tools/probe.py search --args '{"query":"func _ready","max_results":5}'`
на мини-проекте; сравнить с корпусом; записать в лист и `docs/WORKLOG.md`
(что запускали, что увидели).

**M9. Записи.**
Лист (этап `7`, вердикт вставлен), `docs/PROGRESS.md` (этап + следующее действие
= `code_intel.functions`), `docs/parity.md` → `ported`, `docs/WORKLOG.md` — новая
сессия с выводами команд, `docs/NOTES.md` — принятые решения и новые Q-NN.

## 4. Запрещено (стоп-условия, краткая выдержка из `AGENTS.md`)

- писать в старый плагин; копировать старые тесты файлами (берутся **кейсы**, R-16);
- «улучшать» поведение относительно корпуса: расхождение → `docs/deviations.md`;
- бизнес-логика в GDScript (R-14); запись файлов вне воронки (здесь не нужна: `effects=read`);
- из модуля импортировать чужой `domain/`, `substrate`, `protocol`, `channels`, `editor` (R-11);
- менять `RULES.md`/ADR без причины; молчаливые исключения «здесь можно»;
- ставить `ported` без зелёного `selfcheck` и записи о живой проверке;
- коммитить `__pycache__`, `reports/`, корпус с абсолютными путями, секреты
  (`.env`, `*.key`, `secrets*` уже в `.gitignore`).

## 5. Что аудитор будет проверять (готовь доказательства сразу)

| Что | Доказательство |
|---|---|
| Механика работает | полная таблица `selfcheck` + `reports/selfcheck/project_text.search.json` |
| Клиент видит результат | вывод `probe.py search --args '...'` |
| Поведение равно эталону | файлы корпуса, число кейсов, вывод `snapshot_diff` |
| Границы соблюдены | вывод `lint_arch.py`, `check_limits.py`, `gen_contract.py --check` |
| Статус записан | строки в `PROGRESS.md`, `parity.md`, лист механики, `WORKLOG.md` |
| Ничего не сломано | 0 правок в старом плагине, нет `__pycache__` в эталоне, `security_audit` → `ok` |

Отчёт вида «готово, всё работает» без вывода команд не принимается (R-18).
Если что-то не получилось — написать прямо, что и почему; «округление» результата
считается дефектом.

## 6. Границы ожиданий

- Каркас (M5) — единственное место, где допустим код по спецификации; ожидай, что
  после второго модуля его придётся переделать. Это нормально и записано в листе.
- Не закрывай все 44 механики, всю безопасность и всю панель. Один срез, одна
  механика, честный вердикт.
- Упёрся в блокер — остановись, запиши в лист (раздел «Блокеры») и в `docs/NOTES.md`,
  а не обходи правило.

## 7. Первый ответ в новой сессии

Короткий план на 8–12 строк: что уже проверил в файлах (с цитатами путей), какие
шаги M0…M9 берёшь, что считаешь главным риском. Вопросы — только о том, чего нет
в файлах; всё остальное там уже написано. Затем начинай с M0 и не жди разрешения
на каждый шаг.

