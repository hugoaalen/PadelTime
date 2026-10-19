import os
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone, timedelta
from typing import List, Literal, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from .models import Base, NotificationEvent, MatchStatusHistory, TrackedMatch
from .provider import MockProvider
from .snapshot import SnapshotProvider
from .domain import tracking, event_for, preceding
from .worker import CollectorWorker
from .ingestion import subscribe

engine = create_engine(os.getenv('DATABASE_URL','sqlite:///./padeltime.db'))
Base.metadata.create_all(engine)  # local bootstrap; deployed environments use Alembic
provider = SnapshotProvider(os.environ['SNAPSHOT_PATH']) if os.getenv('DATA_PROVIDER')=='snapshot' else MockProvider()
worker = None

@asynccontextmanager
async def lifespan(app):
    global worker
    task = None
    if isinstance(provider, SnapshotProvider) and os.getenv('COLLECTOR_ENABLED','false').lower()=='true':
        worker = CollectorWorker(engine,provider.path,os.environ['COLLECTOR_SLUG'],
            interval=int(os.getenv('COLLECTOR_INTERVAL','90')),order_file=os.getenv('ORDER_FILE'))
        provider.worker = worker
        task = asyncio.create_task(worker.run())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
        worker = None
        if isinstance(provider, SnapshotProvider): provider.worker = None

app = FastAPI(title='PadelTime',version='0.1.0',lifespan=lifespan)
@app.exception_handler(FileNotFoundError)
async def missing_snapshot(request: Request, exc):
    return JSONResponse(status_code=503, content={'detail':'Snapshot unavailable. Run collector before starting snapshot mode.'})

@app.exception_handler(ValidationError)
async def invalid_snapshot(request: Request, exc):
    return JSONResponse(status_code=503, content={'detail':'Snapshot invalid. Last valid collection required.'})

class Audience(BaseModel):
    audience: str = Field(min_length=8,max_length=100,pattern=r'^[a-zA-Z0-9-]+$')
    favorites: List[str] = Field(max_length=100)
    enabled: bool = True
class Change(Audience):
    action: Literal['advance','delay','reschedule','score']

def emit(db, audience, match, kind, message):
    exists = db.scalar(select(NotificationEvent).where(NotificationEvent.audience==audience,NotificationEvent.match_id==match.id,NotificationEvent.kind==kind,NotificationEvent.revision==match.revision))
    if not exists:
        db.add(NotificationEvent(audience=audience,match_id=match.id,kind=kind,revision=match.revision,message=message))
        db.flush()

def events(audience):
    with Session(engine) as db:
        return [{'id':e.id,'match_id':e.match_id,'kind':e.kind,'message':e.message,'created_at':e.created_at.isoformat()} for e in db.scalars(select(NotificationEvent).where(NotificationEvent.audience==audience, *([NotificationEvent.match_id.like('pp-m-%')] if isinstance(provider,SnapshotProvider) else [])).order_by(NotificationEvent.created_at.desc()).limit(50))]

@app.get('/api/health')
def health():
    if isinstance(provider, SnapshotProvider): return provider.metadata()
    return {'status':'ok','demo':True,'source':'mock','snapshot':False,'stale':False,'warnings':[]}
@app.get('/api/players')
async def players(): return await provider.get_players()
@app.get('/api/tournaments')
async def tournaments(): return await provider.get_tournaments()
@app.get('/api/matches')
async def matches(tournament_id: str = ''):
    all_matches = await provider.get_matches(tournament_id)
    return [dict(m.model_dump(mode='json'),tracking=provider.tracking(m,all_matches) if isinstance(provider,SnapshotProvider) else tracking(m,all_matches)) for m in all_matches]
@app.get('/api/tournaments/{tournament_id}/order-of-play')
async def order(tournament_id: str, date: str):
    result = await provider.get_order_of_play(tournament_id,date)
    return [dict(m.model_dump(mode='json'),tracking=provider.tracking(m,result) if isinstance(provider,SnapshotProvider) else tracking(m,result)) for m in result]
