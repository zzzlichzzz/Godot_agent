# scripts/ — инструменты работы со схемой n8n

Служебные скрипты для разработки и проверки схемы воркфлоу
«Шаблон v2: Ядро + 4 канала» (id `v81fH05KY5uKUNK0`) и её копии-ветки
«Шаблон v3: Эконом + отказоустойчивость» (id `rIwvKxDNhOxodBCc`). Запуск — из папки `n8n/`,
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
| `fork_workflow.py` | Форк: копия текущего черновика с новым id/именем в новый файл (ветка разработки) | `python -B scripts/fork_workflow.py --name "Шаблон v3: …" --out schemas/template_v3_economy.json` |
| `mcp_invoke.py` | Один вызов любого инструмента n8n MCP (`tools/call`) | `python -B scripts/mcp_invoke.py get_workflow_execution '{"workflowId":"v81fH05KY5uKUNK0","executionId":"61"}'` |
| `dump_execution.py` | Разобрать прогон: статус, ноды, ошибки, данные выбранных нод | `python -B scripts/dump_execution.py 61 --nodes "Аудитор (ищет баги)"` |
| `token_report.py` | Токены прогона: вызовы и usage каждой «Модель (…)» (замер «эконома») | `python -B scripts/token_report.py 92 93 94 95` |

## Типовые сценарии

**Правка схемы** (пример: починить параметр у ноды):
1. `python -B scripts/mcp_invoke.py update_workflow @ops.json` — точечная правка
   через MCP; сохраняет сразу новую версию и делает её активной.
2. `python -B scripts/export_workflow.py` — обновить снапшот в `schemas/`.
3. `python -B scripts/verify_snapshot.py` — убедиться, что снапшот == база.
4. `python -B scripts/check_no_secrets.py` — проверка перед коммитом.

**Новая ветка схемы (форк под эксперименты):**
1. `python -B scripts/fork_workflow.py --name "Шаблон v3: …" --out schemas/template_v3_economy.json` —
   копия снимается с живой базы, id генерируется, исходная схема не трогается.
2. `scripts\import_workflow.cmd "<абсолютный путь к файлу>"` — импорт копии в
   n8n: создаётся новый черновик (не активный).
3. `python -B scripts/verify_snapshot.py --workflow-id <новый id> --file <файл>` —
   сверка копии в базе с сохранённым файлом.

**Разбор неудачного прогона:**
1. `python -B scripts/dump_execution.py <id>` — список нод и ошибок.
2. `... <id> --nodes "Поисковик (субагент),Аудитор (ищет баги)"` — данные
   конкретных нод (первый запуск каждой, полный JSON — в `--out`).
3. `... <id> --out dump.json` — полный ответ MCP сохранить в файл.

**Оценка токенов прогона («эконом»-ветка):**
1. `python -B scripts/token_report.py 92 93 94 95` — по каждому прогону: вызовы
   каждой «Модель (…)» (точно, из метаданных) и prompt/completion-токены
   (avg и максимум ответа; сумма по полученным запускам, обычно всем).
2. `... --out tokens.json` — те же цифры в JSON (сравнение «до/после» правок
   схемы; ответы MCP тяжёлые — по сотне запусков на модель).

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
- `../schemas/template_v3_economy.json` — снапшот копии-ветки v3 (черновик
  для рефакторинга «эконом + отказоустойчивость»).
- Одноразовые разборы прогонов держите вне репозитория; всё, что нужно
  повторно, складывайте сюда, в `scripts/`.
