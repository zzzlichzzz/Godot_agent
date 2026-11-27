# Browser SEC-19/SEC-20 — D30: многострочные site flags

**Статус:** готов к независимой приёмке D30 repair; финальный CRLF red/restore/green и батарея выполнены, не accepted.
**Дата:** 2026-11-04. Отдельное разрешение пользователя получено после STOP B-3.

## Цель и граница

Прежний страж пропускал три native-подмены False→True: kimi/arena/arena_battle.
Однострочный положительный контроль ловится. Причина — regex не пересекает LF.
Разрешён `tools/security_audit.py`, новые security-тесты и запись решения;
контракт stealth, маскировка, B-1/B-2 production и остальные гейты неизменны.
SEC-03 canonical exclusive-probe/reflection helper и D28 projection сохраняются.

## Спецификация и кейсы

Новый статический AST-разбор Python dict с полями id/needs_visibility_spoof:
порядок, LF/CRLF и переносы не влияют; known network-only и unknown не получают
True; нелитеральные id/boolean не доказывают admission. Код не исполняется.
Прежний regex остаётся для старых JS/text fixtures; D28 comments не расширяются.
Пустая skeleton-заглушка без registry пока допустима; это не полнота runtime.

Инварианты прежние SEC-19/SEC-20/R-21, их содержание не расширяется. Новый
публичный инструмент/effect не появляется. D30 фиксирует реализацию обещания,
а не разрешение новой техники. Тесты — `tests/py/security/test_sec19_site_flags.py`.

## Доказательства

До правки: external `b3-delivery-20261104/guard-probes.json` — три escapes,
native flags exact; inline control red. Native/production/guard не менялись.
Своя новая база: B-1+B-2 109/109 ×2; security237/2 skip; четыре гейта ok/0
(check_limits ok с двумя прежними warnings). Досье создаётся exclusive.

## Следующее действие

Независимому аудитору проверить `guard-final-sandbox/` red/restore/green и
повторить28security cases/свою мутацию в новой внешней папке, без правки B1/B2.

Предыдущее продолжение уже сохранило guard-red28/19expected failures/9passed,
guard-green28passed и sandbox suppression red19. После них normalize_guard.py
восстановил CRLF и доказал SEC-03 prefix exact; эти логи не перезаписываются.

## Финальное доказательство

Submitted guard16153B/343CRLF/0LF, SHA256
`c59e4faf35f1e71e91cd80de9efe590cfc1bd9b661870b494ae7c174188167f4`.
Byte-copy sandbox удаляет только CRLF D30call:28executed/19red/9pass;
raw restore exact→28green. Production guard не мутировался. Реальный
sites kimi False→True также дал SEC20red1; byte-exact sites restore→auditok.

Full security267executed=265passed+2genuine WinError1314skips×2;
B1+B2regression109×2, B3focused45×2, full non-live5478executed/5476pass/2skips.
lint573/0, limits573/2прежних warnings, contract28/0, audit×2ok/0.
Boundary доказывает прежние guard bytes после удаления только D30helper+call:
SEC03/D28/остальные проверки exact. Contract/B1/B2/all foreign files frozen.
Досье общее с B3: `b3-delivery-20261104/`, финальная SHA-печать; никаких
новых masking techniques, site admissions или runtime sandbox promises.


## Приёмка D30 аудитом (2026-11-04, сессия 78)

Мои прогоны: kimi False→True в production sites.py — SEC-20 red 1 (CLI), byte-pin+corpus
red 2, restore ok/0; удаление D30-call — 19/28 sec19-красных, restore ok/0. Формулировка
«самом по себе не sandbox» — принято: статический контроль literal-флагов, D31 явно
не обещает runtime-полноты. Принято.
## Долг закрыт: независимое мутационное покрытие reflection-фильтра SEC-03 (2026-11-04, долг-срез debt-cases)

В tests/py/security/test_sec03_nonlistening_probe.py добавлен test_reflection_built_name_is_the_only_deny: globals()['soc'+'ket'] = fake_socket_impl в __init__ до канонического probe facade — единственная отсечка name-фильтр guard (строка node.id in {"globals",…}). Файл 71+1=72 зелёный (промпт ждал 73+1; фактический прежний корпус 71 — зафиксировано в досье). Мутация набора → set() красит ровно новый кейс; restore byte-exact guard SHA c59e4faf35f1e71e… → 72/72 зелёный. D30-заметка не менялась.


## Долги 1–2: принято аудитом (2026-11-04, сессия 78)

Debt-cases срез проверен независимым аудитом: кейс reflection-only rebind добавлен, мутация набора → set() красит ровно новый кейс (mutant e447909b…), restore byte-exact → 72/72. Гейты ok/0·ok/2·28/0·ok/0; security_audit ×2 ok/0; гигиена 44/86/0/pg335.