@app.get('/api/matches/{match_id}')
async def match_detail(match_id: str):
    m = next((m for m in provider.matches if m.id==match_id),None)
    if not m: raise HTTPException(404,'Match not found')
    return dict(m.model_dump(mode='json'),tracking=provider.tracking(m,provider.matches) if isinstance(provider,SnapshotProvider) else tracking(m,provider.matches))
@app.post('/api/notifications/sync')
def sync(body: Audience):
    if isinstance(provider, SnapshotProvider):
        if not getattr(provider,'worker',None): return []
        subscribe(engine,body.audience,body.favorites,body.enabled,provider.read())
        return events(body.audience)
    with Session(engine) as db:
        for m in provider.matches:
            if m.favorite(body.favorites) and m.status=='SCHEDULED':
                emit(db,body.audience,m,'scheduled','Your followed players have a match on '+m.court+'.')
                if m.official_time and timedelta(0) <= m.official_time-datetime.now(timezone.utc) <= timedelta(minutes=15) and not tracking(m,provider.matches)['remaining']:
                    emit(db,body.audience,m,'approaching','Official earliest time is within 15 minutes. Actual start remains unconfirmed.')
        db.commit()
    return events(body.audience)
@app.get('/api/notifications/{audience}')
def notifications(audience: str): return events(audience)
@app.post('/api/demo/{match_id}')
def demo(match_id: str, body: Change):
    if isinstance(provider, SnapshotProvider) or os.getenv('DEMO_MODE','false').lower() != 'true': raise HTTPException(403,'Demo controls disabled')
    m = next((m for m in provider.matches if m.id==match_id),None)
    if not m: raise HTTPException(404,'Match not found')
    old = m.model_copy(deep=True)
    if body.action=='advance':
        target = {'SCHEDULED':'LIVE','LIVE':'FINISHED','DELAYED':'SCHEDULED','SUSPENDED':'LIVE'}.get(m.status)
        if not target: raise HTTPException(409,'Match already complete')
        if target=='LIVE' and any(p.status not in {'FINISHED','CANCELLED','WALKOVER','RETIRED'} for p in preceding(m,provider.matches)):
            raise HTTPException(409,'Finish preceding matches first')
        if target=='LIVE' and m.official_time and m.official_time > datetime.now(timezone.utc):
            raise HTTPException(409,'Official earliest time has not arrived')
        m.status=target
        if target=='FINISHED': m.scores=[[6,4],[3,6],[6,3]]
    elif body.action=='score':
        if m.status!='LIVE': raise HTTPException(409,'Only live matches have score progression')
        if not m.scores: m.scores=[[0,0]]
        m.scores[-1][0]=min(7,m.scores[-1][0]+1)
    elif body.action=='delay': m.status='DELAYED'
    else:
        m.official_time=datetime.now(timezone.utc)+timedelta(minutes=45)
        m.time_kind='not_before'
    m.revision+=1
    kind=event_for(old,m)
    with Session(engine) as db:
        db.add(MatchStatusHistory(match_id=m.id,before=old.status,after=m.status,revision=m.revision))
        if kind and m.favorite(body.favorites): emit(db,body.audience,m,kind,'Followed match: '+kind.replace('_',' ')+'.')
        if m.status=='FINISHED' and old.status!='FINISHED':
            for following in provider.matches:
                if following.favorite(body.favorites) and following.status=='SCHEDULED' and m in preceding(following,provider.matches) and following.order==m.order+1:
                    emit(db,body.audience,following,'previous_finished','Previous match finished. Court turnaround and official timing still apply.')
        db.commit()
    return {'match':m,'notifications':events(body.audience)}


@app.get('/api/tracking/history')
def tracking_history(match_id: str = ''):
    query=select(MatchStatusHistory)
    if match_id: query=query.where(MatchStatusHistory.match_id==match_id)
    with Session(engine) as db:
        return [{'match_id':r.match_id,'before':r.before,'after':r.after,'revision':r.revision,'created_at':r.created_at.isoformat()}
            for r in db.scalars(query.order_by(MatchStatusHistory.created_at.desc()).limit(50))]
