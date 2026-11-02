"""Bounded adapter for the public World Cup order widget linked by FIP.

No FIP crawl or credentials. Country ties are context, not inferred match
results. Only explicit status labels generate live/completion transitions.
"""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from .matchscorer import Tree, Node, WIDGET, normalized, resolve_person
from .premier import Snapshot, PublicClient, USER_AGENT, SourceError, AccessRestricted
from ..domain import Match, Player, Tournament

START = '2026-11-02'
END = '2026-11-07'
ZONE = 'Asia/Qatar'
EVENT = 'FIP-2026-4516'
TOURNAMENT = Tournament(id='fip-wc-2026', name='FIP WORLD CUP 2026', location='Doha · Qatar',
    category='WORLD CUP', starts=START, ends=END, status='LIVE', timezone=ZONE,
    source_url='https://www.padelfip.com/events/fip-world-cup-2026-2/')
STATUS = {'completed':'FINISHED', 'live':'LIVE', 'in progress':'LIVE',
    'warmup':'WARMUP', 'warm up':'WARMUP', 'warming up':'WARMUP',
    'scheduled':'SCHEDULED', 'upcoming':'SCHEDULED', 'not started':'SCHEDULED',
    'suspended':'SUSPENDED', 'delayed':'DELAYED', 'cancelled':'CANCELLED',
    'canceled':'CANCELLED', 'walkover':'WALKOVER', 'retired':'RETIRED'}


def active(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(ZONE))
    return START <= local.date().isoformat() <= END or (
        local.date().isoformat() == '2026-11-08' and local.hour < 6)


