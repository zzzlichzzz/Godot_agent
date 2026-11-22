"""runtime/context.py - узкий ModuleContext (ADR-0003).

Модуль видит только это: профиль, свои настройки, лог, идентификаторы, часы,
порты по имени и (для агрегаторов) вызов чужого инструмента. Никаких адаптеров,
глобального состояния и прямого доступа к другим модулям.
"""

from datetime import datetime, timezone

from python.kernel.errors import AppError
from python.kernel.ids import new_id


class SystemClock:
    def now_iso(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModuleContext:
    def __init__(self, profile, settings=None, ports=None, path_policy=None,
                 logger=None, ids=None, clock=None, call_tool=None,
                 registry=None):
        self.profile = profile
        self.settings = dict(settings or {})
        self.path_policy = path_policy
        self.logger = logger
        self.ids = ids or new_id
        self.clock = clock or SystemClock()
        self._ports = dict(ports or {})
        self._call_tool = call_tool
        #: Реестр: агрегатор берёт вклады отсюда, а не импортом модуля (ADR-0004).
        self.registry = registry

    def port(self, name):
        try:
            return self._ports[name]
        except KeyError:
            raise AppError("unavailable",
                           "порт %r не подключён в профиле %r" % (name, self.profile),
                           hint="Проверьте requires_ports в манифесте модуля") from None

    def bind_caller(self, fn):
        """Агрегатор получает вызов чужих инструментов после сборки."""
        self._call_tool = fn

    def call_tool(self, name, args):
        if self._call_tool is None:
            raise AppError("unavailable", "вызов чужих инструментов недоступен",
                           hint="Модуль не агрегатор: ctx.call_tool не подключён")
        return self._call_tool(name, args)
