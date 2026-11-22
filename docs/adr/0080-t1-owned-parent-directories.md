# ADR-0080 — новые родительские каталоги внутри той же воронки

Native transaction prepare разрешает `new/nested/file.gd`: independently authored
paired reference равен, файлов/каталогов проекта preparation не меняет.
Native apply делает makedirs (transaction_actions:333/359); native history затем
чистит пустых родителей (history_manager:693–705), в том числе pre-existing.
Rebuild create требует существующий parent, поэтому реальные five-ID RED tests
обнаружили недостающую механику. Native originals не меняются и не применяются
к пользовательскому проекту как альтернативный writer.

Решение: подготовка перечисляет только отсутствующих родителей, pure compiler
вставляет bounded `mkdir` Steps перед файловыми Steps, digest/expected фиксируют
весь footprint. Единственная воронка пишет intent→mkdir→receipt и откатывает
receipt-confirmed каталоги в обратном порядке. Plain directory identity —
device/inode SHA, не хеш содержимого файла; в публичном applied/files_count
каталоги не выдаются за файлы. Запись потомка повторно проверяет parent receipt.
Удаляется только пустой каталог с matching identity; pre-existing, replaced,
reparse или заполненный чужими файлами каталог никогда не удаляется. Каталог
без receipt означает blocked recovery, а не догадку/ложный ROLLED_BACK.

Это минимальное безопасность-обязательное отличие от native empty-parent cleanup,
а не его улучшение/усечение. Для неизменных R06 лимитов pure generic WAL reader
переносится целиком в kernel; старый editing import остаётся compatibility export.
Поведение/AST reader, native bytes, default gates и historical plans сохраняются.
Five-ID RED→same-ID GREEN×2, parent-proof mutant и full paired regression обязательны.
