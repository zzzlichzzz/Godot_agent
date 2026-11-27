"""One foreground request per listener. Stop never waits for the browser lock."""
from collections import deque
from contextvars import ContextVar
from threading import Event, Lock
import re


class TurnControl:
    def __init__(self):
        self.lock = Lock()
        self.active = None
        self.local = ContextVar('cancel_http_turn', default=None)
        # A local stop POST can reach the listener before the long POST.
        self.stopped = deque(maxlen=64)
        self.finished = deque(maxlen=64)

    @staticmethod
    def valid(key):
        return isinstance(key, str) and re.fullmatch('[a-f0-9]{32}', key) is not None

    def begin(self, key):
        event = Event()
        with self.lock:
            if key in self.stopped: event.set()
            self.active = (key, event)
        return self.local.set(event)

    def cancelled(self):
        event = self.local.get()
        return event is not None and event.is_set()

    def stop(self, key):
        with self.lock:
            if key in self.finished: return False
            if key is not None and key not in self.stopped: self.stopped.append(key)
            if self.active and (key is None or self.active[0] == key):
                self.active[1].set()
                return True
            return key is not None

    def finish(self, token):
        # Linearization point under session.lock: the outcome belongs to the
        # originating chat; a subsequent stop cannot revoke its publication.
        with self.lock:
            cancelled = self.cancelled()
            if self.active[0] is not None: self.finished.append(self.active[0])
            self.active = None
        self.local.reset(token)
        return cancelled
