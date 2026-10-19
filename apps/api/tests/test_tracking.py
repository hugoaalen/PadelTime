import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from padeltime.models import Base, TrackedMatch, NotificationEvent
from padeltime.collectors.premier import Snapshot, write_snapshot, AccessRestricted, SourceError
from padeltime.domain import Match, Tournament
from padeltime.ingestion import ingest,subscribe
from padeltime.order import apply_reviewed_order, schedule_fingerprint
from padeltime.worker import CollectorWorker

@pytest.fixture
def engine():
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    return engine

def snapshot(status='SCHEDULED',seconds=0,confirmed=False):
    now=datetime.now(timezone.utc)+timedelta(seconds=seconds)
    day=now.date().isoformat()
    return Snapshot(fetched_at=now,date=day,tournaments=[Tournament(id='t',name='Test',location='Test',category='P1',
        starts=day,ends=day,status='LIVE',timezone='UTC',source_url='https://premierpadel.com/es/tournaments-detail/test')],players=[],
        matches=[Match(id='pp-m-1',tournament_id='t',court='Centre',court_id='c',day=day,order=1,
            order_confirmed=confirmed,players=['p'],status=status)])

def kinds(engine):
    with Session(engine) as db: return [x.kind for x in db.scalars(select(NotificationEvent).order_by(NotificationEvent.created_at))]

def test_transitions_persist_and_deduplicate_across_restart(engine):
    subscribe(engine,'device-123',['p'])
    a=snapshot(); ingest(engine,a,a.fetched_at)
    b=snapshot('LIVE',1);ingest(engine,b,b.fetched_at);ingest(engine,b,b.fetched_at)
    c=snapshot('FINISHED',2);ingest(engine,c,c.fetched_at)
    assert kinds(engine)==['scheduled','started','finished']
    with Session(engine) as db:
        assert db.get(TrackedMatch,'pp-m-1').revision==3
    # New worker/service reuses same DB; older observations cannot roll back state.
    assert ingest(engine,a,c.fetched_at)==0
    assert kinds(engine)==['scheduled','started','finished']

def test_paused_subscriptions_and_score_updates(engine):
    subscribe(engine,'device-123',['p'],False)
    a=snapshot('LIVE');ingest(engine,a,a.fetched_at)
    subscribe(engine,'device-123',['p'],True)
    b=snapshot('LIVE',1);b.matches[0].scores=[[1,0]];ingest(engine,b,b.fetched_at)
    assert kinds(engine)==[]
    c=snapshot('WARMUP',2);ingest(engine,c,c.fetched_at)
    assert kinds(engine)==['approaching']

def test_missing_rows_and_stale_data_do_not_complete_matches(engine):
    subscribe(engine,'device-123',['p'])
    a=snapshot('LIVE');ingest(engine,a,a.fetched_at)
    b=snapshot(seconds=1);b.matches=[];ingest(engine,b,b.fetched_at)
    assert kinds(engine)==[]
    c=snapshot('FINISHED',2)
    assert ingest(engine,c,c.fetched_at+timedelta(minutes=3))==0
    with Session(engine) as db: assert db.get(TrackedMatch,'pp-m-1').payload['status']=='LIVE'

def test_schedule_change_and_confirmed_predecessor(engine):
    subscribe(engine,'device-123',['p'])
    a=snapshot('LIVE',confirmed=True);a.matches[0].players=['other']
    second=a.matches[0].model_copy(update={'id':'pp-m-2','players':['p'],'order':2,'status':'SCHEDULED'})
    a.matches.append(second);ingest(engine,a,a.fetched_at)
    b=a.model_copy(deep=True);b.fetched_at+=timedelta(seconds=1);b.matches[0].status='FINISHED'
    ingest(engine,b,b.fetched_at)
    assert 'previous_finished' in kinds(engine)
    c=b.model_copy(deep=True);c.fetched_at+=timedelta(seconds=1);c.matches[1].court_id='new'
    ingest(engine,c,c.fetched_at)
    assert kinds(engine)[-1]=='schedule_changed'

def test_unconfirmed_order_never_generates_predecessor_alert(engine):
    subscribe(engine,'device-123',['p'])
    a=snapshot('LIVE');a.matches[0].players=[]
    a.matches.append(a.matches[0].model_copy(update={'id':'pp-m-2','players':['p'],'order':2,'status':'SCHEDULED'}))
    ingest(engine,a,a.fetched_at)
    b=a.model_copy(deep=True);b.fetched_at+=timedelta(seconds=1);b.matches[0].status='FINISHED'
    ingest(engine,b,b.fetched_at)
    assert 'previous_finished' not in kinds(engine)

