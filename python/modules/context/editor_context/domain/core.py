"""modules/context/editor_context/domain/core.py - снимок редактора, без IO.

Домен не знает ни про сокет, ни про файлы: он получает ответы моста и схемы,
проверяет их `kernel.schema.validate` и складывает фрагмент секции. Проблема
схемы - отказ с путём поля (`open_scenes[0].revision`), а не частичный снимок:
именно ради `None` в nullable-полях чинили union в валидаторе (ADR-0007).
Правила: R-11 (без os/pathlib/socket), R-14 (смысл на Python), R-15.
"""

from python.kernel.errors import AppError
from python.kernel.schema import validate

#: Примитивы снимка: ответ каждого сверяется со своей `result_schema`.
PING = "editor_ping"
STATE = "editor_state"
SELECTION = "editor_selection"
VERBS = (PING, STATE, SELECTION)


def check(verb, result, schema):
    """Ответ моста по схеме примитива: `[]` - годен, иначе отказ с путём поля."""
    problems = validate(result, schema)
    if problems:
        raise AppError("engine_down", "ответ моста %r не по схеме" % (verb,),
                       hint="Мост и словарь примитивов разошлись (ADR-0007)",
                       details={"reason": "bad_result", "problems": problems[:3]})


def snapshot(state, selection):
    """Фрагмент секции `editor`: только то, что нужно контексту."""
    return {"available": True,
            "reason": None,
            "open_scenes": state.get("open_scenes") or [],
            "selection": {"node_path": selection.get("node_path"),
                          "scene": selection.get("scene"),
                          "script": selection.get("script"),
                          "properties": selection.get("properties") or []}}


def collect(client):
    """Снимок через мост: три примитива, каждый сверен со своей схемой."""
    answers = {}
    for verb in VERBS:
        result = client.call(verb)
        if not isinstance(result, dict):
            raise AppError("engine_down", "ответ моста %r - не объект" % (verb,),
                           details={"reason": "bad_result",
                                    "problems": ["(ответ): ожидался object"]})
        check(verb, result, client.result_schema(verb))
        answers[verb] = result
    return snapshot(answers[STATE], answers[SELECTION])

