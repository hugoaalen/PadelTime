from datetime import datetime,timezone
from pathlib import Path
import pytest
from padeltime.collectors import worldcup as wc
from padeltime.collectors.premier import Snapshot,SourceError
from padeltime.domain import Player
from padeltime.cloud_state import evolve
from padeltime.notification_text import notification_text

HTML=(Path(__file__).parent/'fixtures/worldcup-day-one.html').read_text()
KNOWN=[Player(id='pp-p-14945',name='Arturo Coello',short_name='Coello',country='ESP',gender='male')]

def test_real_worldcup_complete_mixed_courts_scores_and_favorite_identity():
    players,matches,warnings=wc.parse_day(HTML,'2026-11-02',KNOWN)
    assert len(matches)==48 and len(players)==192 and not warnings
    assert len({m.court for m in matches})==8
    assert all(m.status=='FINISHED' and m.order_confirmed for m in matches)
    coello=next(m for m in matches if 'pp-p-14945' in m.players)
    assert coello.national_teams==['ESP','SWE']
    assert coello.scores==[[6,3],[6,2]]
    assert coello.official_time.isoformat()=='2026-11-02T18:00:00+03:00'
    followed=next(m for m in matches if m.court==coello.court and m.order==coello.order+1)
    assert followed.official_time is None
    # A tie-break superscript must not become part of a set score.
    assert followed.scores==[[6,7],[7,5],[6,2]]
    assert next(p for p in players if p.id=='pp-p-14945').name=='Arturo Coello'


def test_worldcup_rejects_wrong_day_and_incomplete_lineup_disables_whole_court():
    with pytest.raises(SourceError):wc.parse_day(HTML,'2026-11-03',KNOWN)
    changed=HTML.replace('<span class="">Bahurel</span>','<span class=""></span>',1)
    _,matches,warnings=wc.parse_day(changed,'2026-11-02',KNOWN)
    assert len(matches)==47 and warnings
    assert all(not m.order_confirmed for m in matches if m.court=='CENTER COURT')
    assert all(m.order_confirmed for m in matches if m.court!='CENTER COURT')


def test_worldcup_identity_stable_across_score_status_and_directory_changes():
    _,a,_=wc.parse_day(HTML,'2026-11-02',KNOWN)
    _,b,_=wc.parse_day(HTML.replace('Completed','In Progress'), '2026-11-02',[])
    assert [m.id for m in a]==[m.id for m in b]
    assert all(m.status=='LIVE' for m in b)
    _,unknown,_=wc.parse_day(HTML.replace('Completed','Unrecognized state'),'2026-11-02',KNOWN)
    assert all(m.status=='UNKNOWN' for m in unknown)  # Completed-looking scores prove nothing.


def test_worldcup_existing_favorite_real_transition_and_replay():
    people,matches,_=wc.parse_day(HTML,'2026-11-02',KNOWN)
    match=next(m for m in matches if 'pp-p-14945' in m.players)
    match.status='SCHEDULED'
    snap=Snapshot(fetched_at=datetime.now(timezone.utc),date='2026-11-02',tournaments=[wc.TOURNAMENT],players=people,matches=[match])
    data,updates=evolve(None,snap,{'phone':{'favorites':['pp-p-14945'],'enabled':True,'events':[]}})
    match.status='LIVE'
    data,updates=evolve(data,snap,updates)
    event=updates['phone']['events'][0]
    assert event['kind']=='started'
    text=notification_text(event,'es','Europe/Madrid')
    assert 'Coello' in text['title'] and 'ESP vs SWE' in text['body'] and 'World Cup' in text['body']
    assert evolve(data,snap,updates)[1]=={}


def test_worldcup_bounds_and_overnight_rollover():
    assert wc.active(datetime(2026,11,7,23,tzinfo=timezone.utc))
    assert not wc.active(datetime(2026,11,8,4,tzinfo=timezone.utc))
    assert not wc.active(datetime(2026,11,1,10,tzinfo=timezone.utc))
    with pytest.raises(ValueError):wc.path('2026-11-08')


def test_worldcup_discovery_uses_existing_catalog_and_bounded_source(monkeypatch):
    import asyncio
    from padeltime import cloud
    monkeypatch.setattr(wc,'active',lambda now:True)
    monkeypatch.setattr(cloud,'get_record',lambda *args:{'players':[p.model_dump(mode='json') for p in KNOWN]})
    async def collect(known):
        assert known[0].id=='pp-p-14945'
        return 'snapshot'
    monkeypatch.setattr(wc,'collect',collect)
    assert asyncio.run(cloud.discover_snapshot(None))==('snapshot','running')


def test_first_published_lineup_already_live_generates_alert():
    from padeltime.ingestion import event_kind
    _,matches,_=wc.parse_day(HTML,'2026-11-02',KNOWN)
    match=matches[0].model_copy(update={'status':'LIVE'})
    assert event_kind(None,match)=='started'
    assert event_kind(None,match.model_copy(update={'status':'FINISHED'})) is None


def test_bounded_overnight_collection_and_optional_day_failure(monkeypatch):
    import asyncio
    import httpx
    requested=[]
    async def request(self,origin,url):
        requested.append(url)
        if '/2?' in url:raise httpx.ReadTimeout('Next day unavailable')
        return httpx.Response(200,text=HTML)
    monkeypatch.setattr(wc.PublicClient,'request',request)
    snapshot=asyncio.run(wc.collect(KNOWN,datetime(2026,11,2,22,tzinfo=timezone.utc)))
    assert len(requested)==2 and len(snapshot.matches)==48
    assert snapshot.coverage=={'fip-wc-2026':['2026-11-02']}
    assert 'current-day tracking continues' in snapshot.warnings[-1]
