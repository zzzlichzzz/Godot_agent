"""Request-local chat inputs and transient state belonging to one project listener."""
import threading
from contextvars import ContextVar


class HttpSession:
    def __init__(self):
        self.lock=threading.RLock();self.pending=None;self.last_receipt=None
        self.editor_snapshot={};self.busy=False;self.turn_context=ContextVar('http_chat_turn',default=(None,None))
        self.approved_read=ContextVar('http_approved_read',default=None);self.ticket=None;self.progress={}

    def report_progress(self,update):
        if self.busy:self.progress=update
