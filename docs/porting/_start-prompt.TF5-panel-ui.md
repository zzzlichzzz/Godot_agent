# Мандат T-F.5: вход панели = нативный agent_entry + fixtures/.gdignore

Контекст: T1 и T-F приняты; установленная копия (тест-плагина-ии/addons/godot_agent,
git, коммит db80ae45) содержит T1-аудиторскую панель (plugin.gd → editor/t1_panel.gd),
а нативный UI (editor/native/agent_entry.gd, байт-точный, 24 233 B) не подключён:
его docstring «ПРОТОТАЙП, НЕ ПОДКЛЮЧЁН» устарел — нативный plugin.cfg (v0.9.1,
бэкап godot_agent_native_moved/godot_agent/plugin.cfg) указывал script="agent_entry.gd".
Пользователь видит минимальную панель и просит прежний UI.

## §1. Задачи
1. plugin.cfg: script="plugin.gd" → script="editor/native/agent_entry.gd"
   (путь от корня аддона). plugin.gd/t1_panel.gd остаются в дереве (не удалять).
2. fixtures/.gdignore (пустой файл) — редактор Godot перестанет сканировать
   66 МБ тестового корпуса (исчезнут warnings "Detected another project.godot"
   и Parse Error по намеренно битым .tres/.gd фикстурам). Headless-пробы,
   запускающие Godot с --path внутрь отдельных fixture-проектов, не затронуты.
3. Верификация активации: копия синтетического проекта (plugin.cfg + plugin.gd
   + editor/**) + headless --editor --quit-after 40, GODOT_AGENT_STATE_DIR
   внешний; ожидание: отсутствие SCRIPT ERROR, наличие печати активации
   agent_entry (найди его print в хвосте agent_entry.gd), dock создан.
   Плюс Godot --check-only на agent_entry.gd и на всех .gd, которые он
   цепляет первыми (lifecycle-аналог нативный: editor/native/agent_*).
4. Live-сервер: exe уже работает (T-F.2, 30 859 253 B 969854a4...); после
   включения нативной панели подтвердить её связку с сервером: token
   user://godot_agent_token.txt, стартовый экран нативной панели показывает
   провайдера, /chat/confirm_action принимает подтверждение из панели.

## §2. Инварианты и запреты
- Все байт-точные файлы (T-A…T-E, K1c, librarian, J1) не изменять.
- plugin.gd/t1_panel.gd не удалять; откат = вернуть script="plugin.gd".
- Без сети; PyInstaller 6.21.0 уже есть; exe не пересобирать без нужды
  (если пересборка обязательна — STOP с обоснованием).
- STOP-ы решаешь сам (делегирование T1 §2), D-записи с D101 в
  docs/porting/deviations.md, WORKLOG append-only CRLF
  (пин на момент старта — prefix-assert от 1 103 888/bcada22bc9bc89b0),
  seal LAST, postseal ZIP, отчёт аудитор.

## §3. Чек-лист
1. Пины + tree-identity; 2. plugin.cfg правка + fixtures/.gdignore;
3. активация headless ×2 (нет SCRIPT ERROR); 4. --check-only agent_entry;
5. регресс ×2 (состав 8427+свои); 6. гейты ×2; 7. связка панель↔exe
(старт/токен/confirm_action из нативной панели — WSGI/сокеты);
8. D101+; 9. seal LAST + ZIP; 10. отчёт.
