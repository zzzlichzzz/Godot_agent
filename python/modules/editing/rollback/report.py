"""modules/editing/rollback/report.py - итог отката (ADR-0005).

`restored` — пары «файл — хеш исходных байтов»: равенство этих хешей
`expected[path]` и есть доказательство, что воронка замкнута.
"""


def result(entry_id, plan_id, restored):
    """Конверт `ROLLED_BACK`: план, запись и восстановленные файлы."""
    return {
        "entry_id": entry_id,
        "state": "ROLLED_BACK",
        "plan_id": plan_id,
        "restored": list(restored),
        "removed": [],
        "files_count": len(restored),
    }
