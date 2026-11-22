# ADR-0020 — J1 B: native judge и lazy composition (D59/D65/D66)

## K1c / D72–D73 (2026-11-20)

D72 санкционирует только локальный ChatGateway import в default_ports и новый
элемент chat_gateway. D65 JudgeRead substitutions и окружающие байты сохраняются;
bootstrap before8451 B/180LF, SHA256
`2c0643473d82cf54355a34704afe784548506c3438db1d2b77221cbc5c096d41`.
After-pin измеряется после вставок и становится pin восстановления для новых
мутаций (не скрытая смена pin). D73 object result описан в ADR-0021.
Ни SEC-02, ни PROC_ALLOWED, ни listen-границы не меняются.

Пользователь 2026-11-15 разрешил обе точные границы sealed B-preflight.
Это реализация уже санкционированного J1, не новая архитектура или NN-клиент.

- `bootstrap.py`: только две замены LibrarianRead → JudgeRead. Новый адаптер
  сохраняет `answer`, активирует 50 aliases лишь внутри `JudgeRead.judge`.
- D59: два identity-bound dotted children принадлежат существующему rollback;
  конфликт не перезаписывается, foreign replacement сохраняется.
- D66: пять named old-pin files: старые 35 aliases остаются точным prefix,
  total50/84 raw LF; единственный новый AST allow — точные path/class/method/import.
- MODULE требует fs+librarian; domain pure, app7 lines. ToolSpec effects="read"
  (kernel representation), contract effects=["read"], idempotent; вход и envelope
  результата закрыты. `action` — явно opaque JSON исходного ответа: unknown fields
  сохраняются для паритета ошибочных ответов и никогда не исполняются.
- Shared librarian lock охватывает profile storage и вызов native; `finally`
  восстанавливает data/history/cache-migration даже при BaseException. Планируемые
  записи — только в памяти; legacy apply/materialize/sync не публичны.
- Tuple→JSON-array и own project-prefix→res:// — явные boundary нормализации R-15;
  shared selfcheck/snapshot/ToolSpec kernel/security checker неизменны.

До реализации: genuine native corpus×2; new103fail/104cases/0errors, legal old
pin5fail/40cases/0errors. Same-ID green/mutations/actual public checks обязательны.


### J1 public judge — final submitted parity (2026-11-15)

J1 полностью реализован и передаётся на независимый аудит: public assistant.judge/judge, read/idempotent, fs+librarian, strict input/result envelope, domain pure/app7. Genuine native74×2 → actual build_agent→agent.call74×2/0diff; final ordinary public corpus74×2/0diff. Actual selfcheck assistant.judge ok/exit0×2 (8unit/74corpus), context.ask ok/exit0×2 (104/213). Final full7923collected/7921passed×2, exact ordered once-only IDs, только два исторических symlink WinError1314 gaps. Frozen230/API253/project288×2, все288 IDs, security/layers/limits/contract×2 green. Четыре actual CLI probes: answer0/invalid_input1/denied1/no-write0; owned state only, no project writes. Final185 new tests green;14 current-submitted mutants killed/0survivors, byte/SHA/LF/CRLF restores/same-ID green. Fifteen Python references+GD harness436437 B byte-exact; part1CRLF824; old35 binding prefix exact,total50/rawLF84. D59/D65–D69 только в санкционированных границах. Native parser/quartet/parser_base/security/check_limits и shared snapshot/selfcheck/generator unchanged. A1/A2/A3 full readback/seal/archive pins exact, только уже раскрытая A1 empty-file inode cohort1430. Rejected invocations/full failures/sample-write defect и initial A2 survivor не удалены; D68 genuine2red→same2green, D69 genuine52fail→same-ID green, fixture isolation repaired only in new B scope, no foreign-parent adoption. Один поздний full run дал importlib source_to_code MemoryError: cause unestablished; unchanged node alone exit0, fresh exclusive full7921pass/2oldskips exit0; failed run retained, not counted. Полный final ZIP включает byte-exact7 mini-seals/8 prior archives, включая rejected incomplete A1 ZIP; их наличие не означает принятия rejected artifacts. Prior real Godot reference probes retained; no public apply/rollback/editor semantic/live/NN/browser/HTTP claim. MODULE_ready=true; independent_acceptance=false, audit pending.
# K1c D72 measured after-pin (2026-11-20)

Two permitted insertions now measured:8592B/182LF/0CRLF SHA256
`d6d933ee8d142efb131372b155992213dadf8390d776f92bdeb4b9d4a9caf2e8`.
Removing exactly both gives original8451 bytes. JudgeRead/D65 unchanged.
All later mutation restoration uses this new legal pin, not superseded before.

D72.4 later full regression explicitly named one additional frozen file before
amendment: tests/py/integration/test_resource_ops.py, exact port-order token
`"librarian", "journal"` → `"librarian", "chat_gateway", "journal"`.
Genuine RED/same-ID GREEN; no other bytes/capability assertions changed.
Kernel/protocol/native/bindings/SEC-02/PROC_ALLOWED/listen boundaries unchanged.
