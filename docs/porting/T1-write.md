# T-B — подтверждаемая write-петля

Этап 6 (финальные paired проверки пройдены; seal/ZIP pending), 2026-11-21. Мандат T1; источник поведения: нативный `main.py`
`confirm_action:2812`, `plan_step:3884`, `rollback:3787`, `_apply_write_step:950`.
Новый MODULE `assistant.write`, effects write. Не изменять принятые нативные
исполнители. Подготовка, preview, подтверждение digest, WAL, применение и
rollback используют существующую воронку. Чат без разрешения остаётся read-only.

Кейсы: native confirm reject/no-pending/policy-stale, план нескольких файлов,
ошибка шага с компенсацией, replay, stale bytes, TTL, traversal, rollback.
Физическая проверка no-unexpected-write обязательна. Кейсы, а не старые тесты.

Измеренный native prepare-корпус: 13 самостоятельно составленных кейсов ×2,
полные raw deltas равны; preparation не меняет файлы. Источник:
`T1-T-B-work-20261121/T-B-native-reference.json`; старые tests не запускались.
Новый внешний baseline проверил mini-seal T-A, каждый ZIP-member и snapshot
репозитория. Mutable dossier:
`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/T1-T-B-work-20261121/`.
Прототипы B/C/D — только внешние, не production и не приёмка.

Отдельно измерено native разрешение Windows ADS-shaped target без apply;
owned guard получил genuine same-ID RED→GREEN. Native bytes не менялись.
Механический лист: [assistant.write](assistant.write.md).

Фактический missing-code RED: 43 failures, 0passed/errors/skips; exact ordered
IDs сохранены. Corpus/tests/SEC-T1-WRITE были созданы до production. ADR0077
описывает generic confirmation, measured ADS refusal и exact K1 reconstruction.

Production write/turn и CLI реализованы:43same-ID GREEN×2/CLI5×2, native13
raw-delta parity, explicit approval/rejection/rollback и no-unexpected-write.
Generic approval сохраняет historical plans; exact K1 reconstruction и inventory
guards имеют реальные same-ID RED→GREEN. Ordinary corpus4/selfcheck ok×2;
три killed/exact-restored mutants. Подробные rejected попытки и byte restoration
записаны в [assistant.write](assistant.write.md). C/D prototypes пока unsubmitted;
structural overlay/provider/browser-live не выданы за готовые.
ADR0080: native missing-parent preparation разрешён и measured×2 без writes;
five genuine RED tests зафиксированы. Parent discovery/pure compiler footprint,
mkdir intent/identity receipt и file-only public counts: five-ID GREEN×2.
Inverse foreign-clone deletion RED исправлен: ancestor proofs до любого inverse;
58same-ID GREEN×2, native script+UID nested move×2/no writes; rejected counts,
LF-only relocation и bound-mutant survivor сохранены. Forward/inverse/unique-bound
mutants killed/exactly restored; reader2746B/63CRLF whole-file exact.
Последние full/gates относятся к прежним bytes: финальная пара начинается заново.
Следующее действие: fresh full/gates×2 на стабилизированных bytes → clients → seal.
Первый directory-final gate: security0, lint1 (test-host runtime/foreign imports
в module tests). Host wiring вынесен в tests/py/transfer_t1/write_composition.py
по существующему ask_composition pattern, assertions и пять IDs неизменны;
checker/production feature imports не менялись. Rejected gate сохранён.
Final-A2 gates и selfchecks assistant.write/write_apply/rollback: exit0×2;
assistant.write verdict ok, unit43/corpus4. Own64×2 и настоящие probe subprocess
plan→denied bare apply→confirm→rollback×2, physical trees exact.
Первый final full:8103passed/6fail/2historic skips. Все failures — шесть прежних
inventory/port-order pins (ADR0081), не GREEN и не готовый пакет. Exact before
bytes и full output/JUnit сохранены в followup-before/ и diagnostics/.
Дополнительно два unsubmitted existing-parent proof RED (ADR0082); production
RED ещё требуется. C prototype35×2/entry6RED остаётся отдельно, без live claims.
Production followup: six full RED + parent2RED + byteguards6RED → same14GREEN×2.
Measured all4effects write; two-write projection дала4fail и сохранена, не
изменялся ни один ToolSpec effect. Exact old-byte reconstruction всех6source.
Public directory-step bound: direct schema RED1pass/3fail→4GREEN×2. Bound356
вместо100 по существующим caps100+256; только2new artifacts changed и byte-equal
actual generator, остальные34physical capability files exact. Dispatcher unchanged.
Все3 followup mutants killed и full byte/SHA/LF/CRLF restored/same-ID GREEN.
No fresh full/gate success ещё не записан; прежний rejected full retained.
ADR0084: genuine A3 selected82/probes×2; limits fail8407. Проверки ordinary и
receipt parents объединены без изменения checker bytes/caps: actual-area RED
→directory/security paired GREEN, editing8400/two original warnings. Compact
forward/inverse/plain mutants killed/exact restored/same-ID GREEN. A3 regression
frozen230/API253/project288×2 прошёл, но source drift отверг весь batch.
## Final verified A4 (2026-11-21)

Full8122passed+2historical WinError1314 skips×2; frozen230/API253/project288×2;
ordered accepted A/K1 IDs и все setup/call/teardown exact, repository unchanged.
Selected clients83×2, genuine probe subprocess plan→denied bare apply→explicit
confirm→rollback×2, files/directories restored exactly. Four static gates×2 and
six genuine selfchecks×2 (write/write_apply/rollback/chat/judge/ask); write43unit/
4corpus, verdict ok. Editing8400; complete checker bytes/caps unchanged.
K1 first extended selfcheck failed because observer omitted PRIOR in PYTHONPATH
and overrode offline config. Complete immutable accepted hook/config-neutral
observer passed; old failure retained, no K1/native/checker source correction.
Closure receipt: T-B-verified-closure-before-docs.json. No real provider/browser
traffic or semantic editor actions, no independent acceptance claimed.

Следующее действие: seal LAST → full physical sibling ZIP verification → T-C.
