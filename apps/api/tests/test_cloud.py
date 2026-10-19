import copy
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from padeltime.cloud_state import valid_signature,evolve
from padeltime.collectors.premier import Snapshot
from padeltime.domain import Match,Tournament
from padeltime import cloud

def capture(status='SCHEDULED'):
    now=datetime.now(timezone.utc)
    return Snapshot(fetched_at=now,date=now.date().isoformat(),players=[],tournaments=[Tournament(id='t',name='Test',location='Test',category='P1',starts='2026-01-01',ends='2026-12-31',status='LIVE')],
        matches=[Match(id='pp-m-1',tournament_id='t',court='c',court_id='1',day=now.date().isoformat(),order=1,order_confirmed=False,players=['p'],status=status)])

def test_signature_missing_expired_and_tampered():
    secret='a'*32;signature=hmac.new(secret.encode(),b'1000',hashlib.sha256).hexdigest()
    assert valid_signature(secret,'1000',signature,now=1001)
    assert not valid_signature(secret,'1000',signature,now=2000)
    assert not valid_signature(secret,'1001',signature,now=1001)
    assert not valid_signature('','1000',signature,now=1001)

def test_serverless_replay_dedup_and_paused_devices():
    device={'favorites':['p'],'enabled':True,'events':[]}
    a=capture();previous,updates=evolve(None,a,{'u':device})
    assert updates['u']['events'][0]['kind']=='scheduled'
    device=updates['u'];b=capture('LIVE');current,updates=evolve(previous,b,{'u':device})
    assert updates['u']['events'][0]['kind']=='started'
    _,replayed=evolve(current,b,updates)
    assert replayed=={}
    paused={**device,'enabled':False}
    assert evolve(previous,b,{'u':paused})[1]=={}

def test_stale_capture_rejected_and_unconfirmed_order_safe():
    a=capture();a.fetched_at-=timedelta(minutes=10)
    with pytest.raises(ValueError):evolve(None,a,{})
    a=capture('LIVE');a.matches[0].players=[]
    a.matches.append(a.matches[0].model_copy(update={'id':'pp-m-2','players':['p'],'status':'SCHEDULED','order':2}))
    previous,updates=evolve(None,a,{'u':{'favorites':['p'],'events':[]}})
    a.matches[0].status='FINISHED'
    _,updates=evolve(previous,a,updates)
    assert not any(e['kind']=='previous_finished' for d in updates.values() for e in d['events'])

def test_cloud_refuses_unconfigured_or_unsigned_calls(monkeypatch):
    monkeypatch.delenv('FIREBASE_PLAN',raising=False)
    client=TestClient(cloud.app)
    assert client.get('/api/health').status_code==503
    assert client.post('/api/collect').status_code==401
    assert client.post('/api/push/register',json={'token':'x'*30}).status_code==401

def test_authenticated_identity_ignores_supplied_audience(monkeypatch):
    records={'catalog':capture().model_dump(mode='json'),'devices':{}}
    records['catalog']['players']=[{'id':'p','name':'Player','country':'ES','rank':None}]
    monkeypatch.setattr(cloud,'uid',lambda request:'verified-uid')
    monkeypatch.setattr(cloud,'get_record',lambda collection,id:copy.deepcopy(records['catalog'] if collection=='catalog' else records['devices'].get(id)))
    monkeypatch.setattr(cloud,'device_list',lambda:copy.deepcopy(records['devices']))
    def put(identity,patch):records['devices'].setdefault(identity,{'favorites':[],'events':[]}).update(patch)
    monkeypatch.setattr(cloud,'put_device',put)
    client=TestClient(cloud.app)
    body={'audience':'someone-else','favorites':['p','unknown'],'enabled':True}
    assert client.post('/api/notifications/sync',json=body).status_code==200
    assert records['devices']['verified-uid']['favorites']==['p']
    assert 'someone-else' not in records['devices']
    assert client.post('/api/push/register',json={'token':'x'*30}).status_code==200
    assert client.post('/api/push/disable').status_code==200
    assert records['devices']['verified-uid']['token'] is None

def test_cloud_stale_live_scores_not_presented_as_live():
    snapshot=capture('LIVE');snapshot.fetched_at-=timedelta(minutes=6)
    shown=cloud.represented(snapshot,snapshot.matches[0])
    assert shown['status']=='UNKNOWN'
    assert shown['tracking']['state']=='stale'

def test_missing_then_returning_fixture_keeps_revision_ledger():
    a=capture('LIVE');data,_=evolve(None,a,{})
    gone=capture();gone.matches=[]
    data,_=evolve(data,gone,{})
    returned=capture('FINISHED');data,events=evolve(data,returned,{'u':{'favorites':['p'],'events':[]}})
    assert data['matches'][0]['revision']==2
    assert events['u']['events'][0]['kind']=='finished'


def test_closed_app_test_queue_retry_expiry_and_delivery(monkeypatch):
    records={'u':{'token':'x'*30,'enabled':False}}
    sent=[]
    monkeypatch.setattr(cloud,'current_device',lambda request:('u',copy.deepcopy(records['u'])))
    monkeypatch.setattr(cloud,'device_list',lambda:copy.deepcopy(records))
    monkeypatch.setattr(cloud,'put_device',lambda identity,patch:records[identity].update(patch))
    client=TestClient(cloud.app)
    assert client.post('/api/push/test-closed').json()['queued']
    assert client.post('/api/push/test-closed').status_code==429
    def fail(*args):raise RuntimeError('Temporary FCM failure')
    monkeypatch.setattr(cloud,'send_push',fail)
    assert cloud.deliver_tests()==0
    assert records['u']['pending_test']
    monkeypatch.setattr(cloud,'send_push',lambda token,event:sent.append(event))
    assert cloud.deliver_tests()==1
    assert records['u']['pending_test'] is None
    assert cloud.deliver_tests()==0
    assert len(sent)==1 and sent[0]['id'].startswith('test-')
    records['u']['pending_test']={**sent[0],'created_at':(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()}
    assert cloud.deliver_tests()==0
    assert records['u']['pending_test'] is None
    assert len(sent)==1

def test_closed_app_test_requires_subscription(monkeypatch):
    monkeypatch.setattr(cloud,'current_device',lambda request:('u',{}))
    assert TestClient(cloud.app).post('/api/push/test-closed').status_code==409

def test_signed_collector_delivers_tests_even_when_collection_blocked(monkeypatch):
    calls=[]
    monkeypatch.setattr(cloud,'valid_signature',lambda *args:True)
    monkeypatch.setattr(cloud,'deliver_tests',lambda:calls.append('test') or 1)
    monkeypatch.setattr(cloud,'acquire',lambda:('owner',None))
    r=TestClient(cloud.app).post('/api/collect')
    assert r.json()['skipped'] and r.json()['test_push_submitted']==1
    assert calls==['test']
