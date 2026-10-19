"""Pure state transition used by the free serverless adapter."""
import hashlib
import hmac
import time
from datetime import datetime, timezone
from .domain import Match, preceding, TERMINAL
from .ingestion import event_kind, MESSAGES

FRESH_SECONDS=300  # Free clock polls every three minutes.
MAX_DEVICES=20

def valid_signature(secret,timestamp,signature,now=None):
    try:
        if not secret or len(secret)<32 or abs((now or time.time())-int(timestamp))>180:return False
        expected=hmac.new(secret.encode(),timestamp.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,signature)
    except (ValueError,TypeError): return False


def evolve(previous,snapshot,devices,now=None):
    now=now or datetime.now(timezone.utc)
    if not 0 <= (now-snapshot.fetched_at).total_seconds() <= FRESH_SECONDS:
        raise ValueError('Stale capture cannot generate current alerts')
    old={m['id']:Match.model_validate(m) for m in (previous or {}).get('observations',(previous or {}).get('matches',[]))}
    changes=[]
    for match in snapshot.matches:
        before=old.get(match.id)
        same=before and before.model_dump(exclude={'revision'})==match.model_dump(exclude={'revision'})
        match.revision=before.revision if same else (before.revision+1 if before else 1)
        if not same: changes.append((before,match,event_kind(before,match)))
    updated={}
    for uid,device in devices.items():
        if not device.get('enabled',True):continue
        inbox=list(device.get('events',[]))
        seen={e['id'] for e in inbox}
        def add(match,kind,revision):
            key=f'{match.id}:{kind}:{revision}'
            if key not in seen:
                inbox.insert(0,{'id':key,'match_id':match.id,'kind':kind,'message':MESSAGES[kind],'created_at':now.isoformat()});seen.add(key)
        for before,match,kind in changes:
            if kind and match.favorite(device.get('favorites',[])):add(match,kind,match.revision)
            if before and before.status not in TERMINAL and match.status=='FINISHED':
                for target in snapshot.matches:
                    prior=preceding(target,snapshot.matches)
                    if target.status=='SCHEDULED' and prior and prior[-1].id==match.id and target.favorite(device.get('favorites',[])):
                        add(target,'previous_finished',match.revision)
        if inbox!=device.get('events',[]):updated[uid]={**device,'events':inbox[:30]}
    known={id:match.model_dump(mode='json') for id,match in old.items()}
    for match in snapshot.matches:
        known.pop(match.id,None);known[match.id]=match.model_dump(mode='json')
    data=snapshot.model_dump(mode='json')
    data['observations']=list(known.values())[-250:]
    return data,updated
