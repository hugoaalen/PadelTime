"""Request-scoped deployment for Vercel Hobby + Firestore Spark + free FCM.

Cloud resources are never created and billing is never enabled by this module.
"""
import asyncio
import json
import os
import secrets
import tempfile
from typing import Literal
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from .cloud_state import valid_signature, evolve, FRESH_SECONDS, MAX_DEVICES
from .collectors.premier import (Snapshot, PublicClient, SITE, USER_AGENT, tournament_records,
    normalize_tournament, collect, AccessRestricted)
from .domain import Match, tracking
import httpx

app = FastAPI(title='PadelTime · zero-budget deployment')
_client=None

def database():
    global _client
    if os.getenv('FIREBASE_PLAN')!='spark':
        raise HTTPException(503,'Configure Firebase Spark explicitly; billing-enabled deployment is not supported.')
    if _client is None:
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT'])))
            _client=firestore.client()
        except (KeyError,ValueError):
            raise HTTPException(503,'Firebase Spark server configuration missing.')
    return _client


def get_record(collection,id):
    doc=database().collection(collection).document(id).get(timeout=5)
    return json.loads(doc.to_dict()['payload']) if doc.exists else None


def pack(value):
    payload=json.dumps(value,separators=(',',':'))
    if len(payload.encode())>750_000:raise HTTPException(503,'Free storage safety limit reached.')
    return {'payload':payload}


def read_snapshot():
    value=get_record('catalog','current')
    if not value:raise HTTPException(503,'No source data yet. Run the signed collector first.')
    return Snapshot.model_validate(value)


def uid(request):
    bearer=request.headers.get('authorization','')
    if not bearer.startswith('Bearer '):raise HTTPException(401,'Anonymous Firebase sign-in required.')
    database()
    from firebase_admin import auth
    try:return auth.verify_id_token(bearer[7:])['uid']
    except Exception:raise HTTPException(401,'Invalid or expired identity token.')


def current_device(request):
    identity=uid(request)
    return identity,get_record('devices',identity) or {'favorites':[],'enabled':True,'events':[],'sent':[]}


def put_device(identity,changes):
    from firebase_admin import firestore
    db=database();ref=db.collection('devices').document(identity)
    @firestore.transactional
    def update(tx):
        row=ref.get(transaction=tx,timeout=5)
        current=json.loads(row.to_dict()['payload']) if row.exists else {'favorites':[],'enabled':True,'events':[],'sent':[]}
        current.update(changes)
        tx.set(ref,pack(current))
    update(db.transaction(max_attempts=2))


def device_list():
    rows=list(database().collection('devices').limit(MAX_DEVICES+1).stream(timeout=5))
    if len(rows)>MAX_DEVICES:raise HTTPException(503,'Free device capacity reached.')
    return {r.id:json.loads(r.to_dict()['payload']) for r in rows}


@app.middleware('http')
async def cache_headers(request,call_next):
    response=await call_next(request)
    public=request.method=='GET' and request.url.path in {'/api/health','/api/players','/api/tournaments','/api/matches'}
    response.headers['Cache-Control']='public, s-maxage=30, max-age=0' if public and response.status_code==200 else 'no-store'
    return response


@app.get('/api/health')
def health():
    snapshot=read_snapshot();control=get_record('control','collector') or {}
    age=(datetime.now(timezone.utc)-snapshot.fetched_at).total_seconds()
    return {'demo':False,'source':snapshot.source,'snapshot':True,'stale':not 0<=age<=FRESH_SECONDS,
        'fetched_at':snapshot.fetched_at.isoformat(),'date':snapshot.date,'warnings':snapshot.warnings,
        'order_confirmed':bool(snapshot.matches) and all(m.order_confirmed for m in snapshot.matches),
        'collector':{'enabled':True,'state':control.get('state','not_started'),'last_error':control.get('error')},
        'push':True,'free_capacity':MAX_DEVICES}


@app.get('/api/players')
def players():return read_snapshot().players

@app.get('/api/tournaments')
def tournaments():return read_snapshot().tournaments


