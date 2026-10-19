"""Transactional observations and in-app outbox. No events inferred from missing rows."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import TrackedMatch, DeviceSubscription, NotificationEvent, MatchStatusHistory
from .domain import Match, preceding, TERMINAL


def event_kind(old, current):
    if old and old.status != current.status:
        if current.status == 'LIVE': return 'started'
        if current.status == 'FINISHED': return 'finished'
        if current.status in {'DELAYED','SUSPENDED','CANCELLED'}: return 'schedule_changed'
    if current.status == 'WARMUP' and (not old or old.status != 'WARMUP'):
        return 'approaching'
    if old and (old.court_id,old.day,old.official_time,old.time_kind,old.schedule_label) != (
            current.court_id,current.day,current.official_time,current.time_kind,current.schedule_label):
        return 'schedule_changed'
    if old and old.order_confirmed and current.order_confirmed and old.order != current.order:
        return 'schedule_changed'
    if not old and current.status == 'SCHEDULED': return 'scheduled'
    return None


MESSAGES={
    'scheduled':'Your player has a published match. Actual start may change.',
    'approaching':'Source reports warm-up. Your player is preparing to play.',
    'started':'Source reports your followed match is live.',
    'finished':'Source reports your followed match has finished.',
    'schedule_changed':'The source changed your followed match schedule or status.',
    'previous_finished':'Previous match finished. Court turnaround and official timing still apply.',
}


def outbox(db, audience, match, kind):
    existing=db.scalar(select(NotificationEvent).where(NotificationEvent.audience==audience,
        NotificationEvent.match_id==match.id,NotificationEvent.kind==kind,NotificationEvent.revision==match.revision))
    if not existing:
        db.add(NotificationEvent(audience=audience,match_id=match.id,kind=kind,
            revision=match.revision,message=MESSAGES[kind]))


def ingest(engine, snapshot, now=None):
    now=now or datetime.now(timezone.utc)
    if not 0 <= (now-snapshot.fetched_at).total_seconds() <= 120:
        return 0  # stale data cannot prove a new current event
    changed=0
    with Session(engine) as db, db.begin():
        subscriptions=list(db.scalars(select(DeviceSubscription).where(DeviceSubscription.enabled==True)))
        old_records={r.id:r for r in db.scalars(select(TrackedMatch))}
        for current in snapshot.matches:
            record=old_records.get(current.id)
            if record:
                observed=record.observed_at
                if observed.tzinfo is None: observed=observed.replace(tzinfo=timezone.utc)
                if snapshot.fetched_at <= observed: continue
            old=Match.model_validate(record.payload) if record else None
            payload=current.model_dump(mode='json',exclude={'revision'})
            old_payload=old.model_dump(mode='json',exclude={'revision'}) if old else None
            if payload==old_payload:
                record.observed_at=snapshot.fetched_at
                continue
            current=current.model_copy(update={'revision':record.revision+1 if record else 1})
            changed+=1
            if record:
                record.payload=current.model_dump(mode='json');record.revision=current.revision
                record.observed_at=snapshot.fetched_at
            else:
                db.add(TrackedMatch(id=current.id,payload=current.model_dump(mode='json'),
                    revision=current.revision,observed_at=snapshot.fetched_at))
            if old:
                db.add(MatchStatusHistory(match_id=current.id,before=old.status,
                    after=current.status,revision=current.revision))
            kind=event_kind(old,current)
            for subscription in subscriptions:
                if kind and current.favorite(subscription.favorites):
                    outbox(db,subscription.audience,current,kind)
                if old and old.status not in TERMINAL and current.status=='FINISHED':
                    for following in snapshot.matches:
                        prior=preceding(following,snapshot.matches)
                        if following.status=='SCHEDULED' and following.favorite(subscription.favorites) and prior and prior[-1].id==current.id:
                            # Revision of completed predecessor identifies this event, not a later score update.
                            outbox(db,subscription.audience,following.model_copy(update={'revision':current.revision}),'previous_finished')
    return changed


def subscribe(engine,audience,favorites,enabled=True,snapshot=None):
    with Session(engine) as db, db.begin():
        subscription=db.get(DeviceSubscription,audience)
        if subscription:
            subscription.favorites=list(dict.fromkeys(favorites));subscription.enabled=enabled
        else:
            db.add(DeviceSubscription(audience=audience,favorites=list(dict.fromkeys(favorites)),enabled=enabled))
        if enabled and snapshot and 0 <= (datetime.now(timezone.utc)-snapshot.fetched_at).total_seconds() <= 120:
            for match in snapshot.matches:
                if match.status=='SCHEDULED' and match.favorite(favorites):
                    record=db.get(TrackedMatch,match.id)
                    outbox(db,audience,match.model_copy(update={'revision':record.revision if record else 1}),'scheduled')
