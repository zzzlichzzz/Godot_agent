# ADR-0018 — J1b: headless reference, точечные SEC-03/04 и ресурс

Граница **санкционирована** аудитором 2026-11-13 (D62–D64), AST-уточнение
`str(proc.pid)` подтверждено пользователем 2026-11-14. Реализация и приёмка
проверяются отдельно; эта запись не объявляет A1/MODULE завершёнными.

## Решение

- D62: новый распознаватель в `tools/security_audit.py` разрешает только один
  конкретный `subprocess.run` в точном пути
  `python/substrate/verification/godot_headless_validation.py`, не весь файл.
  Приёмник — `Name(subprocess)`, настоящий одиночный top-level импорт без alias.
  Один позиционный argv — List из строковых Constant, `str(Name)` или только
  `str(Attribute(Name(proc), pid))`. Иные Attribute/Subscript/Starred запрещены.
  Нет `shell`/`**kwargs`; значения kwargs — Constant или
  `subprocess.DEVNULL`/`subprocess.PIPE`. Пропуск — точный UTF-8 byte-offset.
  Все другие run/bind/listen/HTTPServer и parse error остаются red; B-1 неизменён.
  Это завершение собственного timeout-child списочной командой без shell,
  не общее послабление `.run` и не новый listener.
- D63: разрешён ровно один bare top-level `import subprocess` в этом же пути.
  From-import, alias, multi-import, второй/nested импорт и соседние verification
  файлы не получают исключения. `shell=True` по-прежнему запрещён везде.
  `PROC_ALLOWED` и существующее B-1 исключение не расширяются.
- D64: native `agent_headless_validator.gd` переносится verbatim в
  `python/agent_headless_validator.gd`: 1701 B,
  SHA256 `799ec9e26f43f65aa8208a1cf1e5379b8d5c3ca80fbd3ad7a0a8e87251da895e`,
  LF39/CRLF0. Так работает неизменённый default lookup из verification.
  Примитив читает ResourceLoader, пишет только owned overlay result и quit;
  бизнес-логика, OS launcher и ветка `_MEIPASS` не меняются.
  Замыкание J1: 15 Python references + 1 GD resource = 436437 B, алиасов +15.

## Доказательства

До checker/code: новые D62/D63 матрицы и D64 default/explicit-path tests,
genuine red; затем те же IDs green, killed guard mutations с exact restore.
A1 frozen native118×2 остаётся неизменным; canonical differential×2,
actual gates и настоящие Godot-пробы дополняют (не заменяют) oracle.
Досье: `C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/answer-judge-J1b-A1-20261114/`.
Предыдущие STOP/seal/ZIP read-only; независимая приёмка не делегируется автору.


### J1b / A1 фактическая проверка (2026-11-14)

D62/D63 implemented с exact-path/byte-offset AST-исключениями, B-1/PROC_ALLOWED сохранены; D64 exact1701 B/default+explicit green. Genuine red192 collected/135failed/57passed/0errors → 192 same-ID green, все прежние121 failure ID зелёные; native118×2/canonical118×2/0diff. Real Godot4.6:4 own-sandbox default-harness probes/8 engine processes/0diff/no source writes. Mutants:15 checker+2 D64 killed/0survivors, exact SHA/EOL restore/same-ID green. Full non-live×2:7400passed/2 historical WinError1314 skips; frozen230/API253/project288×2, gates×2 и post-resource gates0. Actual selfcheck assistant.judge fail/exit1 (missing MODULE), probe unknown_tool/exit1; context.ask ok/exit0,104unit/213corpus. Aliases0, MODULE/D59/D60/A2 не implemented. A1 reference mini-seal готовится, MODULE не ported, independent acceptance pending. Все rejected setup/invocation/scope records сохранены, native originals/NN/browser-live/production HTTP нетронуты.

Подэтап reference не закрывает historical verification.check/live fate или assistant.judge MODULE. Frozen230 membership сохранён: browser141 + B-1 AST72 + B217; D51 detector34 дополнительно в full/security/mutations. Мини-seal — integrity, не самостоятельная приёмка.
Следующее действие: После A1 mini-seal: A2 native cases/corpus×2 для scene/editing/actions; D60 genuine red exact-six caps перед переносом.