def test_reviewed_order_requires_complete_court_and_evidence(tmp_path):
    import json
    a=snapshot();p=tmp_path/'order.json'
    plan={'date':a.date,'tournament_id':'t','court_id':'c','match_ids':['pp-m-1'],
        'source_url':'https://example.com/official-order','reviewed_at':a.fetched_at.isoformat(),
        'schedule_fingerprint':schedule_fingerprint(a,('t','c',a.date))}
    p.write_text(json.dumps({'courts':[plan]}))
    assert apply_reviewed_order(a,p).matches[0].order_confirmed
    plan['match_ids']=[];p.write_text(json.dumps({'courts':[plan]}))
    with pytest.raises(SourceError): apply_reviewed_order(a,p)

def test_worker_cycle_and_date_rollover(engine,tmp_path):
    captured=[]
    async def collector(day,slug,output):
        captured.append(day)
        result=snapshot();write_snapshot(output,result);return result
    worker=CollectorWorker(engine,tmp_path/'data.json','test',collector=collector)
    write_snapshot(worker.output,snapshot())
    assert asyncio.run(worker.cycle())==90
    assert worker.state['state']=='running'
    assert captured==[datetime.now(timezone.utc).date().isoformat()]
    # Once tournament dates end, do not replay historical live data.
    old=snapshot();old.tournaments[0].ends='2000-01-01';write_snapshot(worker.output,old)
    assert asyncio.run(worker.cycle())==900
    assert worker.state['state']=='idle'
    assert len(captured)==1

def test_worker_backoff_shutdown_and_access_stop(engine,tmp_path,monkeypatch):
    async def blocked(*args):raise AccessRestricted('403')
    worker=CollectorWorker(engine,tmp_path/'data.json','test',collector=blocked)
    write_snapshot(worker.output,snapshot())
    asyncio.run(worker.run())
    assert worker.state['state']=='blocked'
    assert worker.state['next_attempt'] is None
    async def failure(*args):raise RuntimeError('offline')
    worker=CollectorWorker(engine,tmp_path/'data.json','test',collector=failure)
    waits=[]
    async def sleep(seconds):
        waits.append(seconds);raise asyncio.CancelledError()
    monkeypatch.setattr('padeltime.worker.asyncio.sleep',sleep)
    with pytest.raises(asyncio.CancelledError):asyncio.run(worker.run())
    assert waits==[180]
    assert worker.state['state']=='error'
def test_reviewed_order_invalidated_by_schedule_change(tmp_path):
    import json
    a=snapshot();p=tmp_path/'order.json'
    plan={'date':a.date,'tournament_id':'t','court_id':'c','match_ids':['pp-m-1'],
        'source_url':'https://example.com/official-order','reviewed_at':a.fetched_at.isoformat(),
        'schedule_fingerprint':schedule_fingerprint(a,('t','c',a.date))}
    p.write_text(json.dumps({'courts':[plan]}))
    a.matches[0].schedule_label='Not before 7:00 PM'
    with pytest.raises(SourceError,match='changed'):apply_reviewed_order(a,p)
    assert not a.matches[0].order_confirmed
def test_subscribe_scheduled_events_and_pause_are_durable(engine):
    a=snapshot();ingest(engine,a,a.fetched_at)
    subscribe(engine,'device-123',['p'],True,a)
    subscribe(engine,'device-123',['p'],True,a)
    assert kinds(engine)==['scheduled']
    subscribe(engine,'device-123',['p'],False,a)
    b=snapshot('LIVE',1);ingest(engine,b,b.fetched_at)
    assert kinds(engine)==['scheduled']
def test_real_tracking_api_subscription_inbox_and_history(engine,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from padeltime import main
    from padeltime.snapshot import SnapshotProvider
    a=snapshot();path=tmp_path/'data.json';write_snapshot(path,a)
    provider=SnapshotProvider(path)
    provider.worker=SimpleNamespace(state={'enabled':True,'state':'running'})
    monkeypatch.setattr(main,'engine',engine);monkeypatch.setattr(main,'provider',provider)
    client=TestClient(main.app)
    body={'audience':'api-device-123','favorites':['p'],'enabled':True}
    assert client.get('/api/health').json()['collector']['enabled']
    assert client.post('/api/notifications/sync',json=body).json()[0]['kind']=='scheduled'
    ingest(engine,a,a.fetched_at)
    b=snapshot('LIVE',1);ingest(engine,b,b.fetched_at);write_snapshot(path,b)
    inbox=client.post('/api/notifications/sync',json=body).json()
    assert {n['kind'] for n in inbox}=={'scheduled','started'}
    assert len(client.post('/api/notifications/sync',json=body).json())==2
    history=client.get('/api/tracking/history?match_id=pp-m-1').json()
    assert history[0]['after']=='LIVE'
    client.post('/api/notifications/sync',json={**body,'enabled':False})
    c=snapshot('FINISHED',2);ingest(engine,c,c.fetched_at)
    assert 'finished' not in kinds(engine)
