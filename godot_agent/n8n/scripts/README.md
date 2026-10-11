# scripts/ — инструменты работы со схемой n8n

Служебные скрипты для разработки и проверки схемы воркфлоу
«Шаблон v2: Ядро + 4 канала» (id `v81fH05KY5uKUNK0`). Запуск — из папки `n8n/`,
Python 3.10+ (только стандартная библиотека, ничего ставить не нужно).

## Куда смотрим

- **База n8n** (`~/.n8n/database.sqlite`) — источник истины по схеме.
  Из неё читают `export_workflow.py` и `verify_snapshot.py`.
- **MCP-сервер n8n** (`http://localhost:5678/mcp-server/http`) — живой доступ:
  исполнения (прогоны) и точечные правки. Здесь работают `mcp_invoke.py` и
  `dump_execution.py`. Нужен Bearer-токен: переменная окружения `N8N_MCP_TOKEN`
  или файл `~/n8n/mcp_call.py` (в репозиторий не входит).

## Скрипты

| Скрипт | Зачем | Типовой запуск |
|---|---|---|
| `export_workflow.py` | Снять схему из базы в `schemas/template_v2_core_4_channels.json` (без ключей — только ссылки на креды) | `python -B scripts/export_workflow.py` |
| `verify_snapshot.py` | Сверить снапшот с текущей базой (0 = совпадает) | `python -B scripts/verify_snapshot.py` |
| `check_no_secrets.py` | Перед коммитом: убедиться, что в снапшоте нет ключей | `python -B scripts/check_no_secrets.py` |
| `import_workflow.cmd` | Импортировать снапшот в n8n (перенос на другой инстанс) | `scripts\import_workflow.cmd` |
| `mcp_invoke.py` | Один вызов любого инструмента n8n MCP (`tools/call`) | `python -B scripts/mcp_invoke.py get_workflow_execution '{"workflowId":"v81fH05KY5uKUNK0","executionId":"61"}'` |
| `dump_execution.py` | Разобрать прогон: статус, ноды, ошибки, данные выбранных нод | `python -B scripts/dump_execution.py 61 --nodes "Аудитор (ищет баги)"` |

## Типовые сценарии

**Правка схемы** (пример: починить параметр у ноды):
1. `python -B scripts/mcp_invoke.py update_workflow @ops.json` — точечная правка
   через MCP; сохраняет сразу новую версию и делает её активной.
2. `python -B scripts/export_workflow.py` — обновить снапшот в `schemas/`.
3. `python -B scripts/verify_snapshot.py` — убедиться, что снапшот == база.
4. `python -B scripts/check_no_secrets.py` — проверка перед коммитом.

**Разбор неудачного прогона:**
1. `python -B scripts/dump_execution.py <id>` — список нод и ошибок.
2. `... <id> --nodes "Поисковик (субагент),Аудитор (ищет баги)"` — данные
   конкретных нод (первый запуск каждой, полный JSON — в `--out`).
3. `... <id> --out dump.json` — полный ответ MCP сохранить в файл.

**Пример `ops.json`** для `mcp_invoke.py` (объект JSON; BOM допустим — файл
читается как utf-8-sig):

```json
{
  "workflowId": "v81fH05KY5uKUNK0",
  "operations": [
    {"type": "updateNodeParameters",
     "nodeName": "Поисковик (субагент)",
     "parameters": {"text": "={{ $fromAI('input', 'Что искать в проекте (1-2 фразы).', 'string') }}"}}
  ]
}
```

## Связанные файлы

- `../README.md` — общий обзор папки n8n (состав схемы, креды, точки входа).
- `../schemas/template_v2_core_4_channels.json` — снапшот схемы (источник
  для выпусков плагина).
- Одноразовые разборы прогонов держите вне репозитория; всё, что нужно
  повторно, складывайте сюда, в `scripts/`.
