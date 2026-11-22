"""modules/editing/shared/operation_compiler.py - интерфейс компилятора операций (ADR-0004).

Операция плана — данные, а не код фичи: имя (`op`) и функция, которая превращает
отчёт анализа в шаги. Владелец составного инструмента (`editing.write_preview`)
забирает компиляторы через реестр (`ctx.registry.contributions("editing.write_preview")`)
и не импортирует чужой `domain/` (R-11).

Компилятор только строит шаги: он не пишет файлы (R-12), не читает диск и не знает
про воронку. `compile` вызывается с (`analysis`, `texts`, `mode`, `allow_unverified`,
`exclude`, `newlines`) и возвращает словарь плана либо поднимает `AppError`.
"""

import re

#: Имя операции: как имя инструмента — строчные латинские, цифры, подчёркивание.
OP_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class OperationCompiler:
    """Имя операции и её компилятор плана."""

    __slots__ = ("op", "compile")

    def __init__(self, op, compile):
        if not OP_RE.match(str(op or "")):
            raise ValueError("имя операции: ожидалось [a-z][a-z0-9_]*, получено %r"
                             % (op,))
        if not callable(compile):
            raise ValueError("compile операции %r должен быть вызываемым" % (op,))
        self.op = str(op)
        self.compile = compile

    def build(self, analysis, texts, mode, allow_unverified, exclude=(),
              newlines=None):
        """Построить план операции — та же сигнатура, что у функции компилятора."""
        return self.compile(analysis, texts, mode, allow_unverified, exclude,
                            newlines)

    def __repr__(self):
        return "OperationCompiler(op=%r)" % (self.op,)
