from datetime import datetime, timezone
import copy

from fastapi.testclient import TestClient

from padeltime import cloud
from padeltime.collectors.premier import Snapshot
from padeltime.domain import Match,Player,Tournament
from padeltime.cloud_state import evolve
from padeltime.notification_text import notification_text
from padeltime.player_catalog import ranking_players,merged_players


def fixture():
    players=[Player(id='pp-p-'+str(i),name=name,short_name=short,country='ESP') for i,name,short in [
        (1,'Arturo Coello','Coello'),(2,'Agustin Tapia','Tapia'),
        (3,'Juan Lebron','Lebron'),(4,'Leandro Roman Augsburger','Augsburger')]]
    match=Match(id='m',tournament_id='t',court='Pista central',court_id='1',order=1,
        players=[p.id for p in players],status='SCHEDULED',
        official_time=datetime(2026,10,30,15,tzinfo=timezone.utc),time_kind='not_before')
    return Snapshot(fetched_at=datetime.now(timezone.utc),date='2026-10-30',players=players,matches=[match],
        tournaments=[Tournament(id='t',name='KUWAIT MAJOR',location='Kuwait',category='MAJOR',status='LIVE',starts='2026-10-23',ends='2026-10-31')])


def test_contextual_notifications_names_court_local_time_and_score():
    snapshot=fixture()
    data,updates=evolve(None,snapshot,{'phone':{'favorites':['pp-p-1'],'enabled':True,'events':[]}})
    event=updates['phone']['events'][0]
    text=notification_text(event,'es','Europe/Madrid')
    assert text['title']=='Coello · Partido programado'
    assert 'Coello / Tapia vs Lebron / Augsburger' in text['body']
    assert 'Pista central' in text['body'] and 'Kuwait Major' in text['body']
    assert 'No antes de: 30/10 16:00 CET' in text['body']
    snapshot.matches[0].status='WARMUP'
    _,updates=evolve(data,snapshot,updates)
    assert 'Calentando' in notification_text(updates['phone']['events'][0],'es')['title']
    finished={**event,'kind':'finished','details':{**event['details'],'scores':[[6,3],[7,6]]}}
    assert '6–3, 7–6' in notification_text(finished,'en')['body']


def test_directory_keeps_eliminated_players_and_profile_fields():
    raw={'status':True,'data':[{'id':'99','first_name':'Outside','last_name':'Tournament',
        'gender':'female','rank':80,'country':{'iso3':'ARG'},'display_name':'Tournament'}]}
    ranked=ranking_players(raw,'female')
    directory=merged_players([p.model_dump(mode='json') for p in ranked],fixture().players)
    assert len(directory)==5
    again=merged_players([p.model_dump(mode='json') for p in directory],[])
    assert next(p for p in again if p.id=='pp-p-99').gender=='female'
    assert next(p for p in again if p.id=='pp-p-99').rank==80
    refreshed=merged_players([p.model_dump(mode='json') for p in again],
        [ranked[0].model_copy(update={'rank':79})],authoritative=True)
    assert next(p for p in refreshed if p.id=='pp-p-99').rank==79


def test_empty_browser_does_not_reserve_capacity_and_favorites_survive_rounds(monkeypatch):
    device={'favorites':[],'events':[]}
    writes=[]
    monkeypatch.setattr(cloud,'current_device',lambda request:('phone',copy.deepcopy(device)))
    monkeypatch.setattr(cloud,'read_snapshot',fixture)
    monkeypatch.setattr(cloud,'device_list',lambda:{'old-phone':{'token':'token'}})
    monkeypatch.setattr(cloud,'put_device',lambda identity,patch:writes.append(patch))
    client=TestClient(cloud.app)
    assert client.post('/api/notifications/sync',json={'favorites':[]}).json()==[]
    assert writes==[]
    assert client.post('/api/notifications/sync',json={'favorites':['pp-p-999','unknown'],'timezone':'Europe/Madrid'}).status_code==200
    assert writes[-1]['favorites']==['pp-p-999']
    assert writes[-1]['timezone']=='Europe/Madrid'
    assert client.post('/api/notifications/sync',json={'favorites':[],'timezone':'fake/zone'}).status_code==422
    assert cloud.pack_device({'favorites':[]})['active'] is False
    assert cloud.pack_device({'favorites':['pp-p-999']})['active'] is True


def test_public_bootstrap_needs_no_identity_and_includes_stable_catalog(monkeypatch):
    snapshot=fixture()
    monkeypatch.setattr(cloud,'read_snapshot',lambda:snapshot)
    monkeypatch.setattr(cloud,'get_record',lambda collection,id:{'players':[{'id':'pp-p-99','name':'Outside Tournament','country':'ARG','rank':99}]} if id=='players' else {})
    monkeypatch.setattr(cloud,'uid',lambda request:(_ for _ in ()).throw(AssertionError('Public startup must not authenticate')))
    response=TestClient(cloud.app).get('/api/bootstrap')
    assert response.status_code==200
    assert len(response.json()['players'])==5
    assert response.json()['matches'][0]['id']=='m'
    assert response.headers['cache-control'].startswith('public,')
