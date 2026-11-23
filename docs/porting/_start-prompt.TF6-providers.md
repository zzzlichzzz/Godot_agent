# Мандат T-F.6: провайдеры, каталог, UID-фикс

Контекст: T1/T-F/T-F.5 приняты. Панель (agent_entry.gd) запускается, exe работает,
но пользователь видит: (1) /api/providers → providers=[], models=0 (каталог пуст —
models.dev не доступен без сети), (2) /api/models/refresh висит (пытается фетчить),
(3) sites list есть в API но пользователь сообщает пустой список, (4) WARNING:
AgentStatusBar.tscn:3 ext_resource invalid UID uid://1k5olngje7r8.

## §0. Пути
- Рабочее дерево: D:\vajno\Godot\agent-rebuild\addons\godot_agent
- Установленный агент: D:\vajno\Godot\тест-плагина-ии\addons\godot_agent (git, HEAD ccb0393)
- Натив-источник: D:\vajno\Godot\agent-backups\20261122\godot_agent_native_original\godot_agent
- Досье: %TEMP%\opencode\c8_audit\tf6-<дата>\
- Godot: D:\vajno\Godot\Godot v4.6.3\

## §1. Задачи
1. **Провайдеры**: `agent_api_cache/default_api_cache.json` (2 004 630 B) содержит
   Godot API cache. Провайдерский каталог кэшируется отдельно — проверь model_cache.py
   (байт-точный, substrate/llm/api/): он кэширует каталог после фетча models.dev.
   БЕЗ сети каталог пуст. Решение: (а) разрешить ОДИН fetch models.dev при первом
   /api/providers запросе с явным запросом пользователю, ИЛИ (б) импортировать кэш
   из старого агента (agent-backups/.../agent_api_cache/), ИЛИ (в) добавить статический
   fallback-каталог (встроенный список провайдеров). Решение выбирает исполнитель
   исходя из нативного поведения (main.py: как native обрабатывал пустой каталог).
   В ЛЮБОМ случае: /api/providers должен вернуть непустой список провайдеров
   (aistudio, openrouter, deepseek, qwen — статический минимум).
2. **sites list**: /sites/list возвращает сайты (aistudio, deepseek, qwen). Если панель
   не показывает — проверить формат ответа против agent_panel.gd ожиданий (байт-точный).
   Диагностика показала: 200 с корректными данными — если панель не рендерит,
   искать несоответствие формата в panel части, не в сервере.
3. **"Загрузить" висит**: /api/models/refresh и /api/models/scan пытаются фетчить
   models.dev без ключа. Решение: fail-closed с честным сообщением «Нужен ключ
   провайдера» вместо бесконечного ожидания. Сверить с нативным main.py.
4. **AgentStatusBar.tscn UID**: invalid uid://1k5olngje7r8 — исправить UID в .tscn
   на правильный (прочитать фактический UID из AgentStatusBar.gd.uid) или удалить
   строку ext_resource с невалидным UID (Godot пересоздаст).

## §2. Инварианты
- Запечатанные байты не трогать (chat_routes.py и substrate/assistant/server/* —
  байт-точные, менять ТОЛЬКО через D-запись с обоснованием).
- Сеть: только один fetch models.dev для каталога (без ключей, без провайдеров).
- exe не пересобирать (он работает).
- D-записи D106+ в docs/porting/deviations.md (T-F.5 продолжение).

## §3. Дисциплина
- red-before-code, гейты ×2, selfcheck ×2 (8 модулей), регресс ×2 (состав 8458+свои),
  seal LAST, postseal ZIP, отчёт аудитор.

## §4. Чек-лист
1. Пины; 2. провайдеры непустые; 3. sites рендерятся в панели;
4. refresh/scan fail-closed без ключа; 5. .tscn UID fix;
6. регресс ×2 + гейты ×2 + selfcheck ×2; 7. D106+; 8. seal + ZIP; 9. отчёт.
