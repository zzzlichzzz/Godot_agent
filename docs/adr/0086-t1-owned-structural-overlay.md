# ADR-0086 — T-D: owned structural overlay, not a second project executor

2026-11-22. Решение по мандату T1 до production integration.

## Измерение

Native A7: семь случаев ×2, реальные Godot 4.6 editor/import/prepare/execute.
Четыре успеха; service-property и float32 отказы; missing-UID публикация с
последующим uid_changed и восстановлением. Raw/transient bytes сохранены.
Нормализованы только доказанные новые UID/unique_id и связанные raw hashes;
empty staged_hash, старые идентичности и поля отказов сохранены.
Это reference evidence, ещё не production parity.
Recovery-mode ×2: import0/explicit native SDK1/no response; не рабочий sandbox.
Обычный editor запускает код проекта: один scratch не доказывает изоляцию.

## Решение

1. Engine-layer adapter: fixed absolute Godot binary из GODOT_AGENT_GODOT_BIN
   или explicit composition injection. Без него structural prepare unavailable;
   никаких executable/command strings из action.
2. Exclusive temporary overlay в plain external state, отдельно от проекта и
   исходников. Reparse/links/escape запрещены до IO; только policy-readable assets,
   без addons/cache/истории. Чужие scripts, binary scenes/resources, GDExtension/PCK
   не исполняются/не подменяются stub-ами. Script references/autoloads fail closed
   до запуска: явный safety gap относительно native, не script-bearing parity.
   Unrelated .gd не запускаются; file planner для их редактирования сохранён.
   Text asset quoted dependencies только canonical policy-readable res:// или
   UID; external/encoded references и Script tokens отказ до engine import.
   Escaped text resources также safety gap, не полная native syntax parity.
3. Fixed argv headless editor import→headless editor harness. В scratch только
   pinned/guarded SDK и primitive harness; actual target hash→native prepare→тот
   же expected hash + actual semantic/dependency fingerprints→execute, с
   configure(plugin)/readiness. Refusal/compensation не становится успешным планом.
4. Adapter возвращает raw target delta только. Дополнительные asset effects,
   before-byte races, forbidden paths, invalid/oversized response/timeout fail
   closed. Клиенту не передаются stdout/stderr/absolute paths.
5. Реальный проект пишет только assistant.write/B: plan→explicit digest/boolean
   confirm→existing executor/WAL→rollback. Overlay writers только owned scratch.
   Bootstrap injects one adapter; ToolSpecs/K1 gateway/base50 unchanged.
6. Native UI/host/updater inactive references. Thin panel transport/UI only;
   SDK execute guard refuses outside owned overlay. SEC05 allowance только два
   exact path/full SHA/UTF8-byte-position records, без directory waiver.
   Candidate nine-ID matrix/three kills не production evidence.

## Приёмка шага

Genuine production RED→same-ID paired GREEN, actual native/production raw semantic
comparison/B composition/owned plugin activation. ≥3 current killed/exact-restored
mutants; fresh full/gates/security/six selfchecks×2; seal LAST/full sibling ZIP.
T-C immutable; no network/provider/browser live or independent acceptance.
