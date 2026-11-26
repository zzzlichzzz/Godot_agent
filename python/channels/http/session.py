"""Request-local chat inputs and transient state belonging to one project listener."""
import threading
from contextvars import ContextVar
from .turn_clock import TurnClock


class HttpSession:
    def __init__(self):
        self.lock=threading.RLock();self.pending=None;self.last_receipt=None
        self.editor_snapshot={};self.busy=False;self.turn_context=ContextVar('http_chat_turn',default=(None,None))
        self.approved_read=ContextVar('http_approved_read',default=None);self.ticket=None;self.progress={}
        self.transcript_writer=None;self.pending_chat=None
        self.clock=None;self.timing_writer=None

    def bind_turn_chat(self, chat_id):
        _, snapshot = self.turn_context.get()
        if snapshot is not None:
            self.turn_context.set((chat_id, snapshot))

    def remember(self, chat_id, entries):
        if self.transcript_writer is None:
            return {}
        from flask import request
        from python.kernel.errors import AppError
        try:
            self.transcript_writer(chat_id, entries, request.headers['X-Agent-Token'])
            return {}
        except (OSError, AppError, ValueError, TypeError, RuntimeError):
            return {'transcript_warning': 'Не удалось сохранить этот ход. Скопируйте нужные сообщения до закрытия чата.'}

    def finish_preview_note(self, text):
        owner,self.pending_chat=self.pending_chat,None
        return self.remember(owner,[('system',text)]) if owner else {}

    def report_progress(self,update):
        if self.busy:self.progress=self.clock.observe(update) if self.clock else update

    def report_read(self,tool,outcomes):
        if self.clock:self.clock.data.update(read_tool=tool,read_results=outcomes)

    def start_turn(self, continued):
        self.clock=TurnClock(continued);self.progress={};self.busy=True

    def finish_turn(self, outcome):
        from python.kernel.errors import AppError
        clock,self.clock=self.clock,None
        self.busy=False;self.progress={}
        if self.timing_writer:
            try:self.timing_writer(clock.finish(outcome))
            except (AppError, OSError, ValueError, RuntimeError):pass  # Diagnostic IO never retries a model turn.
