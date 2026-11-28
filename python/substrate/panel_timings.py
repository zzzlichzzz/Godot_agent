"""Fixed-size local panel timing history. Never serialize free-form diagnostic data."""
import json

from .panel_state import ExternalPanelState


def _arena_event(e):
    if not isinstance(e,dict) or e.get('mode') not in ('direct','battle'):return False
    if type(e.get('variants')) is not int or e['variants'] not in (1,2):return False
    fields={'mode','variants','decision'}
    if e.get('decision') in ('selected','local'):
        fields.update(('selected','other','score_a','score_b','reason'))
        if (e['variants']!=2 or (e.get('selected'),e.get('other')) not in (('A','B'),('B','A'))
                or any(type(e.get(k)) is not int or not 0<=e[k]<=100 for k in ('score_a','score_b'))
                or e.get('reason') not in ('other_continues','equal','only_acceptable','only_verifiable',
                                            'higher_score','not_verifiable')):return False
    elif e.get('decision') not in ('single','skip','third','failed','rejected'):return False
    return e.keys()==fields


def _valid(row):
    times = ('first_text_ms', 'visible_done_ms', 'verify_ms')
    def number(key, limit):
        return type(row[key]) is int and 0 <= row[key] <= limit
    if not isinstance(row, dict):
        return False
    fields = {'kind','outcome','utc_s','total_ms','chars',*times}
    if 'arena' in row:
        fields.update(('arena','arena_posts'))
        events,posts=row['arena'],row.get('arena_posts')
        if (not isinstance(posts,list) or not 1<=len(posts)<=8 or
                any(p is not None and (type(p) is not int or not 0<=p<=65535) for p in posts) or
                not isinstance(events,list) or len(events)>2*len(posts) or not all(map(_arena_event,events))):return False
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
            and row['outcome'] in ('error','stopped','final','pending_read','pending_confirmation')
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
                data = source.read(524_289)  # 64 dispatches, each with up to 8 sends and 16 closed choice records.
            if len(data) <= 524_288:
                prior = json.loads(data)
        except (FileNotFoundError, ValueError, RecursionError):
            pass
        rows = [x for x in prior if _valid(x)][-63:] if isinstance(prior, list) else []
        self.files.write_text(path, json.dumps(rows + [row], indent=2) + '\n')
