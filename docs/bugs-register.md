# Реестр актуальных багов Godot Agent

## ОТКРЫТЫЕ БАГИ

### BUG-001: Конфликт эксклюзивных дочерних окон
- Ошибка: `Attempting to make child window exclusive, but the parent window already has another exclusive child`
- Источник: ConfirmationDialog панели конфликтует с AcceptDialog стартового экрана
- Серьёзность: низкая (UI-навигация, не крашит)
- Статус: ОТКРЫТ
- Фикс: показывать ConfirmationDialog только после закрытия стартового экрана

### BUG-002: Parameter obj is null ×6
- Ошибка: `core/variant/callable.cpp:557 - Parameter "obj" is null` (6 раз)
- Причина: сигнал/callable вызывается на освобождённом объекте
- Серьёзность: средняя
- Статус: ОТКРЫТ
- Фикс: отключать сигналы в _exit_tree, проверять is_instance_valid()

### BUG-003: agent_entry.gd загружен дважды
- Ошибка: `[Godot Agent] Точка входа agent_entry.gd загружена` ×2
- Причина: плагин активируется дважды (двойной _enter_tree или дублирующий вызов)
- Серьёзность: средняя (двойной dock, двойные подписки)
- Статус: ОТКРЫТ
- Фикс: guard в _enter_tree

### BUG-007: fixture .uid исчезают в установленной копии
- Описание: 181 fixture .uid файлов исчезли (D105)
- Причина: не установлена; вероятно Godot editor пересоздаёт .uid
- Серьёзность: низкая (Godot перегенерирует)
- Статус: ОТКРЫТ (документировано в D105)

### BUG-014: POST /chat возвращает 400 «исчерпан лимит шагов диалога» на первом коротком запросе
- Симптом (лог HTTP + UI): `GET /chat/progress → 200`, `POST /chat → 400`, `POST /chat/live_input → 200`; в панели сообщение `исчерпан лимит шагов диалога` на первом коротком запросе.
- Источник ошибки: `python/modules/assistant/write/operations/turn.py:26-68` (`assistant_turn` проходит `max_turns=8` и на строке 68 поднимает `AppError('unavailable', 'исчерпан лимит шагов диалога')`); `python/channels/http/routes_chat.py:10-11, 20` любую ошибку кроме `conflict`/`stale_plan` отдаёт как HTTP `400`.
- Причины в коде (гипотезы до живой трассировки):
  1. `turn.py:64-67` + `python/substrate/assistant/answer_judge.py:381-383`: обычный ответ без `agent_action` и без `===DONE===` получает blocking-находку `"plain answer is missing ===DONE==="`; `turn.py` не возвращает ответ пользователю (в отличие от `parser_base.py:35`), а до `8` раз шлёт модели `"Исправь ответ; заверши маркером DONE. ..."`.
  2. `python/substrate/assistant/interactive_gateway.py:84-101` + `python/substrate/llm/parsers/deepseek_parser.py:125-128`: `capture` ловит только `parser_base._strip_done_marker`; ответы вида `[Ошибка]: ...` без `_strip_done_marker` (`deepseek_parser.py:314-316`, `parser_base.py:3245, 3288`) дают `done=False` и гоняются в 8-шаговом цикле. При наличии `agent_action` `deepseek_parser` выносит JSON в `actionRaw` и оставляет в `text`/`raw` заглушку `— агент предлагает действие —`, из-за чего `judge` в `turn.py:55` видит `raw` без ```` ```agent_action``` ````.
  3. Исчерпание `max_turns=8` на серии `READ`/отклонённых `WRITE` шагов (`turn.py:36-57`) и игнорирование `chat_id`/`editor_context` из тела `/chat` (`routes_chat.py:16, 20` vs `editor/native/agent_panel_part1.gd:817-825`).
- Серьёзность: высокая (блокирует базовый диалог в `/chat`).
- Статус: ОТКРЫТ (код не патчился по запросу пользователя).

## ОГРАНИЧЕНИЯ (by design)
- NN minilich исключены (F0); doh.py исключён (D36); n8n исключён
- runtime/editor execution — отказные (D92); protected split apply (D92); automatic sync (D93)
- exe неподписанный (AV/SmartScreen); 2 WinError1314 skips
