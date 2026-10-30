"""Human-readable match alerts, with immutable event context and honest timing."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def match_context(match, snapshot, favorites):
    players = {p.id: p for p in snapshot.players}
    if len(match.players) != 4 or any(id not in players for id in match.players):
        return None
    names = [players[id].short_name or players[id].name.split(' ', 1)[-1] for id in match.players]
    tournament = next((t for t in snapshot.tournaments if t.id == match.tournament_id), None)
    return {'teams': [' / '.join(names[:2]), ' / '.join(names[2:])],
        'followed': ' / '.join(name for id, name in zip(match.players, names) if id in favorites),
        'court': match.court, 'tournament': tournament.name if tournament else '',
        'official_time': match.official_time.isoformat() if match.official_time else None,
        'time_kind': match.time_kind, 'scores': match.scores}


def notification_text(event, language='en', zone='UTC'):
    details = event.get('details')
    if not details:
        return None
    es = language == 'es'
    labels = {
        'scheduled': ('Partido programado', 'Match scheduled'),
        'previous_finished': ('Terminó el anterior', 'Previous match finished'),
        'approaching': ('Calentando', 'Warming up'),
        'started': ('En directo', 'Live now'),
        'finished': ('Resultado final', 'Final result'),
        'schedule_changed': ('Cambio de programación', 'Schedule changed'),
    }
    label = labels.get(event['kind'], ('Actualización', 'Match update'))[0 if es else 1]
    title = f"{details.get('followed') or details['teams'][0]} · {label}"
    body = f"{details['teams'][0]} vs {details['teams'][1]}"
    body += f". {details['court']} · {details['tournament'].title()}."
    if event['kind'] == 'previous_finished':
        body += ' Terminó el partido anterior. Tu partido es el siguiente; pendiente de inicio.' if es else ' Previous match finished. Your match is next; start not yet confirmed.'
    elif event['kind'] == 'approaching':
        body += ' Jugadores en calentamiento.' if es else ' Players are warming up.'
    elif event['kind'] == 'finished' and details.get('scores'):
        body += ' ' + ', '.join(f'{a}–{b}' for a, b in details['scores']) + '.'
    if details.get('official_time') and event['kind'] in {'scheduled', 'previous_finished', 'schedule_changed'}:
        try:
            local = datetime.fromisoformat(details['official_time'].replace('Z', '+00:00')).astimezone(ZoneInfo(zone))
        except (ValueError, ZoneInfoNotFoundError):
            local = datetime.fromisoformat(details['official_time'].replace('Z', '+00:00')).astimezone(ZoneInfo('UTC'))
        prefix = ('No antes de' if es else 'Not before') if details.get('time_kind') == 'not_before' else ('Horario' if es else 'Scheduled')
        body += f" {prefix}: {local:%d/%m %H:%M} {local.tzname()}."
    return {'title': title, 'body': body}
