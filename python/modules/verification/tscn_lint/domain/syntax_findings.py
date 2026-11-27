"""C.8 maps neutral parse events to literal findings; no parser or IO.

Specification port: ba0535d4, tscn_lint.py:518-579,633-697.
"""
from python.formats import tscn_lint_syntax as fmt

MESSAGES = {'property_events_1': 'строка %d: неизвестный заголовок секции [%s] — в .tscn бывают только [gd_scene], [ext_resource], [sub_resource], [node], [connection] и [editable]. Godot упадёт с «Parse Error». Убери эту секцию или замени на правильную.', 'property_events_2': "строка %d: нет знака '=' между именем свойства и значением («%s»). Godot упадёт с «Parse Error» при загрузке сцены. Пиши: свойство = значение.", 'property_events_3': 'строка %d: значение свойства %s не в кавычках и не является числом, true/false или конструктором вида Vector3(...): «%s». Строку пиши в кавычках, иначе Godot упадёт с «Parse Error».', 'balance_events_1': 'строка %d: значение свойства не закрыто (не хватает закрывающей скобки или кавычки) до начала следующей секции — Godot упадёт с «Parse Error» при загрузке сцены. Допиши недостающую «)», «]», «}» или кавычку в этом значении.', 'balance_events_2': 'строка %d: лишняя закрывающая скобка «%s» в значении свойства — Godot упадёт с «Parse Error». Убери её или допиши парную открывающую.', 'balance_events_3': 'строка %d: значение свойства не закрыто (не хватает закрывающей скобки или кавычки) до конца файла — Godot упадёт с «Parse Error» при загрузке сцены. Допиши недостающее, например position = Vector3(0, 5, 0) вместо position = Vector3(0, 5, 0.'}


def _scan_property_syntax(text):
    return [MESSAGES[code] % values for code, values in fmt.property_events(text)]


def _scan_value_balance(text):
    return [MESSAGES[code] % values for code, values in fmt.balance_events(text)]
