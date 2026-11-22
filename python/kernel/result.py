"""kernel/result.py - ответ вызова: ok(value) или error(AppError) (R-15).

Форма одна на все каналы (R-04): ветки перевода протокола не придумывают свою.
"""


def ok(value):
    return {"ok": True, "result": value}


def fail(exc):
    payload = exc.payload()
    payload["ok"] = False
    return payload

