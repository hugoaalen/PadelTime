"""Small public-web adapter, not an official or licensed Premier Padel API.

Only URLs and request parameters observed in the public site are used.
No credentials, cookie extraction, access bypass, or FIP scraping.
"""
import argparse
import asyncio
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field
from ..domain import Match, Player, Tournament

SITE = 'https://premierpadel.com'
API = 'https://api-prod.premierpadel.com'
MATCH_PATH = '/api/tournament/getTournamentMatches'
USER_AGENT = 'PadelTimeResearch/0.1 (public schedule collector; local prototype)'

class SourceError(RuntimeError):
    pass

class AccessRestricted(SourceError):
    pass

class Snapshot(BaseModel):
    version: int = 1
    source: str = 'premier-public-web'
    source_url: str = SITE + '/es'
    fetched_at: datetime
    date: str
    tournaments: list[Tournament]
    players: list[Player]
    matches: list[Match]
    warnings: list[str] = Field(default_factory=list)
    # Public metadata and match availability are separate facts.
    coverage: Dict[str, list[str]] = Field(default_factory=dict)


def flight_objects(html: str):
    """Decode JSON text only; never execute website JavaScript."""
    chunks = []
    for raw in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>', html, re.S):
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if len(value) == 2 and value[0] == 1 and isinstance(value[1], str):
            chunks.append(value[1])
    for line in ''.join(chunks).splitlines():
        try:
            yield json.loads(line.split(':', 1)[1])
        except (ValueError, IndexError):
            continue


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def tournament_records(html: str):
    found = {}
    for root in flight_objects(html):
        for item in walk(root):
            if all(k in item for k in ('event_code', 'slug', 'start_date_utc', 'end_date_utc', 'type', 'id')):
                found[str(item['id'])] = item
    if not found:
        raise SourceError('Public page tournament schema changed or contains no tournament records')
    return list(found.values())


def normalize_tournament(raw: dict) -> Tournament:
    status = {'P':'LIVE', 'N':'UPCOMING', 'F':'FINISHED'}.get(raw.get('status'), 'UNKNOWN')
    return Tournament(id='pp-t-'+str(raw['id']), name=raw.get('display_name') or raw['name'],
        location=', '.join(filter(None, [raw.get('city'), raw.get('country')])),
        category=raw['type'], starts=raw['start_date_utc'][:10], ends=raw['end_date_utc'][:10],
        status=status, timezone=raw.get('timezone') or 'UTC', source_url=SITE+'/es/tournaments-detail/'+raw['slug'])


def explicit_time(raw: dict, zone: str):
    """Header is authoritative: observed start_date_time contradicted header.

    Do not infer timestamps from generic start_time/start_date_time fields.
    Those repeated the session start for both finals in the observed response.
    """
    header = raw.get('header') or ''
    match = re.fullmatch(r'(Starting at|Not before)\s+(\d{1,2}):(\d{2})\s*(AM|PM)', header.strip(), re.I)
    if not match:
        return None, 'unknown'
    hour, minute = int(match[2]), int(match[3])
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        raise SourceError('Invalid explicit schedule header')
    hour = hour % 12 + (12 if match[4].upper() == 'PM' else 0)
    local = datetime.combine(date.fromisoformat(raw['date']), datetime.min.time()).replace(
        hour=hour, minute=minute, tzinfo=ZoneInfo(zone))
    return local.astimezone(timezone.utc), 'not_before' if match[1].lower() == 'not before' else 'scheduled'


