# T-A — добор нативных godot_tools

Этап 7 (native substrate-замыкание), 2026-11-21. Мандат: `_start-prompt.T1-full-completion.md`.

Native29×2/no diff, corpus+new tests before implementation; missing-code/SEC/
limits/scoped-import genuine RED preserved externally. Eight native copies exact
SHA/EOL. D74/D75+ADR0074 implemented; base50/K1 gateway unchanged. Actual same-ID
GREEN×2/security×2/limits×2 successful. First capture rejected AST-identity observer
defect preserved; complete ast.dump makes parity deterministic, source unchanged.

Три настоящих мутанта убиты; для каждого восстановлены исходные bytes/SHA/LF/
CRLF и тот же упорядоченный набор ID стал GREEN. Полные прогоны full2/full3:
8044 passed + ровно два исторических symlink skip, одинаковые ordered IDs и
setup/call/teardown, физический снимок проекта не изменён. Frozen230/API253/
project288 также пройдены дважды. Провал full1 — внешний observer читал env после
его очистки тестом; pytest INTERNALERROR/exit3 и JUnit сохранены, не выданы за
успех. Observer теперь запоминает путь при импорте; тесты/предикаты/native bytes
не менялись. Genuine security/layers/limits/contract и selfcheck assistant.judge/
editing.split_gd уже дали OK×2. Принятие независимым аудитором не заявляется.

Клиентская проверка: настоящий `probe.py split_gd_scan` OK×2. Пинованный native
`split_gd._godot_check` вызван с известным Godot4.6 и внешним owned fixture:
exit0×2, исходный .gd и пользовательский проект не изменены. Неполный первый
client fixture без plugin.cfg корректно отказан и сохранён; исправлен только
fixture. Применение записей и browser/provider-live здесь не проверялись.

Финальный повтор `T-A-final`: security/layers/limits/contract ×2 exit0;
подлинные selfcheck `assistant.judge` и `editing.split_gd` ×2 exit0/OK.
Физический снимок production во время повторов не изменился. Закрыт именно
byte-exact/lazy substrate-пакет, не T-B запись, T-C сервер или T-D UI.
Mini-seal LAST и проверка каждого физического ZIP-member выполняются последними;
публикационная квитанция находится вне запечатанного досье. Независимое принятие
не заявляется.

Первый clone-package отказан WinError1314 на directory junction, не скрыт и не
запечатан. D76/ADR0076: accepted K1 in-place процедура вместо новых link privileges;
реальный junction RED → тот же ID GREEN. Досье `c8_audit/T1-20261121` будет immutable
после seal LAST; ZIP/publication только в sibling `T1-20261121-postseal`, а T-B
получит новый внешний каталог. Все rejected bytes/inventories сохранены.

## Цель и источники

Byte-exact `split_gd`, `split_refactor`, `node_refactor`, `arch_map`,
`gather_context`, `gd_functions`; источники — нативный `python/godot_tools`.
Кейсы: `test_split_gd*`, `test_split_refactor`, `test_node_refactor*`,
`test_high_level_*`, `test_function_card`; судьбы в `tests-map.md` сохранены.
Не копировать тесты. Нативные исполнители не получают самостоятельного
разрешения записи: активная запись только через rebuild WAL/funnel.

## Нативные зависимости / решения

`gather_context:11` импортирует `log_reader`: T-C byte-port этой зависимости
выполняется в T-A, без переноса сетевого сервера. `librarian:1238–1246` и
нативный `agent_bridge:500–504` действительно вызывают `function_card`:
возврат D48-исключения требуется для `func:...`, не для NN. Доказательства,
точные пины, RED/GREEN и решения записаны в D74 и внешнем досье.

## База

`C:/Users/Lich/AppData/Local/Temp/opencode/c8_audit/T1-20261121/`.
Fresh census 6078 файлов, принятый K1 snapshot 6077: добавлен только мандат,
чужие изменения WORKLOG/selfcheck-report сохранены. Числа 6122/6063 в старом
аудиторском тексте не являются fresh census. Issued WORKLOG-prefix 1032789 B
проверен SHA; K1 seal и каждый физический ZIP-member проверены, bad=0.

## Следующее действие

In-place seal LAST/ZIP по D76 → publication.json → новый T-B каталог и формальный RED.
