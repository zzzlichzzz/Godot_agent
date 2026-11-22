# assistant.write — T-B

Этап 7 для file/WAL scope T-B; package seal/ZIP ещё публикуются. Group sheet: [T1-write](T1-write.md). Четыре публичных write-tool:
`assistant_plan`, `assistant_confirm`, `assistant_rollback`, `assistant_turn`.
K1 `chat` остаётся read-only; модель никогда не вызывает confirm сама.

Native source: main confirm_action2812/plan_step3884/rollback3787;
transaction_actions.prepare, node_refactor.prepare, file_refactor/symbol_refactor
prepare. Исходные тесты — case provenance, а не исполняемый новый suite;
старые test_transaction_actions/flow и rollback_by_entry уже имеют fate corpus.

Native13×2 exact raw-delta/no-write reference сохранён до production.
Только существующий WAL executor пишет проект; новая preparation не вызывает
native apply. Explicit confirmation связывает immutable preview/digest/project
policy/TTL; rejection/no-pending/replay/stale/foreign edit должны отказать.
Структурные Godot candidate bytes подключаются T-D, не считаются готовыми здесь.

Actual missing-code RED:43failures/0errors/skips; native13×2/no-write,
SEC-T1-WRITE/ADR0077 до production.
Actual production GREEN:43same ordered IDs×2; CLI5same IDs×2;
exact K1 bootstrap reconstruction and two inventory guards RED→same-ID GREEN.
Genuine ordinary corpus4×2 and `selfcheck assistant.write` ok×2:
unit38passed, architecture/limits/contract/security ok. Первое selfcheck blocked
только из-за own corpus cases/ layout; записи перемещены в штатный root corpus,
checker predicates/native reference не изменены.
Три настоящих mutants (approval bypass, ADS guard, rejection expiry) killed;
каждый восстановлен до полного bytes/SHA/LF/CRLF и same-ID GREEN. Первый
mutation selector exit4 не counted; CRLF restoration сначала rejected byte check,
затем восстановлен единственный CR byte в own app и проверен exact original.
ADR0080: native missing-parent preparation×2/no writes; five-ID genuine RED
сохранён. Продолжение: parent discovery/pure mkdir Steps/footprint digest,
receipt-only inverse и file-only public reports: five-ID GREEN×2.
Partial production до продолжения сохранён в directory-resume-before/.
Дополнительный security RED выявил equal-byte foreign-child deletion при inverse;
ancestor receipts теперь проверяются и до inverse в rollback/compensation/recovery.
58same-ID GREEN×2; native nested move×2 включает UID (rejected count сохранён).
Forward/inverse/unique-bound mutants killed/exactly restored; initial bound
mutant survivor сохранён, независимый unique-bound test добавлен и убил retry.
WAL reader exact whole-file2746B/63CRLF; rejected LF-only relocation сохранён.
ADR0081/82: six real full inventory RED + two parent proof RED + six byte guards
→ same ordered14GREEN×2. Все шесть old source files восстанавливаются byte-exact
удалением только разрешённых tokens. Existing parents проверяются plain до
эффекта только tagged assistant.write, не присваиваются и не удаляются.
Actual effects всех4write (WAL/history); rejected two-write assumption сохранён.
ADR0083: public preview schema RED1pass/3fail→four same-ID GREEN×2; bound356,
только2new artifacts изменены, actual generator bytes exact, остальные34physical
capability files unchanged. Port-generated depth — не NTFS/live proof.
Три followup mutants (plain-proof omission, unauthorized inventory count,
schema max100) killed и exact bytes/SHA/LF/CRLF restored; same-ID GREEN.
ADR0084: A3 selected82/probes×2 passed; limits8407 failed. One parent map
сохраняет обе проверки/старые errors, actual-area RED→GREEN×2, area8400;
полные checker bytes/caps unchanged. Compact-source forward/inverse/plain
mutants killed/exact restored. A3 regression source drift retained, not final.
Final A4: actual selfcheck assistant.write verdict ok×2, unit43/corpus4; остальные
write_apply/rollback/chat/judge/ask selfchecks тоже ok×2. Все четыре gates×2;
editing8400/two original warnings, checker bytes/caps unchanged. K1 failed corpus
observer исправлен полным accepted offline-hook PYTHONPATH и neutral config,
не изменением K1/checker/native. Rejected invocation сохранён.
Full8122passed+только2historical WinError1314 skips×2; exact ordered A+K1 IDs и
setup/call/teardown once-only. Selected clients83×2; actual probe plan→denied
bare apply→explicit confirm→rollback×2, raw files/directories exact. Все ранее
описанные rejected runs/survivor сохранены. Evidence: T1-T-B-work-20261121/.
Следующее действие: package mini-seal LAST/full sibling ZIP → T-C. Structural
Godot candidates/editor/provider/browser live не объявлены закрытыми T-B.