def normalize_schedule(raw: dict, tournament: Tournament, zone: str, day: str):
    if raw.get('status') is not True or not isinstance(raw.get('data'), dict):
        raise SourceError('Public schedule returned an unsuccessful or unexpected response')
    courts = raw['data'].get('courts')
    if not isinstance(courts, list):
        raise SourceError('Schedule is missing courts; refusing to overwrite previous snapshot')
    players, matches = {}, {}
    for court in courts:
        for source in court.get('matches', []):
            if source.get('date') != day:
                continue
            teams = sorted(source.get('teams', []), key=lambda t: int(t['team_no']))
            if len(teams) != 2 or any(len(t.get('players', [])) != 2 for t in teams):
                raise SourceError('Match has incomplete participants; preserving previous snapshot')
            ids = []
            for team in teams:
                for player in team['players']:
                    # player.id is tournament-specific. player_id is the stable identity.
                    if player.get('player_id') is None:
                        raise SourceError('Missing stable player_id')
                    player_id = 'pp-p-'+str(player['player_id'])
                    ids.append(player_id)
                    players[player_id] = Player(id=player_id,
                        name=' '.join(filter(None,[player.get('first_name'), player.get('last_name')])),
                        country=player.get('country_code') or '', rank=player.get('player_rank'))
            scores = []
            for number in range(1, 6):
                values = [(team.get('score') or {}).get('set'+str(number)) for team in teams]
                if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values):
                    scores.append(values)
                elif any(v is not None for v in values):
                    raise SourceError('Incomplete set score')
            timestamp, kind = explicit_time(source, zone)
            status = {'P':'LIVE', 'N':'SCHEDULED', 'F':'FINISHED', 'W':'WARMUP', 'C':'ON_COURT'}.get(source.get('status'), 'UNKNOWN')
            match_id = 'pp-m-'+str(source['match_id'])
            matches[match_id] = Match(id=match_id, tournament_id=tournament.id,
                court= court.get('court_name') or 'Court unavailable', court_id=str(court['court_id']),
                day=day, order=0, order_confirmed=False, players=ids, status=status,
                scores=scores, official_time=timestamp, time_kind=kind,
                round={'F':'Final','SF':'Semi-final','QF':'Quarter-final'}.get(source.get('round_name'), source.get('round_name') or 'Round unavailable'),
                schedule_label=source.get('header') or '', source_url=tournament.source_url)
    return players, matches


