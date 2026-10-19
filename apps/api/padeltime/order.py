"""Apply a reviewed complete court-day order, never guess from response array position."""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .collectors.premier import SourceError


def schedule_fingerprint(snapshot,court):
    entries=[{'id':m.id,'players':m.players,'court_id':m.court_id,'day':m.day,'official_time':m.official_time.isoformat() if m.official_time else None,'time_kind':m.time_kind,'label':m.schedule_label} for m in snapshot.matches if (m.tournament_id,m.court_id,m.day)==court]
    return hashlib.sha256(json.dumps(sorted(entries,key=lambda x:x['id']),sort_keys=True).encode()).hexdigest()

def apply_reviewed_order(snapshot,path):
    document=json.loads(Path(path).read_text())
    plans=document.get('courts',[])
    seen=set()
    assignments=[]
    by_id={m.id:m for m in snapshot.matches}
    for plan in plans:
        if plan['date']!=snapshot.date: continue
        evidence=plan.get('source_url','')
        if urlparse(evidence).scheme!='https' or not plan.get('reviewed_at'):
            raise SourceError('Reviewed order requires HTTPS source_url and reviewed_at')
        reviewed=datetime.fromisoformat(plan['reviewed_at'])
        if reviewed.tzinfo is None or reviewed>datetime.now(timezone.utc):
            raise SourceError('Reviewed order requires a valid past timezone-aware review timestamp')
        ids=plan['match_ids']
        court=(plan['tournament_id'],plan['court_id'],plan['date'])
        if plan.get('schedule_fingerprint')!=schedule_fingerprint(snapshot,court):
            raise SourceError('Source schedule changed since order review; confirmation withdrawn')
        expected={m.id for m in snapshot.matches if (m.tournament_id,m.court_id,m.day)==court}
        if not expected or len(ids)!=len(set(ids)) or set(ids)!=expected or seen.intersection(ids):
            raise SourceError('Reviewed order must cover the complete court day exactly once')
        seen.update(ids)
        assignments.append(ids)
    for ids in assignments:
        for index,id in enumerate(ids,1):
            by_id[id].order=index;by_id[id].order_confirmed=True
    return snapshot

if __name__ == '__main__':
    import argparse
    from .collectors.premier import Snapshot
    parser=argparse.ArgumentParser(description='Print court-day fingerprints for a human-reviewed order file; does not confirm order')
    parser.add_argument('snapshot',type=Path)
    args=parser.parse_args()
    snapshot=Snapshot.model_validate_json(args.snapshot.read_text())
    courts=sorted({(m.tournament_id,m.court_id,m.day) for m in snapshot.matches})
    print(json.dumps({'courts':[{'tournament_id':t,'court_id':c,'date':d,'schedule_fingerprint':schedule_fingerprint(snapshot,(t,c,d)),
        'match_ids':[m.id for m in snapshot.matches if (m.tournament_id,m.court_id,m.day)==(t,c,d)],
        'source_url':'REPLACE WITH OFFICIAL ORDER EVIDENCE','reviewed_at':'REPLACE AFTER HUMAN REVIEW'} for t,c,d in courts]},indent=2))
