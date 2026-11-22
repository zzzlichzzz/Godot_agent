# ADR-0019 — D60: шесть точных лимитов native reference J1

Решение D60 санкционировано аудитором в J1a, 2026-11-13. Реализуется
2026-11-15 в A2; не является приёмкой MODULE `assistant.judge`.

## Решение

Для неизменённых native references R-08 сохраняет байты и EOL. Вместо
разрезания исходников `tools/check_limits.py` применяет явный exact-path класс:

| Путь | Строк |
|---|---:|
| `python/substrate/editing/file_refactor.py` | 1457 |
| `python/substrate/code_intel/symbol_refactor_part1.py` | 824 |
| `python/substrate/code_intel/symbol_refactor_part2.py` | 718 |
| `python/substrate/code_intel/symbol_refactor_part3.py` | 714 |
| `python/substrate/assistant/answer_judge.py` | 492 |
| `python/substrate/scene/scene_deps.py` | 412 |

Только полное совпадение пути даёт измеренный лимит. Переполнение даже на
одну строку запрещено. Все другие файлы новых каталогов и одноимённые файлы
в иных каталогах остаются под default400. Entry caps module/tools150/app80,
старые class caps, module3000/area8000/8400 и folder warnings не меняются.

## Доказательства

Pending draft `test_native_j1_limits.py` включён побайтно в новые A2 tests.
До checker edit: genuine26 collected/13failed/13passed/0errors; исходный
checker6373 B/SHA256 `fcb7bd45d36e831c4c40bec6102a3559f939df06a9d3f7d197943abfa3282367`.
Первые pytest setup errors отвергнуты, tests/checker не менялись при исправлении
owned basetemp runner. Same-ID green и killed guard mutants фиксируются в
досье отдельно от red и отдельно от A2 native/canonical differential.

Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/`.
Ранние seals A1/STOP read-only, production алиасы/D59 и публичный MODULE вне D60.


### Actual same-ID/mutation/gate evidence (2026-11-15)

A2 reference-read/prepare проверен, не public MODULE. Six sources152941 B/EOL byte-exact; native214+supp1 ×2/canonical214+supp1 ×2/0diff, full snapshots no-write. Genuine A2220/221 red → same221green, D6013/26 red → same26green; restored all249green. 6 A2+4 D60 mutants killed/0final survivors, exact bytes/SHA/LF/CRLF restore/same-ID green. Первый ambiguity survivor сохранён: wrongly named old negative-case не создавал candidates; gap закрыт новым genuine native supplement×2 и теми же mutant bytes, frozen214 не переписан. Full non-live7649passed ×2 + ровно два historical WinError1314 skips, no added skips/xfails; collected7651 и executed IDs/order exact. Frozen230/API253/project288 ×2, все288 manifest IDs. Gates/security ×2 green. Real Godot4.6:4 native/canonical reference probes/8 processes, default harness,0diff/no source writes/owned validation leftovers0; это headless structural validation, не semantic editor apply/rollback и не public judge probes. Actual selfcheck assistant.judge fail/exit1 (missing MODULE) ×2; actual probe judge unknown_tool/exit1 ×2. Actual context.ask selfcheck ok/exit0 ×2,104unit/213corpus. D60 exact-six caps реализованы minimal two-insertion checker delta, old constants/caps сохранены; D59/A3/B/+15 aliases/MODULE/public corpus не реализованы. Rejected baseline assumptions, freeze path, pytest basetemp setup, outer120s partial canonical capture, singular collected-item receipt, double-q collect verbosity и initial survivor сохранены, не засчитаны как successful evidence. A1 accepted record read-only; mini-seal/ZIP фиксируют integrity, не самостоятельную приёмку.

Досье: C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1-A2-20261114/
Следующее действие: После A2 mini-seal/ZIP: A3 symbol_refactor native cases/observations ×2 до missing-code red; затем B/D59/adapter/MODULE.
