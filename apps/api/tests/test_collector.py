import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
import pytest
from padeltime.collectors.premier import (tournament_records, normalize_tournament,
    normalize_schedule, explicit_time, Snapshot, write_snapshot, PublicClient, SourceError)
from padeltime.snapshot import SnapshotProvider
from padeltime.domain import preceding, tracking

FIXTURES=Path(__file__).parent/'fixtures'
def fixture(): return json.loads((FIXTURES/'premier-day.json').read_text())
def tournament():
    return normalize_tournament(tournament_records((FIXTURES/'premier-page.html').read_text())[0])

def test_decode_public_page_metadata():
    t=tournament()
    assert t.id=='pp-t-274'
    assert t.name=='MILANO P1'
    assert t.source_url.endswith('/milano-p1-2')
    with pytest.raises(SourceError): tournament_records('<html>Consent required</html>')

def test_stable_player_ids_and_scores():
    players,matches=normalize_schedule(fixture(),tournament(),'Europe/Berlin','2026-10-18')
    m=matches['pp-m-18888']
    assert 'pp-p-14945' in m.players
    assert 'pp-p-72142' not in players
    assert m.scores==[[4,6],[6,3],[6,2]]
    assert m.status=='FINISHED'
    assert m.order_confirmed is False
    assert len(players)==4

def test_header_overrides_conflicting_session_timestamp():
    source=fixture()['data']['courts'][0]['matches'][0]
    timestamp,kind=explicit_time(source,'Europe/Berlin')
    assert timestamp.isoformat()=='2026-10-18T15:00:00+00:00'
    assert kind=='not_before'
    source['header']='Following previous match'
    assert explicit_time(source,'Europe/Berlin')==(None,'unknown')

def test_unconfirmed_order_never_produces_dependency_or_eta():
    _,matches=normalize_schedule(fixture(),tournament(),'Europe/Berlin','2026-10-18')
    m=next(iter(matches.values())).model_copy(update={'status':'SCHEDULED'})
    assert preceding(m,list(matches.values()))==[]
    result=tracking(m,list(matches.values()))
    assert result['state']=='order_unconfirmed'
    assert result['estimate'] is None
    assert result['remaining'] is None

def test_bad_source_and_missing_identity_rejected():
    raw=fixture(); raw['status']=False
    with pytest.raises(SourceError): normalize_schedule(raw,tournament(),'Europe/Berlin','2026-10-18')
    raw=fixture();del raw['data']['courts'][0]['matches'][0]['teams'][0]['players'][0]['player_id']
    with pytest.raises(SourceError): normalize_schedule(raw,tournament(),'Europe/Berlin','2026-10-18')

def test_atomic_snapshot_and_stale_live_not_reported(tmp_path):
    players,matches=normalize_schedule(fixture(),tournament(),'Europe/Berlin','2026-10-18')
    match=next(iter(matches.values())).model_copy(update={'status':'LIVE'})
    snapshot=Snapshot(fetched_at=datetime.now(timezone.utc)-timedelta(minutes=3),date='2026-10-18',
        players=list(players.values()),matches=[match],tournaments=[tournament()])
    path=tmp_path/'data.json';write_snapshot(path,snapshot)
    p=SnapshotProvider(path)
    assert p.metadata()['stale']
    assert p.matches[0].status=='UNKNOWN'
    assert p.read().matches[0].status=='LIVE'

def test_robots_exclusion_auth_errors_and_redirects_stop():
    def handler(request):
        return httpx.Response(200,text='User-agent: *\nDisallow: /api/',headers={'content-type':'text/plain'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(SourceError,match='excludes'):
                await PublicClient(client).request('https://api-prod.premierpadel.com','/api/blocked')
    asyncio.run(run())
    for code in (401,403,429,302,500):
        def handler(request):
            return httpx.Response(404) if request.url.path=='/robots.txt' else httpx.Response(code)
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(SourceError,match='HTTP'):
                    await PublicClient(client).request('https://api-prod.premierpadel.com','/api/matches')
        asyncio.run(run())
def test_dependencies_do_not_cross_days():
    from padeltime.domain import Match
    a=Match(id='a',tournament_id='t',court='c',day='2026-10-17',order=1,players=[])
    b=a.model_copy(update={'id':'b','day':'2026-10-18','order':2})
    assert preceding(b,[a,b])==[]

def test_snapshot_api_isolated_from_demo_and_alerts(tmp_path,monkeypatch):
    from padeltime import main
    from fastapi.testclient import TestClient
    players,matches=normalize_schedule(fixture(),tournament(),'Europe/Berlin','2026-10-18')
    snapshot=Snapshot(fetched_at=datetime.now(timezone.utc),date='2026-10-18',players=list(players.values()),
        matches=list(matches.values()),tournaments=[tournament()])
    path=tmp_path/'real.json';write_snapshot(path,snapshot)
    monkeypatch.setattr(main,'provider',SnapshotProvider(path))
    client=TestClient(main.app)
    assert not client.get('/api/health').json()['demo']
    result=client.get('/api/matches').json()
    assert result[0]['id'].startswith('pp-m-')
    assert result[0]['tracking']['estimate'] is None
    body={'audience':'test-real-device','favorites':['pp-p-14945']}
    assert client.post('/api/notifications/sync',json=body).json()==[]
    assert client.post('/api/demo/pp-m-18888',json={**body,'action':'advance'}).status_code==403
    assert client.get('/api/tournaments/pp-t-274/order-of-play?date=2026-10-17').json()==[]