def represented(snapshot,match):
    stale=not 0 <= (datetime.now(timezone.utc)-snapshot.fetched_at).total_seconds() <= FRESH_SECONDS
    if stale and match.status in {'LIVE','WARMUP','ON_COURT'}:match=match.model_copy(update={'status':'UNKNOWN'})
    state={'state':'stale','previous':None,'remaining':None,'estimate':None} if stale else tracking(match,snapshot.matches)
    return {**match.model_dump(mode='json'),'tracking':state}


@app.get('/api/matches')
def matches(tournament_id:str=''):
    snapshot=read_snapshot()
    return [represented(snapshot,m) for m in snapshot.matches if not tournament_id or m.tournament_id==tournament_id]

@app.get('/api/matches/{match_id}')
def match_detail(match_id:str):
    snapshot=read_snapshot();match=next((m for m in snapshot.matches if m.id==match_id),None)
    if not match:raise HTTPException(404,'Match not found.')
    return represented(snapshot,match)

@app.get('/api/tournaments/{tournament_id}/order-of-play')
def order(tournament_id:str,date:str):
    snapshot=read_snapshot()
    return [represented(snapshot,m) for m in snapshot.matches if m.tournament_id==tournament_id and m.day==date]

class Preferences(BaseModel):
    favorites:list[str]=Field(max_length=30)
    enabled:bool=True
    audience:str=''  # ignored: identity comes from verified Firebase token
    language:Literal['en','es']='en'

@app.post('/api/notifications/sync')
def sync(request:Request,body:Preferences):
    identity,device=current_device(request)
    allowed={p.id for p in read_snapshot().players}
    favorites=sorted(set(body.favorites)&allowed)
    if not device.get('registered') or device.get('favorites')!=favorites or device.get('enabled')!=body.enabled or device.get('language')!=body.language:
        if not device.get('registered') and identity not in device_list() and len(device_list())>=MAX_DEVICES:
            raise HTTPException(503,'Free pilot device capacity reached.')
        device.update(favorites=favorites,enabled=body.enabled,registered=True)
        put_device(identity,{'favorites':favorites,'enabled':body.enabled,'registered':True,'language':body.language})
    return device['events']

class PushToken(BaseModel):
    token:str=Field(min_length=20,max_length=4096)
    language:Literal['en','es']='en'

@app.post('/api/push/register')
def register_push(request:Request,body:PushToken):
    identity,device=current_device(request)
    if identity not in device_list() and len(device_list())>=MAX_DEVICES:raise HTTPException(503,'Free pilot device capacity reached.')
    device.update(token=body.token,registered=True)
    put_device(identity,{'token':body.token,'registered':True,'language':body.language})
    return {'registered':True}

@app.post('/api/push/disable')
def disable_push(request:Request):
    identity,device=current_device(request);put_device(identity,{'token':None})
    return {'disabled':True}


PUSH_SPANISH={
 'scheduled':'Tu jugador tiene un partido programado. La hora de inicio puede cambiar.',
 'approaching':'La fuente confirma calentamiento. Tu jugador se prepara para jugar.',
 'started':'La fuente indica que el partido que sigues está en directo.',
 'finished':'La fuente indica que el partido que sigues ha terminado.',
 'schedule_changed':'La fuente cambió el horario o el estado del partido que sigues.',
 'previous_finished':'Terminó el partido anterior. Aún se aplican el tiempo de cambio y el horario oficial.'
}
def push_message(event):
    if event.get('language')!='es':return event['message']
    if event['id'].startswith('test-'):return 'PadelTime: prueba de notificación. No es un aviso de partido real.'
    kind=event.get('kind')
    return PUSH_SPANISH.get(kind,event['message'])

def send_push(token,event):
    from firebase_admin import messaging
    message=messaging.Message(token=token,data={'title':'PadelTime','body':push_message(event),
        'event_id':event['id'],'url':'/matches/'+event['match_id'] if event.get('match_id') else '/'},
        webpush=messaging.WebpushConfig(headers={'TTL':'180','Urgency':'high'}))
    messaging.send(message)

