import asyncio
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from padeltime.collectors import premier
from padeltime.collectors.matchscorer import WIDGET, apply_widget_order, widget_path
from padeltime.cloud_state import evolve

FIXTURES = Path(__file__).parent / 'fixtures'
URL = WIDGET + '/screen/oopbyday/FIP-2026-4902/8?t=tol'


def semifinal():
    record = premier.tournament_records((FIXTURES / 'premier-page.html').read_text())[0]
    players, matches = {}, {}
    for gender in ('male', 'female'):
        p, m = premier.normalize_schedule(json.loads((FIXTURES / f'premier-semifinals-{gender}.json').read_text()),
            premier.normalize_tournament(record), 'Europe/Rome', '2026-10-17')
        players.update(p)
        matches.update(m)
    return record, players, matches, (FIXTURES / 'matchscorer-milano-semifinals.html').read_text()


def test_real_mixed_court_sequence_including_followed_by():
    _, players, matches, html = semifinal()
    assert apply_widget_order(matches, players, html, URL) == 1
    assert [m.id for m in sorted(matches.values(), key=lambda m: m.order)] == [
        'pp-m-18883', 'pp-m-18884', 'pp-m-18885', 'pp-m-18886']
    assert all(m.order_confirmed and m.source_url == URL for m in matches.values())
    assert matches['pp-m-18884'].official_time is None  # Followed by, not a made-up timestamp.


def test_incomplete_ambiguous_or_wrong_day_cannot_confirm_order():
    for change in ('missing', 'ambiguous', 'different_day', 'unknown', 'wrong_pairs'):
        _, players, matches, html = semifinal()
        if change == 'missing':
            matches.pop('pp-m-18885')
        elif change == 'ambiguous':
            player = next(p for p in players.values() if p.name == 'Arturo Coello')
            players['duplicate'] = player.model_copy(update={'id': 'duplicate'})
        elif change == 'different_day':
            html = html.replace('play-day-button active', 'play-day-button')
        elif change == 'unknown':
            html = html.replace('Triay Pons', 'Unknown Player')
        else:
            match = matches['pp-m-18884']
            match.players[1], match.players[2] = match.players[2], match.players[1]
        assert apply_widget_order(matches, players, html, URL) == 0
        assert not any(m.order_confirmed for m in matches.values())


def test_metadata_drives_widget_day_without_hardcoded_tournament_ids():
    record, _, _, _ = semifinal()
    record.update(year=2026, organization='FIP')
    assert widget_path(record, '2026-10-17') == '/screen/oopbyday/FIP-2026-4902/8?t=tol'
    assert widget_path(record, '2026-10-09') is None
    record.update(event_code='4410', start_date_utc='2026-10-23T00:00:00Z', end_date_utc='2026-10-31T00:00:00Z')
    assert widget_path(record, '2026-10-23') == '/screen/oopbyday/FIP-2026-4410/1?t=tol'


def test_verified_predecessor_finish_produces_one_alert_and_replay_none(monkeypatch):
    from padeltime import cloud
    record, players, matches, html = semifinal()
    apply_widget_order(matches, players, html, URL)
    for match in matches.values():
        match.status = 'SCHEDULED'
    matches['pp-m-18883'].status = 'LIVE'
    snapshot = premier.Snapshot(fetched_at=datetime.now(timezone.utc), date='2026-10-17',
        tournaments=[premier.normalize_tournament(record)], players=list(players.values()), matches=list(matches.values()))
    device = {'favorites': ['pp-p-14945'], 'enabled': True, 'events': []}  # Coello follows the women's match.
    previous, updates = evolve(None, snapshot, {'phone': device})
    matches['pp-m-18883'].status = 'FINISHED'
    snapshot.matches = list(matches.values())
    current, updates = evolve(previous, snapshot, updates)
    alerts = [e for e in updates['phone']['events'] if e['kind'] == 'previous_finished']
    assert len(alerts) == 1 and alerts[0]['match_id'] == 'pp-m-18884'
    assert evolve(current, snapshot, updates)[1] == {}
    device = {**updates['phone'], 'token': 'test-token', 'language': 'es'}
    delivered = []
    monkeypatch.setattr(cloud, 'device_list', lambda: {'phone': copy.deepcopy(device)})
    monkeypatch.setattr(cloud, 'put_device', lambda identity, patch: device.update(patch))
    monkeypatch.setattr(cloud, 'send_push', lambda token, event: delivered.append(event))
    cloud.deliver()
    assert len([event for event in delivered if event['kind'] == 'previous_finished']) == 1
    assert cloud.deliver() == 0
    assert any('Terminó el partido anterior' in cloud.push_message(event) for event in delivered)


@pytest.mark.parametrize('next_day_failure', [False, True])
def test_collector_fetches_tomorrow_and_joins_widget(monkeypatch, tmp_path, next_day_failure):
    record, _, _, html = semifinal()
    record.update(year=2026, organization='FIP')
    page = '<script>self.__next_f.push(' + json.dumps([1, '0:' + json.dumps({'tournament': record})]) + ')</script>'
    requested = []

    async def request(self, origin, path, body=None):
        requested.append((origin, path, copy.deepcopy(body)))
        if origin == premier.SITE:
            return httpx.Response(200, text=page)
        if origin == WIDGET:
            return httpx.Response(200, text=html)
        if body['date'] == '2026-10-17':
            return httpx.Response(200, json=json.loads((FIXTURES / f"premier-semifinals-{body['gender']}.json").read_text()))
        if next_day_failure:
            raise httpx.ReadTimeout('Next-day source unavailable')
        return httpx.Response(200, json={'status': True, 'data': {'courts': []}})

    monkeypatch.setattr(premier.PublicClient, 'request', request)
    snapshot = asyncio.run(premier.collect('2026-10-17', record['slug'], tmp_path / 'capture.json', include_next_day=True))
    assert len(snapshot.matches) == 4 and all(m.order_confirmed for m in snapshot.matches)
    assert snapshot.coverage == {'pp-t-274': ['2026-10-17']}
    assert {body['date'] for origin, _, body in requested if origin == premier.API} == {'2026-10-17', '2026-10-18'}
    assert any(('unavailable' if next_day_failure else 'not published') in warning for warning in snapshot.warnings)


def test_cloud_discovers_tomorrows_tournament_before_it_starts(monkeypatch):
    from padeltime import cloud
    record, _, _, _ = semifinal()
    record.update(slug='kuwait-p1-2', timezone='Asia/Riyadh',
        start_date_utc='2026-10-23T00:00:00Z', end_date_utc='2026-10-31T00:00:00Z')
    page = '<script>self.__next_f.push(' + json.dumps([1, '0:' + json.dumps(record)]) + ')</script>'
    requested = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 22, 10, tzinfo=timezone.utc).astimezone(tz)

    async def request(*args, **kwargs):
        return httpx.Response(200, text=page)

    async def collect(day, slug, path, include_next_day=False):
        requested.append((day, slug, include_next_day))
        return 'capture'

    monkeypatch.setattr(cloud, 'datetime', Clock)
    monkeypatch.setattr(cloud.PublicClient, 'request', request)
    monkeypatch.setattr(cloud, 'collect', collect)
    assert asyncio.run(cloud.discover_snapshot(None)) == ('capture', 'running')
    assert requested == [('2026-10-23', 'kuwait-p1-2', True)]
