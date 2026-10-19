from datetime import datetime, timezone, timedelta
from padeltime.domain import Match, preceding, next_on_court, tracking, event_for

def match(id='a',order=1,**kwargs): return Match(id=id,tournament_id='t',court='c',order=order,players=['1','2','3','4'],**kwargs)
def test_favorite_individual_and_pair_changes():
    assert match().favorite(['1'])
    assert not match().favorite(['9'])
    assert match().model_copy(update={'players':['1','9','8','7']}).favorite(['1'])
def test_court_and_tournament_dependencies():
    first=match(); second=match('b',2)
    other=match('x',0).model_copy(update={'court':'other'})
    other_t=match('y',0).model_copy(update={'tournament_id':'other'})
    assert preceding(second,[other,second,first,other_t])==[first]
    assert next_on_court([second,first]).id=='a'
    first.status='FINISHED'
    assert next_on_court([second,first]).id=='b'
def test_transition_and_schedule_changes():
    old=match(); new=old.model_copy(deep=True);new.status='LIVE'
    assert event_for(old,new)=='started'
    new=old.model_copy(update={'court':'Court 2'})
    assert event_for(old,new)=='schedule_changed'
    assert event_for(old,old) is None
def test_estimate_and_official_floor():
    now=datetime(2026,10,18,10,tzinfo=timezone.utc)
    first=match(status='LIVE');second=match('b',2,official_time=now+timedelta(hours=3),time_kind='not_before')
    result=tracking(second,[first,second],now)
    assert result['state']=='previous_live'
    assert datetime.fromisoformat(result['estimate']['earliest'])>=second.official_time
    assert datetime.fromisoformat(result['estimate']['latest'])>datetime.fromisoformat(result['estimate']['earliest'])
def test_no_false_imminence_and_suspension():
    first=match(status='FINISHED'); second=match('b',2)
    assert tracking(second,[first,second])['state']=='court_clear'
    assert tracking(second,[first,second])['estimate'] is None
    first.status='SUSPENDED'
    assert tracking(second,[first,second])['estimate'] is None
