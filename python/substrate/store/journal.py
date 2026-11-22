"""substrate/store/journal.py - WAL планов и записей (ADR-0005, R-12).

Единственное место, где агент пишет план: `<state_dir>/<plan_id>.jsonl`, одна
строка — одно состояние. Каталог приходит из `runtime/config.py` и лежит ВНЕ
проекта, поэтому предпросмотр не меняет ни байта рабочего дерева.

`write_prepared` делает `flush` + `fsync`: часть 2 будет искать план на диске
после падения процесса, и «запись в буфере» там равна отсутствию плана.
"""

import json
import os


class FileJournal(object):
    """Файловый журнал: пишет и читает JSONL по `plan_id`."""

    def __init__(self, state_dir):
        self.state_dir = os.path.abspath(str(state_dir))

    def path(self, plan_id):
        return os.path.join(self.state_dir, "%s.jsonl" % plan_id)

    def write_prepared(self, plan, detail=None):
        """Записать `PREPARED`: план целиком + момент создания."""
        record = {"state": "PREPARED", "plan": plan,
                  "detail": dict(detail or {})}
        return self._append(plan["plan_id"], record)

    def read(self, plan_id):
        """Все записи плана по порядку; пустой список — плана нет."""
        path = self.path(plan_id)
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def append(self, plan_id, record):
        """Любая следующая запись состояния: APPLYING, RECEIPT, COMMITTED…"""
        return self._append(plan_id, dict(record))

    def modified_at(self, plan_id):
        """Момент создания плана (mtime файла журнала) — для `confirm_ttl`."""
        return os.path.getmtime(self.path(plan_id))

    def plan_ids(self):
        """Все планы в каталоге: recovery проходит по ним при старте."""
        if not os.path.isdir(self.state_dir):
            return []
        return sorted(name[:-6] for name in os.listdir(self.state_dir)
                      if name.endswith(".jsonl"))

    def _append(self, plan_id, record):
        if not os.path.isdir(self.state_dir):
            os.makedirs(self.state_dir, exist_ok=True)
        path = self.path(plan_id)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False,
                                    sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path
