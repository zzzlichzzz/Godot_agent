"""modules/editing/write_apply/ports.py - порты применения плана (ADR-0003, R-12).

- `writer` — `ProjectWriter`: единственная запись в проект;
- `journal` — WAL (`read`, `append`, `modified_at`, `path`);
- `backups` — сырые байты до правки (`put`, `get`, `token`, `exists`);
- `lock` — эксклюзивный лок проекта (`acquire`, `release`).
"""


class ProjectWriter(object):
    def read_raw(self, rel):
        raise NotImplementedError

    def write_raw(self, rel, data):
        raise NotImplementedError


class PlanJournal(object):
    def read(self, plan_id):
        raise NotImplementedError

    def append(self, plan_id, record):
        raise NotImplementedError

    def modified_at(self, plan_id):
        raise NotImplementedError


class Backups(object):
    def put(self, plan_id, index, data):
        raise NotImplementedError

    def get(self, token):
        raise NotImplementedError


class ProjectLock(object):
    def acquire(self):
        raise NotImplementedError

    def release(self):
        raise NotImplementedError
