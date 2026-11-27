# Godot Agent — rebuild

Рабочий Python-agent, тонкий Godot-плагин и локальные CLI/HTTP/MCP каналы.
Правила проекта: `RULES.md` (R-01…R-22); архитектура — `docs/architecture.md`.
`ToolSpec` — источник контракта; `contract/` генерируется, не редактируется вручную.

## Возможности и границы

- K1: independently accepted read-only `chat`; native parser/API/judge и 50 bindings
  сохранены. K1 не даёт разрешения на запись.
- Отдельные `assistant_plan`, `assistant_confirm`, `assistant_rollback`,
  `assistant_turn` имеют effects=`write`. Plan/turn лишь готовят preview.
  Разрешение выдаёт только явный confirm с `plan_id`, `digest` и `--approve`:
  `USER_CONFIRMED` → единственный executor → WAL/journal → rollback.
  `--reject` не записывает проект. Для отката нужны `plan_id` и `entry_id`.
  Изменившиеся/чужие байты и identity дают конфликт, а не перезапись.
- Безопасные create/edit scene, text resource и project settings: native SDK
  prepare/execute в отдельном внешнем Godot-overlay; в проект возвращается raw
  delta для того же подтверждаемого B-funnel. Отказы native, float32, UID,
  пустой staged_hash и восстановление при отказе сохранены.
- HTTP и MCP вызывают один Agent. HTTP — только собственный случайный порт
  `127.0.0.1`, external token, Host/Origin/bounds; MCP — JSON-RPC stdio.
- Плагин показывает чат/preview/approve/reject/rollback и сохраняет принятый
  bridge/lifecycle. Native UI/host/updater/config остаются неактивными reference,
  кроме трёх SDK, допускаемых лишь в owned overlay. Это не второй executor.

**Ограничения:** скриптовые ресурсы, autoload, binary resource dependencies и
escaped/external/protected references в структурном overlay fail closed, не
подменяются заглушками. Обычные file/WAL операции остаются отдельным механизмом.
Консервативный фильтр может также отклонить допустимые строковые settings,
parent-node paths и строки с `.cfg`/code suffix (ADR0089); это явный safety/parity gap.
Headless editor/dock и captured UI transport не являются доказательством
визуальной desktop-проверки. Offline fixtures не являются доказательством provider/browser live.
Browser recorded-протокол отдельно от live; Qwen live-дефект отложен пользователем.
NN, training/weights, `doh.py`, `n8n/scripts` исключены. Две исторические
WinError1314 symlink-проверки остаются privilege coverage gap, не успехом.
При сборке D130 обнаруживаются 33 действующих манифеста и 13 заготовок; опубликовано 36 контрактов. Как добавить модуль и проверить отказ его зависимости — в [архитектуре](docs/architecture.md) и [примерах проверки](tests/py/integration/test_module_composition.py).
T1: independent_acceptance=false до отдельного аудита; seal/ZIP — целостность,
не самостоятельное принятие.

## Установка и external state

Python 3.11+, Godot 4.6. Пакет не устанавливает зависимости/браузеры автоматически.
Для тестов нужен pytest; для opt-in HTTP нужен Flask (runtime dependencies сейчас
не объявлены в pyproject). Установка — отдельное действие пользователя:

```powershell
python -m pip install pytest Flask
```

Проект и addon должны быть доступны в PYTHONPATH/cwd. Секреты, profile, WAL,
token/endpoint и runtime logs хранятся вне проекта и addon. Для структурных
операций задайте **абсолютный** путь к существующему Godot console binary:

```powershell
$env:GODOT_AGENT_GODOT_BIN = "D:\Godot\Godot_v4.6-stable_win64_console.exe"
$env:GODOT_AGENT_STATE_DIR = "C:\Users\<USER>\AppData\Local\godot_agent_state"
```

Нет PATH-discovery, action-selected executable или shell. Без бинарника file
operations/read-only chat доступны, структурная подготовка возвращает unavailable.
Provider credentials задаются только внешней конфигурацией/разрешёнными
GODOT_AGENT_* env; ключи не помещаются в проект, fixtures, отчёты или примеры.
Сам факт наличия переменной не является разрешением агенту на live-сетевой тест.

