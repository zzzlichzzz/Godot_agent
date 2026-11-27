"""Fixed-size local panel timing history. Never serialize free-form diagnostic data."""
import json

from .panel_state import ExternalPanelState


def _valid(row):
    times = ('first_text_ms', 'visible_done_ms', 'verify_ms')
    def number(key, limit):
        return type(row[key]) is int and 0 <= row[key] <= limit
    if not isinstance(row, dict):
        return False
    fields = {'kind','outcome','utc_s','total_ms','chars',*times}
    if 'read_tool' in row:
        fields.update(('read_tool','read_results'))
        results = row.get('read_results')
        if (row.get('kind') != 'read' or row['read_tool'] not in ('read','tree','functions','scene','ask',
                'search','usages','context','analyze_rename') or not isinstance(results,list) or len(results)>5
                or any(label not in ('ok','truncated','empty','missing_names','budget','error','directory',
                    'not_found','denied','invalid_input','unavailable') for label in results)):
            return False
    return (row.keys() == fields
            and row['kind'] in ('read','message','rename_report')
            and row['outcome'] in ('error','final','pending_read','pending_confirmation')
            and number('utc_s', 2**40) and number('chars', 200_000) and number('total_ms', 86_400_000)
            and all(row[t] is None or number(t, row['total_ms']) for t in times))


class TimingLog:
    def __init__(self, profile, project):
        self.files = ExternalPanelState(profile, project)
        self.path = self.files.profile / 'agent_turn_timings.json'

    def append(self, row):
        if not _valid(row):
            raise ValueError('Invalid timing record')
        path = self.files.check(self.path)
        prior = []
        try:
            with path.open('rb') as source:
                data = source.read(32_769)
            if len(data) <= 32_768:
                prior = json.loads(data)
        except (FileNotFoundError, ValueError, RecursionError):
            pass
        rows = [x for x in prior if _valid(x)][-63:] if isinstance(prior, list) else []
        self.files.write_text(path, json.dumps(rows + [row], indent=2) + '\n')
