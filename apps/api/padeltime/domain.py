from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

TERMINAL = {'FINISHED', 'WALKOVER', 'RETIRED', 'CANCELLED'}
class Player(BaseModel):
    id: str
    name: str
    country: str
    rank: Optional[int] = None
class Tournament(BaseModel):
    id: str
    name: str
    location: str
    category: str
    starts: str
    ends: str
    status: str
    source_url: Optional[str] = None
    timezone: str = "UTC"
class Match(BaseModel):
    id: str
    tournament_id: str
    court: str
    order: int
    order_confirmed: bool = True
    day: str = ""
    court_id: str = ""
    schedule_label: str = ""
    source_url: Optional[str] = None
    players: List[str]
    status: str = 'SCHEDULED'
    scores: List[List[int]] = Field(default_factory=list)
    official_time: Optional[datetime] = None
    time_kind: str = 'unknown'
    round: str = 'Quarter-final'
    revision: int = 0
    def favorite(self, ids):
        return bool(set(self.players) & set(ids))

def preceding(match, matches):
    return sorted([m for m in matches if m.tournament_id == match.tournament_id and m.court == match.court and m.day == match.day and m.order_confirmed and match.order_confirmed and m.order < match.order], key=lambda m: m.order)

def next_on_court(matches):
    if any(not m.order_confirmed for m in matches):
        return None
    return next(iter(sorted([m for m in matches if m.status not in TERMINAL], key=lambda m: m.order)), None)

def tracking(match, matches, now=None):
    now = now or datetime.now(timezone.utc)
    if not match.order_confirmed:
        return {"state":match.status.lower() if match.status != "SCHEDULED" else "order_unconfirmed", "previous":None, "remaining":None, "estimate":None}
    prior = preceding(match, matches)
    pending = [m for m in prior if m.status not in TERMINAL]
    previous = prior[-1] if prior else None
    if match.status != 'SCHEDULED':
        state = match.status.lower()
    elif pending:
        state = 'previous_live' if any(m.status == 'LIVE' for m in pending) else 'waiting'
    elif match.official_time and match.official_time > now:
        state = 'scheduled'
    else:
        state = 'court_clear'  # court clearance alone cannot establish imminent start
    estimate = None
    if match.status == 'SCHEDULED' and not any(m.status not in {'SCHEDULED','LIVE'} for m in pending):
        low = sum(20 if m.status == 'LIVE' else 65 for m in pending) + len(pending)*10
        high = sum(75 if m.status == 'LIVE' else 120 for m in pending) + len(pending)*15
        if pending:
            lower = now + timedelta(minutes=low)
            upper = now + timedelta(minutes=high)
            if match.official_time:
                lower = max(lower, match.official_time)
                upper = max(upper, lower + timedelta(minutes=15))
            estimate = {'earliest':lower.isoformat(), 'latest':upper.isoformat(), 'label':'Estimated · demo rules'}
    return {'state':state, 'previous':previous.model_dump(mode='json') if previous else None, 'remaining':len(pending), 'estimate':estimate}

def event_for(old, new):
    if old.status != new.status:
        return {'LIVE':'started','FINISHED':'finished','SUSPENDED':'schedule_changed','DELAYED':'schedule_changed'}.get(new.status)
    if (old.court, old.order, old.official_time) != (new.court, new.order, new.official_time):
        return 'schedule_changed'
    return None