@app.post('/api/push/test')
def test_push(request:Request):
    identity,device=current_device(request)
    if not device.get('token'):raise HTTPException(409,'Enable notifications on this device first.')
    now=datetime.now(timezone.utc)
    last=device.get('last_test')
    if last and (now-datetime.fromisoformat(last)).total_seconds()<60:raise HTTPException(429,'Wait one minute between tests.')
    device['last_test']=now.isoformat();put_device(identity,{'last_test':device['last_test']})
    send_push(device['token'],{'id':'test-'+secrets.token_hex(6),'message':'Device test: PadelTime push works. This is not a real match alert.','language':device.get('language','en')})
    return {'submitted':True}


@app.post('/api/push/test-closed')
def queue_test_push(request:Request):
    identity,device=current_device(request)
    if not device.get('token'):raise HTTPException(409,'Enable notifications on this device first.')
    now=datetime.now(timezone.utc)
    last=device.get('last_test')
    if last and (now-datetime.fromisoformat(last)).total_seconds()<60:raise HTTPException(429,'Wait one minute between tests.')
    event={'id':'test-'+secrets.token_hex(6),'created_at':now.isoformat(),
        'message':'PadelTime: closed-app test. This is not a real match alert.'}
    put_device(identity,{'last_test':now.isoformat(),'pending_test':event})
    return {'queued':True,'expected_within_seconds':240}


def deliver_tests():
    """Explicit device tests run even when source collection is idle or blocked."""
    now=datetime.now(timezone.utc);count=0
    for identity,device in device_list().items():
        event=device.get('pending_test')
        if not event:continue
        age=(now-datetime.fromisoformat(event['created_at'])).total_seconds()
        if age>600 or not device.get('token'):
            put_device(identity,{'pending_test':None});continue
        if age<0:continue
        try:send_push(device['token'],{**event,'language':device.get('language','en')})
        except Exception:continue
        put_device(identity,{'pending_test':None});count+=1
    return count


def acquire():
    from firebase_admin import firestore
    db=database();ref=db.collection('control').document('collector');owner=secrets.token_hex(12)
    @firestore.transactional
    def lock(tx):
        row=ref.get(transaction=tx,timeout=5);state=json.loads(row.to_dict()['payload']) if row.exists else {}
        now=datetime.now(timezone.utc);today=now.date().isoformat()
        if state.get('blocked'):return None
        if state.get('lease_until') and datetime.fromisoformat(state['lease_until'])>now:return None
        if state.get('last_attempt') and (now-datetime.fromisoformat(state['last_attempt'])).total_seconds()<170:return None
        if state.get('day')!=today:state.update(day=today,cycles=0,writes=0)
        if state.get('cycles',0)>=480 or state.get('writes',0)>=12000:return None
        state.update(owner=owner,last_attempt=now.isoformat(),lease_until=(now+timedelta(seconds=75)).isoformat(),cycles=state.get('cycles',0)+1)
        tx.set(ref,pack(state));return state
    return owner,lock(db.transaction(max_attempts=2))


async def discover_snapshot(previous):
    async with httpx.AsyncClient(timeout=10,follow_redirects=False,headers={'User-Agent':USER_AGENT}) as client:
        response=await PublicClient(client).request(SITE,'/es')
        records=tournament_records(response.text)
    active=[]
    for record in records:
        day=datetime.now(ZoneInfo(record['timezone'])).date().isoformat()
        if record['start_date_utc'][:10]<=day<=record['end_date_utc'][:10]:active.append((record,day))
    if active:
        record,day=active[0]
        with tempfile.TemporaryDirectory() as directory:
            return await collect(day,record['slug'],Path(directory)/'capture.json'),'running'
    # Never re-stamp old scores as fresh while discovering upcoming metadata.
    if previous:
        snapshot=Snapshot.model_validate(previous)
        known={t.id:t for t in snapshot.tournaments}
        known.update({normalize_tournament(r).id:normalize_tournament(r) for r in records})
        snapshot.tournaments=list(known.values())
        return snapshot,'idle'
    return Snapshot(fetched_at=datetime.now(timezone.utc),date=datetime.now(timezone.utc).date().isoformat(),
        tournaments=[normalize_tournament(r) for r in records],players=[],matches=[],warnings=['No active tournament found in public homepage metadata.']),'idle'


