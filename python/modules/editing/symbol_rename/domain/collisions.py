"""modules/editing/symbol_rename/domain/collisions.py - коллизия нового имени.

Один экземпляр проверки на весь агент (R-04). Перенесён смысл
`symbol_refactor_part2._collision` + `_is_real_conflict` в границах среза:
проверяется файл объявления (для члена скрипта это и есть настоящий конфликт).
Проект-wide `class_name`, `autoload`, InputMap и классы движка сюда не входят —
это долг, записанный в `docs/deviations.md` (нужны `project.godot` и ClassDB).
"""

from python.formats import gdscript


def name_conflict(text, new_name):
    """Текст отказа, если `new_name` уже объявлено в этом же скрипте."""
    if not text:
        return ""
    for item in gdscript.parse(text)["declarations"]:
        if item.get("name") == new_name:
            return ("новое имя %r уже объявлено в этом скрипте (%s, строка %s)"
                    % (new_name, item.get("kind"), item.get("line")))
    return ""
