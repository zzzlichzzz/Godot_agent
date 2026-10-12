# Ограничение: живой UI-прогон rename из панели редактора

<!-- LIMITATION -->
Блок LIMITATION. Живой UI-прогон панели `agent_panel.gd` (открыть диалог rename,
снять галочку у места переименования, нажать подтверждение и проверить файл на диске)
**невозможен** в окружении каналов конвейера (headless/CLI: нет интерактивного
дисплея и ввода). Поэтому канал «Редактор» закрывает п.4 задачи
документом-ограничением, а не живым логом UI.

## Чем ограничение компенсируется (фактические прогоны)

1. `python -B godot_agent/python/tests/test_gdscript_wiring.py` из `addons/Godot_Agent`
   → **rc=0, «ИТОГО: 109/109»** (прогон 2026-10-12, локальная проверка).
2. Godot-проверка `agent_panel.gd` (headless): **5/5 без ошибок**
   (прогон аудитора конвейера, вердикт фазы 2, run_id 71).
3. Аудит кода пути «снятие галочки → exclude → применение» (аудитор конвейера):
   - `agent_panel.gd:1562` — чеклист «Места переименования…»; id места = адрес для exclude;
   - `agent_panel.gd:1614-1617` — чтение `_rename_excluded` до сброса состояния;
   - `agent_panel.gd:1651-1656` — передача `body["exclude"]` в confirm-запрос;
   - `main.py:587-616` — формирование id мест (`path:line:column`), они же уходят в `_with_exclude`;
   - ядро `symbol_refactor._excluded_places` — точечное сравнение `(path, line)`;
     path-only адрес отвергается `RenameError` (симметрично для места объявления).

## Что это значит для п.4 задачи

Фактический прогон «rename константы обновляет использование в том же файле»
подтверждён по трём независимым путям:

- **API**: `POST /chat` → `POST /chat/confirm_action`, rc=200, обе строки
  (19 объявление, 69 использование) переименованы, `reference_count=1`; скрипт
  `%TEMP%\n8n_hands_scratch\lab_rename_http_proof.py`, `LAB_HTTP_PROOF: PASS`;
- **MCP-мост**: `agent_bridge.py write preview` → `write apply` → `write rollback`, rc=0,
  в диффе ровно два ханка (`@@ -16,7` и `@@ -66,7`), цикл rename→rollback→rename чист;
- **Браузер**: `probe_rename_turret.py` (rc=0) на temp-копии проекта:
  вызовы `/chat` (rc=200) и `/chat/confirm_action` (rc=200, варианты (a) без exclude
  и (b) с exclude) — строки 19/69 обновляются вместе в (a); в (b) снятое место
  остаётся старым осознанно (`skipped_usages`).

Панель редактора использует те же `/chat` и `/chat/confirm_action`
(wiring-тест, 109/109), а её эксклюзивный участок — рендер чеклиста и сбор
`exclude` — покрыт wiring-тестом и аудитом кода; живой UI-клик в headless
недоступен и заменён этим документом.
