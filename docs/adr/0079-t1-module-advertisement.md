# ADR-0079 — точное объявление нового MODULE assistant.write

T-B добавил один MODULE к историческим 45. Его собственные 43/CLI5 тестов,
корпус4 и genuine selfcheck уже прошли попарно. Полная collection закономерно
добавила один параметр существующего test_selfcheck_unit_selector:
`test_only_three_of_44_target_lists_change_without_reordering[assistant.write]`.
Первый full gate остановился ДО запуска full: этот точный дополнительный ID не
был объявлен в owned observer. Paired frozen230/API253/project288 уже успешны;
никакого full success по этому отклонённому запуску не заявляется.

Реальный RED всех 46 selector IDs показал устаревший literal count45. Минимальная
правка: count46 плюс обязательное присутствие assistant.write. Historical name,
REMOVED, legacy masks, ordering и все остальные predicates сохранены. Observer
разрешает только этот один exact new ID, не весь tests.py.tools namespace.
GREEN должен иметь те же ordered46 IDs; full — exact ordered A+K1 IDs, только
объявленные additions и два исторических skips. Native bytes/gates не изменяются.

Состояние: исполнение, независимая приёмка не заявлена.
