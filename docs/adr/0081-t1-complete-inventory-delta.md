# ADR-0081 — остаточные T-B inventory-пины после настоящего full RED

2026-11-21. Решение в рамках автономного мандата T1, не независимая приёмка.

Full `T-B-directory-final-A2-full-1`: 8103 passed, 6 failures, 2 прежних skips.
Все шесть failures — прежние точные inventory/port-order assertions:
`test_gd_lint`, `test_node`, `test_resource_ops`, `test_scene`, `test_tscn_lint`,
`test_verify` в `tests/py/integration/`. Output/JUnit/ordered IDs сохранены.

Разрешён только полный ранее объявленный D77/D78 delta: четыре sorted tool names
`assistant_confirm/assistant_plan/assistant_rollback/assistant_turn`, count30→34,
write effects всех четырёх по существующим ToolSpec (WAL/history тоже эффект);
один `native_planner` port после
`chat_gateway`. Все остальные байты, assertions, корпуса и bootstrap неизменны.
В `test_tscn_lint` меняется только live projection, не pinned corpus names.

Перед правкой сохранены byte/SHA/LF/CRLF всех шести файлов. Новая byte-reconstruction
проверка разрешает только эти tokens; после patch сохраняется исходный EOL.
Шесть настоящих RED IDs → same-ID GREEN×2; mutant должен быть killed и exact
restored. После стабилизации повторяются full×2, gates×2, clients, затем seal LAST.

Нативный источник новых действий/confirm/rollback указан в ADR0077; эта ADR не
разрешает новую семантику, изменение native bytes или широкое обновление fixtures.

Rejected two-write assumption сохранён отдельно: first followup14 дал4fail/10pass.
Actual registry и common_tool_defs подтверждают write для всех четырёх; четыре
исходных новых contracts не меняются. Byte guard разрешает именно измеренные
четыре effects, не startswith assistant или filtered list.
