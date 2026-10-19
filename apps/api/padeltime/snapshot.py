"""Read validated snapshots; never silently fall back to simulated data."""
from datetime import datetime, timezone
from pathlib import Path
from .collectors.premier import Snapshot
from .domain import tracking

class SnapshotProvider:
    def __init__(self, path):
        self.path = Path(path)
        self.worker = None

    def read(self):
        return Snapshot.model_validate_json(self.path.read_text())

    def metadata(self):
        snapshot = self.read()
        age = (datetime.now(timezone.utc)-snapshot.fetched_at).total_seconds()
        return {'status':'ok','demo':False,'source':snapshot.source,
            'source_url':snapshot.source_url,'fetched_at':snapshot.fetched_at.isoformat(),
            'snapshot':True,'stale':age>120,'warnings':snapshot.warnings,'date':snapshot.date,
            'order_confirmed':bool(snapshot.matches) and all(m.order_confirmed for m in snapshot.matches),
            'collector':dict(self.worker.state) if self.worker else {'enabled':False,'state':'disabled'}}

    @property
    def matches(self):
        snapshot = self.read()
        stale = (datetime.now(timezone.utc)-snapshot.fetched_at).total_seconds()>120
        # Cached LIVE is not evidence that a match is still in progress.
        return [m.model_copy(update={'status':'UNKNOWN'}) if stale and m.status=='LIVE' else m for m in snapshot.matches]

    def tracking(self,match,matches):
        if self.metadata()['stale']:
            return {'state':'stale','previous':None,'remaining':None,'estimate':None}
        return tracking(match,matches)

    async def get_players(self): return self.read().players
    async def get_tournaments(self): return self.read().tournaments
    async def get_matches(self, tournament_id=''):
        return [m for m in self.matches if not tournament_id or m.tournament_id==tournament_id]
    async def get_order_of_play(self, tournament_id, date):
        return [m for m in await self.get_matches(tournament_id) if m.day==date]
    async def get_live_scores(self, tournament_id):
        return [m for m in await self.get_matches(tournament_id) if m.status=='LIVE']
