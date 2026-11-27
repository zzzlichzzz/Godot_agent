"""Keep Arena's native branch protocol, evaluating only a Godot-read project view."""
from .arena_parser import ArenaParser


class ArenaDelivery(ArenaParser):
    def __init__(self, judge):
        super().__init__()
        self.judge = judge

    def _project_judgments(self, mon):
        return self.judge.select(mon.branch_variants()) if mon.branch_count() >= 2 else None

    def _judge_single_current_answer(self, mon):
        return self.judge.judge(mon.current_text())

    def send_message_and_get_response(self, *args, **kwargs):
        reply = super().send_message_and_get_response(*args, **kwargs)
        if isinstance(reply, dict) and ArenaParser._last_choice_summary:
            return dict(reply, battle_choice=dict(ArenaParser._last_choice_summary))
        return reply
