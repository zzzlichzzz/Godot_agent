"""One panel dispatch. Only elapsed times and closed labels cross the log boundary."""
from time import monotonic, time


class TurnClock:
    def __init__(self, continued):
        self.start = monotonic()
        self.data = dict(kind='read' if continued else 'message', utc_s=int(time()),
                         first_text_ms=None, visible_done_ms=None, verify_ms=None, chars=0)

    def elapsed(self):
        return min(86_400_000, max(0, round(1000 * (monotonic() - self.start))))

    def observe(self, update):
        now = self.elapsed()
        stream = update.get('stream', '')
        marker = stream.rstrip().rsplit('\n', 1)[-1].strip() == '===DONE==='
        verifying = update.get('phase') == 'проверяю, что ответ дописан'
        for field, seen in (('first_text_ms', bool(stream)), ('visible_done_ms', marker), ('verify_ms', verifying)):
            if seen and self.data[field] is None:
                self.data[field] = now
        self.data['chars'] = min(200_000, max(self.data['chars'], update.get('chars', 0)))
        if marker and verifying:
            return dict(update, phase='Маркер получен · сверяю ответ')
        return update

    def finish(self, outcome):
        return dict(self.data, total_ms=self.elapsed(), outcome=outcome)