def commit_capture(owner,state,snapshot,mode,previous,devices):
    from firebase_admin import firestore
    db=database();ref=db.collection('control').document('collector')
    @firestore.transactional
    def commit(tx):
        row=ref.get(transaction=tx,timeout=5);control=json.loads(row.to_dict()['payload'])
        if control.get('owner')!=owner:raise HTTPException(409,'Collector lease lost.')
        rows=[db.collection('devices').document(identity).get(transaction=tx,timeout=5) for identity in devices]
        latest={row.id:json.loads(row.to_dict()['payload']) for row in rows if row.exists}
        data,updates=evolve(previous,snapshot,latest) if mode=='running' else ({**snapshot.model_dump(mode='json'),'observations':(previous or {}).get('observations',[])},{})
        cost=3+len(updates)+len(latest)
        if control.get('writes',0)+cost>12000:raise HTTPException(503,'Daily free write budget reached.')
        tx.set(db.collection('catalog').document('current'),pack(data))
        for identity,device in updates.items():tx.set(db.collection('devices').document(identity),pack(device))
        control.update(state=mode,error=None,lease_until=None,writes=control.get('writes',0)+cost,last_success=datetime.now(timezone.utc).isoformat())
        tx.set(ref,pack(control))
    commit(db.transaction(max_attempts=2))


def deliver():
    now=datetime.now(timezone.utc);count=0
    for identity,device in device_list().items():
        if not device.get('enabled') or not device.get('token'):continue
        sent=set(device.get('sent',[]));original=set(sent)
        for event in reversed(device.get('events',[])):
            if event['id'] in sent:continue
            if (now-datetime.fromisoformat(event['created_at'])).total_seconds()>180:
                sent.add(event['id']);continue
            if count>=20:break
            try:send_push(device['token'],{**event,'language':device.get('language','en')})
            except Exception:
                # Preserve pending event; do not mark failures delivered.
                continue
            sent.add(event['id']);count+=1
        if sent!=original:
            device['sent']=[e['id'] for e in device.get('events',[]) if e['id'] in sent]
            put_device(identity,{'sent':device['sent']})
    return count

@app.post('/api/collect')
async def collect_route(request:Request):
    if not valid_signature(os.getenv('COLLECT_SECRET',''),request.headers.get('x-padeltime-time',''),request.headers.get('x-padeltime-signature','')):
        raise HTTPException(401,'Invalid collector signature.')
    tests_sent=0;tests_pending=False
    try:tests_sent=await asyncio.wait_for(asyncio.to_thread(deliver_tests),timeout=5)
    except Exception:tests_pending=True
    owner,state=acquire()
    if state is None:return {'skipped':True,'test_push_submitted':tests_sent,'test_push_pending':tests_pending}
    try:
        previous=get_record('catalog','current');devices=device_list()
        snapshot,mode=await asyncio.wait_for(discover_snapshot(previous),timeout=35)
        commit_capture(owner,state,snapshot,mode,previous,devices)
        sent=0;pending=False
        if mode=='running':
            try:sent=await asyncio.wait_for(asyncio.to_thread(deliver),timeout=5)
            except Exception:pending=True
        return {'state':mode,'push_submitted':sent,'push_pending':pending,'matches':len(snapshot.matches),'test_push_submitted':tests_sent,'test_push_pending':tests_pending}
    except Exception as exc:
        from firebase_admin import firestore
        db=database();ref=db.collection('control').document('collector')
        @firestore.transactional
        def release(tx):
            row=ref.get(transaction=tx,timeout=5);latest=json.loads(row.to_dict()['payload']) if row.exists else {}
            if latest.get('owner')!=owner:return
            latest.update(state='blocked' if isinstance(exc,AccessRestricted) else 'error',blocked=isinstance(exc,AccessRestricted),error='Source unavailable; previous data retained.',lease_until=None)
            tx.set(ref,pack(latest))
        release(db.transaction(max_attempts=2))
        raise HTTPException(503,'Collection failed; previous results retained.')
