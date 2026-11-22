# tests/

Кросс-модульные тесты и e2e. Тесты конкретной фичи лежат в её папке
(`python/modules/<область>/<фича>/tests/`) - R-02.

- `py/unit` - чистые функции без IO;
- `py/contract` - схемы и коды ошибок;
- `py/integration` - модули вместе (fs + store);
- `py/e2e` - реальный Godot и реальный мост;
- `py/snapshots` - сравнение со старым агентом (R-09);
- `py/kernel` - ядро: валидатор схем (`validate`, `unknown_schema_types`),
  union-типы и тотальность;
- `py/security` - инварианты SEC (побег пути, воронка записи, секреты);
- `py/formats` - парсеры форматов (`.gd`, `.tscn`);
- `py/code_intel` - анализ кода: `search`, `functions`, `usages`;
- `py/tools` - тесты самих инструментов разработчика (`gen_contract`, `selfcheck`):
  проверяется вердикт, а не только код механик;
- `gd/` - тесты GDScript-стороны;
- `fixtures/` - корпус входов и тестовые проекты (R-07).
