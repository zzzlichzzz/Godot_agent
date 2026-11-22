import pytest
from tests.py.engine_cache.observations import cases,observe

ROWS=cases('history')
@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['id'])
def test_history_corpus(row,tmp_path):
    actual=observe(row['input'],tmp_path/row['id'])
    assert actual==row['expected']
    result=actual['result']
    if row['input']['action']=='save':
        assert result['legacy_preserved'] and result['owned_temps_left']==[]
        if row['input'].get('failure'):
            assert result['preserved']
        else:
            assert [event['op'] for event in result['events']]==['fsync','replace']
            assert result['events'][1]['temporary'] and result['events'][1]['same_parent']
    if row['input']['action']=='record_failure':
        assert result['journal_preserved'] and result['snapshots_left']==result['temps_left']==[]
    if row['input']['action']=='batch_failure':
        assert result['first'][0] is False and result['retained']['journal_preserved']
        assert result['retry'][0] is True and result['journal']==[]
