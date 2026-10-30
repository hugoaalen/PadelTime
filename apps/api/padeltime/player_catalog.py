"""Persistent circuit directory; independent of a tournament's remaining draw."""
from .domain import Player


def ranking_players(raw, gender):
    if raw.get('status') is not True or not isinstance(raw.get('data'), list):
        raise ValueError('Invalid public ranking response')
    players = []
    for row in raw['data']:
        if str(row.get('id', '')).isdigit() and row.get('gender') == gender:
            name = ' '.join(filter(None, [row.get('first_name'), row.get('last_name')]))
            if not name:
                continue
            players.append(Player(id='pp-p-'+str(row['id']), name=name,
                short_name=row.get('display_name') or row.get('last_name') or name,
                country=(row.get('country') or {}).get('iso3') or '',
                rank=row.get('rank'), gender=gender))
    if not players:
        raise ValueError('Public ranking is empty; keep previous directory')
    return players


def merged_players(stored, current, authoritative=False):
    players = {p['id']: Player.model_validate(p) for p in stored}
    for player in current:
        # A match feed has fewer profile fields and must not erase catalog data.
        previous = players.get(player.id)
        if previous:
            player = player.model_copy(update={
                'gender':player.gender or previous.gender,
                'country':player.country or previous.country,
                'short_name':(player.short_name if authoritative else previous.short_name) or player.short_name,
                'rank':player.rank if authoritative or previous.rank is None else previous.rank})
        players[player.id] = player
    return sorted(players.values(), key=lambda p:(p.rank is None,p.rank or 0,p.name))
