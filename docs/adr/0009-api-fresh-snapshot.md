# ADR-0009. Свежий read-only снимок API без изменения принятого classes()

Статус: принято пользователем, 2026-10-31 (C.11, уточнение start-prompt).

## Контекст

В C.8 `ApiCacheStore.classes()` мемоизирует truthy classes. C.11 требует свежие
данные на каждый `api`-вызов, но запрещает менять принятое поведение classes().
Отдельный version() не устраняет stale classes и может рассогласовать поля.

## Решение

Пользователь разрешил аддитивный `snapshot()` существующего порта `api_cache`:
он читает свежую запись и возвращает `(classes, version)` из одного JSON.
Пути, фолбэки, лимит4МиБ, отказ при ошибке чтения и read-only остаются как C.8.
`classes()`, `_read()`, конструктор и cache_path остаются байт-в-байт; приватный
`_classes` не сбрасывается. `api` вызывает snapshot() один раз вместо двух
независимых чтений classes()/version(). Новый порт не появляется.

## Уточнение доказательств и whitelist

Пользователь также разрешил заменить P3: pathlib в class_api/domain/core.py
должен покраснить frozen lint_arch; чистота shared/inheritance.py проверяется
отдельным новым тестом и собственной мутацией. Сам lint_arch не меняется.

Companion-правки разрешены только для SHA case001 в context/gather/manifest.json
и api/count/list/effects инвентаря в integration test_gd_lint.py, test_node.py,
test_scene.py и contract test_functions_contract.py, test_usages_contract.py.
Исходный whitelist context case001/test_tscn_lint.py сохраняется. Прочие байты
этих файлов и всех принятых механик заморожены.

## Следствия

Свежесть api доказывается заменой/удалением/поломкой файла между вызовами
одного агента; совместимость C.8 — исходными тестами и обратной byte-проекцией.
Портер останавливается на этапе6; независимое принятие/этап7 остаётся аудитором.