def write_snapshot(path: Path, snapshot: Snapshot):
    """Atomic replace: failed fetches/parses never destroy last valid data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.padeltime-', suffix='.json')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(snapshot.model_dump_json(indent=2))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PublicClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.policies = {}

    async def check_robots(self, origin: str, path: str):
        if origin not in self.policies:
            response = await self.client.get(origin+'/robots.txt')
            if response.status_code in (404, 410):
                self.policies[origin] = None
            elif response.status_code == 200 and 'text/plain' in response.headers.get('content-type', '') and not response.text.lstrip().startswith('<'):
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                self.policies[origin] = parser
            else:
                raise SourceError('Cannot verify robots policy for '+origin+'; collection stopped')
        parser = self.policies[origin]
        if parser and not parser.can_fetch(USER_AGENT, origin+path):
            raise AccessRestricted('robots.txt excludes '+path)
        if parser:
            delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay('*')
            if delay:
                await asyncio.sleep(delay)

    async def request(self, origin: str, path: str, body=None):
        await self.check_robots(origin, path)
        # Small fixed request budget, sequential requests, no retries or auth fallback.
        response = await self.client.request('POST' if body is not None else 'GET', origin+path, json=body)
        if response.status_code in (401,403):
            raise AccessRestricted('Public source HTTP '+str(response.status_code)+'; access restricted, collector stopped')
        if response.status_code != 200:
            raise SourceError('Public source returned HTTP '+str(response.status_code)+'; no bypass attempted')
        if len(response.content) > 5_000_000:
            raise SourceError('Response exceeds collector size limit')
        await asyncio.sleep(1)
        return response


async def collect(day: str, slug: str, output: Path, include_next_day: bool = False):
    date.fromisoformat(day)
    if not re.fullmatch(r'[a-z0-9-]+',slug):
        raise SourceError('Invalid tournament slug')
    if output.exists():
        try:
            cached = Snapshot.model_validate_json(output.read_text())
            age = (datetime.now(timezone.utc)-cached.fetched_at).total_seconds()
            if not include_next_day and cached.date == day and 0 <= age < 60 and any(t.source_url == SITE+'/es/tournaments-detail/'+slug for t in cached.tournaments):
                return cached  # Avoid repeated requests within one minute.
        except (ValueError, OSError, TypeError):
            pass
    capture_started=datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, headers={
        'User-Agent':USER_AGENT, 'language_code':'es'}) as client:
        public = PublicClient(client)
        # Homepage contains current tournament strip and upcoming metadata.
        home = await public.request(SITE, '/es')
        records = {str(r['id']):r for r in tournament_records(home.text)}
        detail = await public.request(SITE, '/es/tournaments-detail/'+slug)
        records.update({str(r['id']):r for r in tournament_records(detail.text)})
        source = next((r for r in records.values() if r['slug'] == slug), None)
        if not source:
            # Historical detail pages may only embed the current tournament strip.
            # This is the same public detail endpoint used by the website.
            response = await public.request(API, '/api/tournament/getTournamentDetails?slug='+slug)
            result = response.json()
            source = result.get('data') if result.get('status') is True else None
            if not isinstance(source, dict) or source.get('slug') != slug:
                raise SourceError('Requested tournament absent from public detail response')
            records[str(source['id'])] = source
        tournament = normalize_tournament(source)
        from .matchscorer import WIDGET, widget_path, apply_widget_order
        players, matches, warnings, coverage = {}, {}, [], []
        days = [day]
        tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        if include_next_day and tomorrow <= source['end_date_utc'][:10]:
            days.append(tomorrow)
        for requested_day in days:
            daily_players, daily_matches = {}, {}
            try:
                for gender in ('male','female'):
                    response = await public.request(API, MATCH_PATH, {'slug':slug,'date':requested_day,
                        'isFavourite':False,'gender':gender,'matchStatus':'All'})
                    p, m = normalize_schedule(response.json(), tournament, source['timezone'], requested_day)
                    daily_players.update(p)
                    for id, match in m.items():
                        if id in daily_matches and daily_matches[id] != match:
                            raise SourceError('Conflicting fixture identities across gender feeds')
                        daily_matches[id] = match
            except AccessRestricted:
                raise
            except (SourceError, httpx.HTTPError):
                if requested_day == day:
                    raise
                warnings.append('Next-day schedule unavailable; current-day tracking continues.')
                continue
            if daily_matches:
                path = widget_path(source, requested_day)
                if path:
                    try:
                        widget = await public.request(WIDGET, path)
                        apply_widget_order(daily_matches, daily_players, widget.text, WIDGET + path)
                    except AccessRestricted:
                        raise
                    except (SourceError, httpx.HTTPError):
                        warnings.append('Official order widget unavailable for '+requested_day+'; predecessor alerts suspended.')
                coverage.append(requested_day)
            else:
                warnings.append('Source has not published matches for '+requested_day+'.')
            players.update(daily_players)
            matches.update(daily_matches)
        # Confirmed order comes exclusively from the mixed official court column.
        # Unknown courts retain a display order without enabling dependency alerts.
        ordered = sorted(matches.values(), key=lambda m:(m.day, m.court_id,
            m.order if m.order_confirmed else 0,
            m.official_time or datetime.max.replace(tzinfo=timezone.utc), m.id))
        for index, match in enumerate(ordered, 1):
            if not match.order_confirmed:
                match.order = index
        if any(not m.order_confirmed for m in ordered):
            warnings.append('Some court sequences could not be matched completely; their predecessor alerts are suspended.')
        snapshot = Snapshot(fetched_at=capture_started, date=day,
            tournaments=[normalize_tournament(r) for r in records.values()],
            players=list(players.values()), matches=ordered,
            coverage={tournament.id:coverage}, warnings=[
                'Public website integration, not an official API or redistribution license.',
                *warnings])
        write_snapshot(output, snapshot)
        return snapshot


def main():
    parser = argparse.ArgumentParser(description='Collect one public Premier Padel tournament day into local JSON')
    parser.add_argument('--date', required=True, help='Venue-local YYYY-MM-DD')
    parser.add_argument('--slug', required=True, help='Slug from public tournament URL')
    parser.add_argument('--output', type=Path, default=Path('../../data/premier.json'))
    args = parser.parse_args()
    try:
        snapshot = asyncio.run(collect(args.date,args.slug,args.output))
    except (SourceError,httpx.HTTPError,ValueError,KeyError) as exc:
        parser.exit(1, 'Collection stopped; previous JSON preserved: '+str(exc)+'\n')
    print(f'Saved {len(snapshot.tournaments)} tournaments, {len(snapshot.players)} players, {len(snapshot.matches)} matches to {args.output}')

if __name__ == '__main__':
    main()
