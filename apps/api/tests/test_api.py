import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DEMO_MODE']='true'
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from padeltime import main
from padeltime.models import Base
from padeltime.provider import MockProvider

def setup_function():
    main.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(main.engine)
    main.provider=MockProvider()
client=TestClient(main.app)
body={'audience':'test-device-123','favorites':['2']}
def test_endpoints_and_missing_order():
    assert client.get('/api/health').status_code==200
    assert len(client.get('/api/players').json())==12
    assert len(client.get('/api/tournaments').json())==3
    assert len(client.get('/api/matches').json())==4
    assert client.get('/api/matches/missing').status_code==404
    assert client.get('/api/tournaments/milan/order-of-play?date=2026-01-01').json()==[]
def test_duplicate_notifications_and_device_isolation():
    first=client.post('/api/notifications/sync',json=body).json()
    second=client.post('/api/notifications/sync',json=body).json()
    assert len(first)==len(second)==1
    assert client.get('/api/notifications/other-device').json()==[]
def test_progression_previous_finished_and_start():
    assert client.post('/api/demo/m2',json={**body,'action':'advance'}).status_code==409
    assert client.post('/api/demo/m1',json={**body,'action':'score'}).status_code==200
    r=client.post('/api/demo/m1',json={**body,'action':'advance'})
    assert r.status_code==200
    assert any(n['kind']=='previous_finished' for n in r.json()['notifications'])
    r=client.post('/api/demo/m2',json={**body,'action':'advance'})
    assert any(n['kind']=='started' for n in r.json()['notifications'])
def test_schedule_change_and_demo_guard():
    r=client.post('/api/demo/m2',json={**body,'action':'reschedule'})
    assert any(n['kind']=='schedule_changed' for n in r.json()['notifications'])
    os.environ['DEMO_MODE']='false'
    assert client.post('/api/demo/m2',json={**body,'action':'advance'}).status_code==403
    os.environ['DEMO_MODE']='true'
def test_approaching_is_conservative_and_deduplicated():
    from datetime import datetime, timezone, timedelta
    target=main.provider.matches[1]
    target.official_time=datetime.now(timezone.utc)+timedelta(minutes=10)
    initial=client.post('/api/notifications/sync',json=body).json()
    assert not any(n['kind']=='approaching' for n in initial)
    main.provider.matches[0].status='FINISHED'
    ready=client.post('/api/notifications/sync',json=body).json()
    repeated=client.post('/api/notifications/sync',json=body).json()
    assert sum(n['kind']=='approaching' for n in ready)==1
    assert len(ready)==len(repeated)