def path(day):
    if not START <= day <= END:
        raise ValueError('Day outside World Cup')
    index = (date.fromisoformat(day)-date.fromisoformat(START)).days+1
    return f'/screen/oopbyday/{EVENT}/{index}?t=tol'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def parse_day(html, day, known):
    root = Tree(html).root
    selected = [n for n in root.find(cls='play-day-button') if 'active' in n.attrs.get('class','').split()]
    if len(selected)!=1 or selected[0].parent.tag!='a' or urlsplit(selected[0].parent.attrs.get('href','')).path != urlsplit(path(day)).path:
        raise SourceError('World Cup widget did not select the requested day')
    players, matches, warnings = {}, [], []
    for header in root.find(cls='schedule-header'):
        courts = list(header.find(cls='oop-court'))
        if len(courts)!=1:
            raise SourceError('Ambiguous World Cup court')
        court = courts[0].text()
        tables = [n for n in header.parent.children if isinstance(n,Node) and n.tag=='table']
        complete = True
        court_matches = []
        for order, table in enumerate(tables,1):
            rounds = list(table.find(cls='round-name'))
            round_text = ' '.join(rounds[0].text().split()) if len(rounds)==1 else ''
            gender = 'female' if normalized(round_text).startswith('women ') else 'male' if normalized(round_text).startswith('men ') else ''
            ids, identities, countries, scores = [], [], [], []
            for team in table.find('td','team'):
                flags = [n.attrs.get('src','').rsplit('/',1)[-1].split('.')[0] for n in team.find('img','flags')]
                country = flags[0] if flags and len(set(flags))==1 and re.fullmatch('[A-Z]{3}',flags[0]) else ''
                countries.append(country)
                for line in team.find(cls='line-thin'):
                    parts = [n.text() for n in line.children if isinstance(n,Node) and n.tag=='span']
                    if len(parts)!=2 or not all(parts):
                        continue
                    identity = '|'.join([gender,country,*map(normalized,parts)])
                    candidates = {p.id:p for p in known if p.gender==gender and p.country==country}
                    # Match only a unique initial + complete surname in same category/country.
                    id = resolve_person(parts,candidates)
                    if id:
                        player = candidates[id]
                    else:
                        id = 'fip-p-'+digest(identity)
                        player = Player(id=id,name=' '.join(parts),short_name=parts[1],country=country,gender=gender)
                    players[id] = player
                    ids.append(id);identities.append(identity)
                row_scores = []
                for cell in team.parent.find('td','set'):
                    # Ignore tie-break superscripts and empty third sets.
                    value = ''.join(c for c in cell.children if isinstance(c,str)).strip()
                    row_scores.append(int(value) if value.isdigit() else None)
                scores.append(row_scores)
            if len(ids)!=4 or len(set(ids))!=4 or len(countries)!=2 or not all(countries) or not gender:
                complete=False
                warnings.append('World Cup lineup incomplete on '+court+'; individual tracking unavailable for that slot.')
                continue
            statuses = list(table.find(cls='text-uppercase'))
            label = normalized(statuses[0].text()) if len(statuses)==1 else ''
            status = STATUS.get(label,'UNKNOWN')
            timing = list(table.find(cls='court-name'))
            schedule = timing[0].text() if len(timing)==1 else ''
            official, kind = None, 'unknown'
            clock = re.fullmatch(r'(Starting at|Not before) (\d{1,2}):(\d{2}) (AM|PM)',schedule)
            if clock:
                prefix,hour,minute,period=clock.groups()
                hour,minute=int(hour),int(minute)
                if 1<=hour<=12 and 0<=minute<=59:
                    hour=hour%12+(12 if period=='PM' else 0)
                    official=datetime.combine(date.fromisoformat(day),datetime.min.time()).replace(hour=hour,minute=minute,tzinfo=ZoneInfo(ZONE))
                    kind='not_before' if prefix=='Not before' else 'scheduled'
            # IDs use source lineup strings, independent of directory updates and court moves.
            signature = '|'.join([day,gender,*sorted(identities)])
            match=Match(id='fip-wc-m-'+digest(signature),tournament_id=TOURNAMENT.id,
                court=court,court_id=normalized(court),day=day,order=order,order_confirmed=True,
                players=ids,status=status,scores=[[a,b] for a,b in zip(*scores) if a is not None and b is not None],
                official_time=official,time_kind=kind,schedule_label=schedule,
                source_url=WIDGET+path(day),round=round_text,national_teams=countries)
            if any(m.id==match.id for m in matches+court_matches):
                raise SourceError('Duplicate World Cup fixture identity')
            court_matches.append(match)
        if not complete:
            for match in court_matches:match.order_confirmed=False
        matches.extend(court_matches)
    return list(players.values()),matches,warnings


async def collect(known,now=None):
    now=now or datetime.now(timezone.utc)
    local=now.astimezone(ZoneInfo(ZONE))
    day=local.date()
    # Keep the previous evening through venue midnight, so its final transition
    # is not lost. Never poll more than two day pages per three-minute cycle.
    first=day-timedelta(days=1) if local.hour<6 else day
    days=[(first+timedelta(days=i)).isoformat() for i in range(2)]
    days=[d for d in days if START<=d<=END]
    players,matches,warnings,coverage={},[],[],[]
    async with httpx.AsyncClient(timeout=10,follow_redirects=False,headers={'User-Agent':USER_AGENT}) as client:
        public=PublicClient(client)
        for requested in days:
            try:
                response=await public.request(WIDGET,path(requested))
                people,fixtures,issues=parse_day(response.text,requested,known)
            except AccessRestricted:
                raise
            except (SourceError,httpx.HTTPError):
                if requested==days[0]:raise
                warnings.append('Next World Cup day unavailable; current-day tracking continues.')
                continue
            players.update({p.id:p for p in people});matches.extend(fixtures);warnings.extend(issues)
            if fixtures:coverage.append(requested)
            else:warnings.append('World Cup source has not published individual fixtures for '+requested+'.')
    return Snapshot(source='fip-worldcup-public-widget',source_url=TOURNAMENT.source_url,
        fetched_at=now,date=local.date().isoformat(),tournaments=[TOURNAMENT],players=list(players.values()),
        matches=matches,coverage={TOURNAMENT.id:coverage},warnings=warnings)
