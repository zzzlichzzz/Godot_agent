# ADR-0076 — mini-seal на существующем физическом досье

Дата: 2026-11-21. T1 §2; независимый аудит ещё не состоялся.

Первый T-A snapshot-copy отказан WinError1314: directory junction нельзя
скопировать через `Path.symlink_to` без отсутствующей symbolic-link привилегии.
Нативная истина: принятый K1 `seal_and_package.py` запечатывает существующее
досье, не пересоздаёт ссылки. Повышать права, терять ссылки или обходить проверки
не требуется и запрещено.

T-A seal выполняется LAST на `c8_audit/T1-20261121`; production bytes перед ним
копируются как regular files в `submitted`. Все имеющиеся reparse entries
сохраняются; их targets и native tags записаны. ZIP находится только в отдельном
`-postseal`, каждый member проверяется по CRC/bytes/SHA/EOL/type/target; Windows
metadata остаётся в seal, не выдаётся за lossless ZIP metadata. Источник и
production inventory до/после равны. После seal досье не изменяется: T-B получает
новый внешний рабочий каталог.

Незавершённый `T1-T-A-20261121` остаётся отклонённой незапечатанной копией с
физическим inventory; он не удалён и не объявлен принятым. Реальный junction
test сначала RED/WinError1314, затем тот же ID GREEN без новых прав. Предикаты,
accepted native bytes, K1 evidence и глобальная безопасность не меняются.
