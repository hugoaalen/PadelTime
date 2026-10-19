"""Cancellable single-process collector loop; opt-in through API lifespan."""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .collectors.premier import collect, AccessRestricted, SourceError
from .ingestion import ingest
from .order import apply_reviewed_order

logger=logging.getLogger(__name__)

class CollectorWorker:
    def __init__(self,engine,output,slug,interval=90,order_file=None,collector=collect):
        if interval<60: raise ValueError('Collector interval must be at least 60 seconds')
        self.engine=engine;self.output=Path(output);self.slug=slug;self.interval=interval
        self.order_file=order_file;self.collector=collector
        self.state={'enabled':True,'state':'starting','last_success':None,'last_error':None,'next_attempt':None,'failures':0}

    async def cycle(self):
        # Always select today's venue day; never replay an old day as live.
        from .snapshot import SnapshotProvider
        if not self.output.exists():
            raise SourceError('Bootstrap a current tournament snapshot before enabling collection')
        prior=SnapshotProvider(self.output).read()
        tournament=next((t for t in prior.tournaments if t.source_url and t.source_url.endswith('/'+self.slug)),None) if prior else None
        zone=getattr(tournament,'timezone','UTC') if tournament else 'UTC'
        day=datetime.now(ZoneInfo(zone)).date().isoformat()
        if tournament and (day<tournament.starts or day>tournament.ends):
            self.state.update(state='idle',last_error=None,failures=0)
            return 900  # do not repeatedly fetch an event outside its dates
        self.state['state']='collecting'
        snapshot=await self.collector(day,self.slug,self.output)
        if self.order_file:
            try:
                apply_reviewed_order(snapshot,self.order_file)
            except (SourceError,ValueError,KeyError,OSError):
                for match in snapshot.matches: match.order_confirmed=False
                snapshot.warnings.append('Reviewed order no longer valid; predecessor alerts suspended.')
            from .collectors.premier import write_snapshot
            write_snapshot(self.output,snapshot)
        ingest(self.engine,snapshot)
        self.state.update(state='running',last_success=snapshot.fetched_at.isoformat(),last_error=None,failures=0)
        return self.interval

    async def run(self):
        while True:
            try:
                delay=await self.cycle()
            except AccessRestricted:
                self.state.update(state='blocked',last_error='Source access restricted. Collection stopped.',next_attempt=None)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Collector cycle failed; previous valid data retained')
                count=self.state['failures']+1
                delay=min(900,self.interval*2**min(count,4))
                self.state.update(state='error',last_error='Collection failed. Previous results retained.',failures=count)
            from datetime import timedelta
            self.state['next_attempt']=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()
            await asyncio.sleep(delay)
