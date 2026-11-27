# ADR-0083 — public preview schema учитывает directory steps

2026-11-21, исправление контракта новой assistant.write после ADR0080.

Компилятор уже допускает ≤100 file deltas и ≤256 parent steps. PLAN_RESULT
сохранил прежний steps_count.maximum=100. Четыре реальные Agent preview calls
с port-generated deltas:99/100/101/256 parents, no project effects. Agent не
валидирует result schema: initial observer4pass сохранён, dispatcher не меняется.
Прямая kernel.schema проверка actual result дала1pass/3fail по тем же четырём IDs.
Это protocol contract defect, не доказательство реальных глубоких NTFS paths.

Разрешено только steps_count.maximum=MAX_FILES+MAX_PARENTS=356 в новой
PLAN_RESULT; ToolSpec limits.max_files=100 и compiler parent cap256 неизменны.
Артефакты assistant_plan/assistant_turn регенерируются по ToolSpec;31 прежний
и остальные2 новых contracts остаются byte-exact. Native/corpus не меняются.

Нужны same-ID GREEN×2, max-bound mutant killed/exact restored, свежие full/gates
после стабилизации. Нет расширения executor, входного action limit или эффектов.
