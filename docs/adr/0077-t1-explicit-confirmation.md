# ADR-0077 — T1 write preview and explicit confirmation

Решение исполнителя в автономном мандате T1; independent acceptance pending.

43 самостоятельно составленных теста получили genuine missing-code RED;
native13 paired preparations сняты до production, project bytes неизменны.
`assistant_plan/turn` создают только preview/WAL; `assistant_confirm` отдельно
проверяет digest/project-policy/immutable TTL и boolean approved. Модель не
может сама дать approval. `assistant_rollback` требует owned plan/receipt.

Kernel helper остаётся generic: marker requires_confirmation=true требует
matching USER_CONFIRMED. Нет зависимости kernel от assistant или scene.
Existing write_apply вызывает helper до эффекта; untagged historical plans
не меняются. Только существующий funnel/executor пишет проект. Две пустые
строки в write_apply убираются вместо повышения лимита editing area8400;
все старые непустые строки и newline style сохраняются.

Native preparation фактически допускает ADS-shaped res://safe.txt:stream,
измерено read/prepare без apply. Adapter fail-closed отказывает colon в target
до native и повторно в delta compiler; declaration :line[:column] и текст
файла остаются данными. Owned five-ID path guard RED→GREEN; native неизменён.

Default composition добавляет ровно NativePlanner import/port; removal этих
двух строк обязано восстановить полный frozen K1 bootstrap8592B/SHA256,
а removal исторических двух K1 строк — frozen D65 bootstrap8451B/SHA256.
Старый guard сначала должен реально упасть, затем получить только exact
scoped reconstruction, без ослабления старых SHA/count/identity predicates.

R06: app — orchestration; operations — cohesive prepare/turn и отдельный
tools_assistant_<tool>.py для каждого из четырёх инструментов. No global
gate relaxations, native-port/K1/base50 bytes unchanged. Structural Godot
overlay подключается T-D, не объявляется готовым этим решением.
