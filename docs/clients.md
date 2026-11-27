# Работа вне панели: MCP, CLI и HTTP

Для чтения проекта внешней моделью достаточно MCP: клиент сам запускает локальный процесс, отдельный чат с провайдером и работающий HTTP-сервер не нужны. CLI удобен для воспроизведения одного плана, HTTP — для проверки того, что видит док.

## MCP по stdio

Пример для клиента с конфигурацией `mcpServers`. Замените пути на свои: `--project` — каталог с `project.godot`, `--state` — отдельный каталог состояния **вне игры и исходников аддона**. `PYTHONPATH` нужен, чтобы клиент мог запустить модуль из любого рабочего каталога. Python — той установки, где доступны зависимости из [README](../README.md); Godot — установленный редактор, а не игра.

```json
{
  "mcpServers": {
    "godot-agent": {
      "command": "python",
      "args": ["-m", "python.channels.mcp.stdio", "--project", "D:/Games/MyGame", "--state", "D:/AgentState/MyGame-mcp"],
      "env": {
        "PYTHONPATH": "D:/Games/MyGame/addons/godot_agent",
        "PYTHONUTF8": "1",
        "GODOT_AGENT_GODOT_BIN": "D:/Programs/Godot/Godot.exe"
      }
    }
  }
}
```

После подключения обновите в клиенте список инструментов. Для проверки попросите вызвать `read` с аргументами `{"path":"res://project.godot","start_line":1,"end_line":3}`. Для записи сначала вызывают `assistant_plan`, показывают `diffs` пользователю и только по его решению вызывают `assistant_confirm` с полученными `plan_id` и `digest`. Для отката сохраните `entry_id` квитанции. [Схемы аргументов и ответов](../contract/capabilities/) относятся к инструментам, а не к командам внутри ответа модели.

## CLI

В PowerShell из корня аддона:

```powershell
$project = (Resolve-Path ../..).Path
$state = Join-Path $env:LOCALAPPDATA 'GodotAgent/MyGame-cli'
$env:GODOT_AGENT_GODOT_BIN = 'D:/Programs/Godot/Godot.exe'  # укажите свой путь, если Godot не в PATH
python -m python.channels.cli.main --project "$project" --state-dir "$state" tools list
```

`plan --action-file <путь-к-JSON>` показывает план без записи; `confirm <plan_id> <digest> --approve` применяет именно его, а `--reject` отклоняет. `rollback <plan_id> <entry_id>` использует квитанцию. Для этих команд используйте **тот же** `--project` и `--state-dir`, что при подготовке.

## HTTP уже запущенного дока

Откройте в Godot **Проект → Открыть папку пользовательских данных**. В ней лежат `http_endpoint.json` с адресом процесса и `godot_agent_token.txt` для заголовка `X-Agent-Token`. Не переносите их в проект. Панельный порт — `5000`; порт экземпляра, запущенного с явными `--project` и `--state`, смотрите в его каталоге состояния. Это JSON API панели, не MCP по HTTP.

Для проверки привязки откройте PowerShell **в папке пользовательских данных работающего проекта**:

```powershell
$endpoint = Get-Content ./http_endpoint.json -Raw | ConvertFrom-Json
$headers = @{ 'X-Agent-Token' = (Get-Content ./godot_agent_token.txt -Raw).Trim() }
Invoke-RestMethod "http://127.0.0.1:$($endpoint.port)/init" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}'
```

Ожидается `ok: true` и корень вашей игры в `project_root`. Для вызова инструмента маршрут — `POST /tools/call`, тело — `{"name":"read","args":{"path":"res://project.godot","start_line":1,"end_line":3}}`, заголовки те же.
