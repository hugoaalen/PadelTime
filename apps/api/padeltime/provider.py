from typing import Protocol, List
from datetime import datetime, timezone, timedelta
from .domain import Player, Tournament, Match

class PadelDataProvider(Protocol):
    async def get_players(self) -> List[Player]: ...
    async def get_tournaments(self) -> List[Tournament]: ...
    async def get_matches(self, tournament_id: str = '') -> List[Match]: ...
    async def get_order_of_play(self, tournament_id: str, date: str) -> List[Match]: ...
    async def get_live_scores(self, tournament_id: str) -> List[Match]: ...

class MockProvider:
    def __init__(self):
        self.players = [Player(id=str(i), name=n, country=c, rank=i+1) for i,(n,c) in enumerate([
            ('Arturo Coello','ES'),('Agustín Tapia','AR'),('Alejandro Galán','ES'),('Federico Chingotto','AR'),('Juan Lebrón','ES'),('Franco Stupaczuk','AR'),('Paquito Navarro','ES'),('Lucas Bergamini','BR'),('Ariana Sánchez','ES'),('Paula Josemaría','ES'),('Gemma Triay','ES'),('Delfina Brea','AR')])]
        today = datetime.now(timezone.utc)
        self.tournaments = [Tournament(id='madrid', name='Madrid Premier Padel', location='Madrid, Spain',category='P1',starts=today.date().isoformat(),ends=(today+timedelta(days=3)).date().isoformat(),status='LIVE'),Tournament(id='milan',name='Milano Premier Padel',location='Milan, Italy',category='P1',starts=(today+timedelta(days=10)).date().isoformat(),ends=(today+timedelta(days=17)).date().isoformat(),status='UPCOMING'),Tournament(id='major',name='Mexico Major',location='Acapulco, Mexico',category='MAJOR',starts=(today+timedelta(days=25)).date().isoformat(),ends=(today+timedelta(days=32)).date().isoformat(),status='UPCOMING')]
        self.matches = [Match(id='m1',tournament_id='madrid',court='Centre Court',order=1,players=['0','1','4','5'],status='LIVE',scores=[[6,4],[3,6],[2,1]]),Match(id='m2',tournament_id='madrid',court='Centre Court',order=2,players=['2','3','6','7']),Match(id='m3',tournament_id='madrid',court='Court 2',order=1,players=['8','9','10','11'],status='FINISHED',scores=[[6,3],[6,4]]),Match(id='m4',tournament_id='madrid',court='Court 2',order=2,players=['8','9','10','11'],official_time=today+timedelta(hours=2),time_kind='not_before',round='Exhibition · demo')]
    async def get_players(self): return self.players
    async def get_tournaments(self): return self.tournaments
    async def get_matches(self, tournament_id=''): return [m for m in self.matches if not tournament_id or m.tournament_id == tournament_id]
    async def get_order_of_play(self, tournament_id, date):
        tournament = next((t for t in self.tournaments if t.id == tournament_id), None)
        return await self.get_matches(tournament_id) if tournament and date == tournament.starts else []
    async def get_live_scores(self, tournament_id): return [m for m in await self.get_matches(tournament_id) if m.status == 'LIVE']
