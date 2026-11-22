# Микро-срез SEC-20: распознавание JS-комментариев в проекции стража

Роль: портер. Сессия 78, 2026-11-03. Класс: простой (механический ремонт
проекции стража). Разрешение выдано решением аудитора **D28** в
`docs/deviations.md` — прочитай его до любой правки.

## Среда

- Репозиторий: `D:\vajno\Godot\agent-rebuild` (корень плагина
  `addons\godot_agent`). PowerShell, команды ≤30 с; фоновые — через
  `start /b`. Сначала прочитай `RULES.md` в корне плагина, `AGENTS.md`,
  `docs/deviations.md` (D24–D28) и хвост `docs/WORKLOG.md`.
- Код стража: `tools/security_audit.py`, функция `check_browser_stealth()`
  (середина файла). Сейчас проекция = `re.sub(r"#[^\n]*", "", raw)`, затем
  поиск подстрок forbidden_techniques + pinned/launch/forbidden_paths сканы.
- Досье контекста: `%TEMP%\opencode\c8_audit\b1-final-20261103\` (STOP B-1,
  false-positive SEC-20 на byte-exact native-копиях).

## Задача

1. **Red-пины сначала** — новый файл `tests/py/security/test_sec20_js_comments.py`:
   - фикстура A (реальная подмена): Python-файл с JS-литералом, содержащим
     исполняемый `Object.defineProperty(window, 'hasFocus', ...)` и токен
     `toString` в коде → чек обязан давать 2 нарушения (красный до и после фикса);
   - фикстура B (комментарий-описание): JS-литерал, где `hasFocus`/`toString`
     встречаются ТОЛЬКО в полных `//`-комментариях, код их не содержит →
     до фикса красный, после — зелёный.
   Красные прогоны зафиксируй в досье до правки стража.
2. **Фикс**: в `check_browser_stealth()` после выреза Python-комментариев
   добавить вырез полных JS-строчных комментариев из проекции:
   `re.sub(r"(?m)^[ \t]*//[^\n]*", "", text)`. Проекция общая — она применяется
   ко всем четырём сканам функции (forbidden, pinned needs_visibility_spoof,
   launch webdriver.Chrome, forbidden_paths). Больше ничего в функции не менять.
3. **Green**: `python -B -X utf8 tools/security_audit.py` → `ok / 0`; на
   byte-exact native-копиях в `python/substrate/llm/browser/` SEC-20 зелёный.
   Тестовый файл целиком зелёный.
4. **Мутация**: удали добавленный вырез → фикстура B снова красная (FP
   возвращается) → restore байт-в-байт → зелёный. Двойной полный прогон
   security_audit: результаты идентичны (ok/0).
5. Отчёты и preflight-артефакты храни в досье
   `%TEMP%\opencode\c8_audit\sec20-fix-20261103\`; в `reports/` ничего не
   писать. Последним файлом досье — `SHA256-final.json`.

## Граница (всё остальное запрещено)

Разрешено менять ровно два файла: `tools/security_audit.py` (одна проекция в
`check_browser_stealth`) и новый `tests/py/security/test_sec20_js_comments.py`.
Запрещено: трогать `contract/browser_stealth.json`, forbidden_techniques,
другие чеки и гейты, native/transport-файлы и их комментарии, `selfcheck.py`,
`gen_contract`, `lint_arch`, `check_limits`, таблицу 44 механик PROGRESS,
parity-блоки, ADR, лист `docs/porting/browser.md`, WORKLOG-префикс. Внутри
фикстур теста запрещено писать настоящие вредоносные техники — только токены
и минимальный `Object.defineProperty` как маркер.

## Стоп-условия

- Фикстура A (реальная подмена) перестала быть красной — STOP: проекция
  ослабляет страж, исправлять нельзя, жди аудита.
- Красный до правки вырезается иначе, чем по D28, или нужен второй заход в
  security_audit — STOP и вопрос аудитору.
- Любая байтовая разница вне двух разрешённых файлов — STOP.
- WORKLOG: только append (`ab`, `\r\n`), префикс побайтно не трогать; запись
  одна, в конце сессии, с SHA до/после.

## Вердикт

Только своими прогонами: двойной security_audit ok/0, red→fix→green,
мутация с restore, SHA-таблица. Формат: «принято/не принято» + таблица прогонов
+ список правленных файлов (2) + SHA. Приёмку делает независимый аудитор.
