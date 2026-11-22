"""protocol/validation.py - проверка входа по схеме до вызова (R-04, R-15).

Ошибка валидации — всегда `invalid_input` и никогда не содержит путей или
стектрейсов: клиенту нужен список полей, а не внутренности агента.
"""

from python.kernel.errors import AppError
from python.kernel.schema import validate


def validate_args(spec, args):
    if not isinstance(args, dict):
        raise AppError("invalid_input", "аргументы должны быть объектом",
                       hint="Ожидается JSON-объект с полями инструмента")
    problems = validate(args, spec.args)
    if problems:
        raise AppError("invalid_input", problems[0],
                       hint="Исправьте аргументы и повторите вызов",
                       details={"problems": problems[:5]})
    return args

