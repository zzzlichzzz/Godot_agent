"""One local decision per completed Arena response, shared by extraction and fallback."""
from python.kernel.errors import AppError
from .arena_parser import ArenaParser
from .panel_read_judgment import panel_read_judgment


class ArenaChoices(ArenaParser):
    def _is_battle_mode(self):
        return self.site['id'] == 'arena_battle'

    def _project_judgments(self, mon):
        if mon.branch_count() < 2: return None
        variants = mon.branch_variants()
        if {k for k,_ in variants} != {0,1}:
            raise AppError('unavailable','Arena: не удалось сопоставить ответы кнопкам A/B.')
        _, _, _, ranked = self.judge.select(variants)
        self._ranked = [(k, panel_read_judgment(j, self.valid_read)) for k,j in ranked]
        key, best = max(self._ranked, key=lambda row: (row[1]['acceptable'], row[1]['score']))
        return key, dict(variants)[key], best, self._ranked

    def _judge_single_current_answer(self, mon):
        return panel_read_judgment(self.judge.judge(mon.current_text()), self.valid_read)

    def submit(self, driver, el):
        mon = self._ensure_monitor(driver)
        self._before = mon.chat_request_count() if mon else None
        return super().submit(driver, el)

    def stream_posts(self):
        mon = ArenaParser._monitor
        if mon and self._before is not None:
            return max(0, mon.chat_request_count() - self._before)

    def _apply_selected_choice(self, driver, mon):
        # The native fallback can reach this after a missing Skip/Battle button.
        # Only a positively ranked Direct branch can authorize continuing with A/B.
        return (not self._is_battle_mode() and (mon.branch_count() == 1 or
                any(j['acceptable'] and k == mon.selected_stream() for k,j in self._ranked))
                and super()._apply_selected_choice(driver, mon))

    def _judge_and_apply_choice(self, driver, mon):
        number = mon.answer_request_count()
        if number == self._number: return self._decision
        self._ranked = []
        ArenaParser._last_choice_summary = ArenaParser._choice_applied_for_request = None
        outcome = super()._judge_and_apply_choice(driver, mon)
        count = mon.branch_count()
        if outcome == 'choice' and count == 2 and not self._is_battle_mode():
            acceptable = [j for _,j in self._ranked if j['acceptable']]
            reason = ('only_acceptable' if len(acceptable)==1 else
                      'equal' if acceptable[0]['score']==acceptable[1]['score'] else 'higher_score')
            self._remember_choice_summary(mon.selected_stream(), self._ranked, reason)
        decision = ('failed' if outcome == 'choice_failed' else 'rejected' if outcome.startswith('reject:') else
                    'single' if count == 1 and outcome == 'choice' else
                    {'choice':'selected', 'no_vote':'local'}.get(outcome, outcome))
        event = dict(mode='battle' if self._is_battle_mode() else 'direct', variants=count, decision=decision)
        if ArenaParser._last_choice_summary: event.update(ArenaParser._last_choice_summary)
        self.events.append(event)
        self._number, self._decision = number, outcome
        return outcome

    def extract_answer(self, driver):
        mon = ArenaParser._monitor
        if not self.net_answer_ready(driver) or mon.is_generating():
            return dict(text='', actionRaw=None, error='Arena: ожидаю завершения ответа.')
        if self._number == mon.answer_request_count() and self._frame is not None:
            return dict(self._frame)
        frame = super().extract_answer(driver)
        if self._decision == 'choice_failed':
            raise AppError('unavailable', 'Arena не подтвердила выбор ветки. Действие не выполнено.')
        if not frame.get('error'):
            # Reading the same response again (including Plan C) must use the voted branch.
            self._frame = dict(frame)
            self._stream = '' if self._decision.startswith('reject:') else mon.current_text()
        return frame

    def answer_stream(self, driver):
        mon = ArenaParser._monitor
        if self._frame is not None and mon and self._number == mon.answer_request_count():return self._stream
        return super().answer_stream(driver)

    def extract_raw_fallback(self, driver):
        frame = self.extract_answer(driver)
        return None if frame.get('error') else frame