## CLI

Запускайте из папки addon. Замените `<PROJECT>`, `<EXTERNAL_STATE>` и остальные
placeholders. Все команды одного plan/confirm/rollback цикла используют один
проект, один state и один channel/profile; чужой план не переносится между profiles.

```powershell
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" health
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" tools list
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" chat "Объясни структуру проекта"
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" repl
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" turn "Подготовь изменение"
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" plan --action-file "<ACTION_JSON>"
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" confirm "<PLAN_ID>" "<DIGEST>" --approve
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" confirm "<PLAN_ID>" "<DIGEST>" --reject
python -m python.channels.cli.main --project "<PROJECT>" --state-dir "<EXTERNAL_STATE>" rollback "<PLAN_ID>" "<ENTRY_ID>"
```

`chat` не пишет проект. `turn` может вернуть pending confirmation, но не применяет
его сам. Action JSON — данные, не команды. `python tools/probe.py <tool> --args
'{...}'` показывает реальную typed envelope; ошибки/needs_live не считаются pass.

## Local HTTP, MCP и Godot UI

```powershell
python -m python.channels.http --project "<PROJECT>" --state "<EXTERNAL_STATE>"
python -m python.channels.mcp --project "<PROJECT>" --state "<EXTERNAL_STATE>"
```

HTTP по умолчанию выбирает порт0 (собственный random loopback listener). Реальный
порт находится в external `http_endpoint.json`; не используйте hardcoded endpoint,
не запускайте сервер на публичном интерфейсе. MCP пишет protocol frames в stdout,
не запускает listener. `--state` у HTTP/MCP и `--state-dir` у CLI — разные реальные
parser flags. Token не копируется в проект и не печатается для настройки UI.

Для UI задайте `GODOT_AGENT_STATE_DIR` тому Godot-процессу, который откроет проект,
на тот external HTTP profile, где лежат endpoint/token. Запустите HTTP отдельно,
включите `Godot Agent` в Project Settings → Plugins. Корневой `plugin.cfg` по-прежнему
использует `plugin.gd`; native `agent_entry`/updater не включаются. Без корректного
external profile панель отказывает локально до token IO; confirm/reject передают
оба preview identifiers. Ошибка rollback не выдаётся за успешное восстановление.

Принятый Godot bridge отдельно использует `user://godot_agent/port.json`, не HTTP
state. Для UI выделите отдельный Godot user-data namespace в Project Settings;
не запускайте параллельно проекты, делящие этот namespace. Новые live-пробы
использовали заранее отсутствующий namespace; прежний global profile не объявлен
проверенным или автоматически восстановленным. HTTP endpoint/token туда не копируются.

## Проверка и доказательства

```powershell
python tools/selfcheck.py assistant.write
python tools/security_audit.py
python tools/lint_arch.py
python tools/check_limits.py
python tools/gen_contract.py --check
python -m pytest tests/py python/modules --ignore=tests/py/live
```

Для accepted K1 offline-корпуса требуется полный sealed helper/config, описанный
в WORKLOG (independent acceptance 2026-11-20, строки10746–10764). Запуск без него
и без отдельно разрешённого provider не воспроизводит offline verdict; это не
основание менять native parser/goldens или выдавать failed corpus за pass.
Сопоставление native/generated identities нормализует только доказанные новые
UID/unique_id и соответствующие заранее проверенные raw hashes, не удаляет поля.

Точные package paths, paired counts, текущие восстановленные mutants и sealed
hashes: `docs/porting/T1-godot-tools.md`, `docs/porting/T1-write.md`,
`docs/porting/T1-channels.md`, `docs/porting/T1-editor.md`, `docs/porting/T1-final.md`,
`docs/PROGRESS.md`, `docs/parity.md`, `docs/tests-map.md`, append-only WORKLOG.
Accepted A/K1/B/C/D evidence не перезаписывается; rejected attempts остаются видимы.
Финальный T1 передаётся независимому аудитору, а не объявляется принятым самим agent.
