# TASK_6: ClinePass — провайдер в рекомендованный ряд плагина (+ OpenRouter, + защита ключа)

**Постановка:** владелец, 13.10.2026, через цикл v3 («Вход: MCP»).
**Статус:** отправлено в цикл; план — за ядром/аудитором, правки — за супервайзером.

## Цель

1. Добавить в реестр провайдеров плагина запись **ClinePass** — одним из
   первых («рекомендованный» ряд).
2. Подтвердить **OpenRouter** в том же ряду (сейчас он первый и
   `DEFAULT_PROVIDER_ID`), включая пометку о бесплатных моделях.
3. Ключ ClinePass **никогда** не попадает в репозиторий (инвариант).

## Факты

- Реестр: `python/api/providers.py`, список `PROVIDERS` — ручные проверенные
  записи идут первыми; каталог models.dev (`catalog_records()`) — вторым
  рядом, `from_catalog=True`. Порядок `PROVIDERS` = порядок показа в панели.
- ClinePass (официально, docs.cline.bot/getting-started/clinepass):
  - подписка Cline, $9.99/мес, 2–5× лимиты на открытые кодинг-модели;
  - использование вне Cline — через Cline API: `https://api.cline.bot/api/v1`,
    `Authorization: Bearer <ключ>`, OpenAI-совместимый `/chat/completions`
    (docs.cline.bot/api/overview);
  - ключ: app.cline.bot → Settings → API Keys;
  - слаги моделей: `cline-pass/glm-5.3`, `cline-pass/kimi-k3`,
    `cline-pass/deepseek-v4-pro`, `cline-pass/deepseek-v4.1-flash`,
    `cline-pass/mimo-v2.5(-pro)`, `cline-pass/minimax-m3`,
    `cline-pass/qwen3.8-max`, `cline-pass/qwen3.7-max`, `cline-pass/qwen3.7-plus`
    и др. (список живой — тянется с `/models`, не зашивать);
  - квота: окна 5 часов / неделя / месяц.
- Этим же ключом уже работает n8n-цикл (креденшел «Cline API (ClinePass)»,
  модели `cline-pass/deepseek-v4.1-flash`, `cline-pass/mimo-v2.6-flash`).

## Конвенции записи

Поля как у соседних записей: `id`, `name`, `base_url`, `needs_key`,
`env_names`, `models_path`, `models`, `default_model`, `extra_headers`,
`note_ru`, `note_en`, комментарии-обоснования. `env_names` — по документации
`CLINE_API_KEY` (+ наш шаблон `GODOT_AGENT_<ID>_KEY` — сверить с api_keys.py).
`models_public` / `live_pricing` — **только после живой проверки именно этого
поля**, не по документации; `verified` не ставить. «Бесплатного» не обещать.

## Ключ — вне репозитория (требование владельца)

- Хранилище ключей — вне репо: `python/api/api_keys.py` →
  `%APPDATA%\Godot_agent\api_keys.json`; env `GODOT_AGENT_CONFIG_DIR` —
  подмена для тестов; наружу — только маска (`redact()`).
- Из n8n-базы ключ **не извлекать**: секрет не должен попасть ни в контекст
  агентов, ни в историю исполнений n8n.
- В файлы репозитория (тесты, доки, отчёты, логи) — только фиктивные ключи
  (`sk-or-v1-ABC…`) и маски. В командах — ссылка на переменную окружения,
  не значение.
- Живая проверка — допустима (если владелец положит ключ в env на машине):
  список моделей + минимальный запрос; в отчёт — только результат.
- Перед коммитом: `python -B n8n/scripts/check_no_secrets.py` (по n8n —
  0 ошибок; по затронутым файлам — 0 ошибок) и `git diff` глазами на
  ключеподобные строки. `.gitignore` корня закрыт: `.env`, `*.key`,
  `api_keys.json`, `secrets/`.

## Приёмка

- Оффлайн-тесты плагина зелёные (`python -B selfcheck.py`, профильные
  `test_api_*`, `test_gdscript_wiring.py`).
- Version bump плагина по конвенции; отчёт с координатами `file:line`.
- Явное подтверждение: ключа в диффе и в новых файлах нет.
