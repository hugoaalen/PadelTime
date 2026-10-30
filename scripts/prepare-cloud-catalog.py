"""Backfill device activity metadata and seed a public ranking directory.

No device, token, preference or alert is deleted. Credentials are read locally,
never printed. Run once when upgrading from the original pilot device schema.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from padeltime.cloud import device_is_active, pack
from padeltime.domain import Player
from padeltime.player_catalog import ranking_players, merged_players


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--rankings', type=Path, action='append', default=[])
    args = parser.parse_args()
    ranked = []
    for path in args.rankings:
        raw = json.loads(path.read_text())
        genders = {p.get('gender') for p in raw.get('data', [])}
        if len(genders) != 1 or not genders.issubset({'male', 'female'}):
            raise ValueError('A ranking file must contain one category')
        ranked.extend(ranking_players(raw, next(iter(genders))))
    firebase_admin.initialize_app(credentials.Certificate(str(args.credentials)))
    db = firestore.client()
    count = active = 0

    @firestore.transactional
    def migrate(tx, ref):
        row = ref.get(transaction=tx, timeout=5)
        current = json.loads(row.to_dict()['payload'])
        enabled = device_is_active(current)
        tx.update(ref, {'active': enabled})
        return enabled

    for row in db.collection('devices').limit(100).stream(timeout=10):
        active += migrate(db.transaction(max_attempts=2), row.reference)
        count += 1
    directory_count = None
    if ranked:
        previous = db.collection('catalog').document('players').get(timeout=5)
        stored = json.loads(previous.to_dict()['payload']).get('players', []) if previous.exists else []
        current = db.collection('catalog').document('current').get(timeout=5)
        seen = [Player.model_validate(p) for p in json.loads(current.to_dict()['payload']).get('players', [])] if current.exists else []
        directory = merged_players(stored, ranked, authoritative=True)
        directory = merged_players([p.model_dump(mode='json') for p in directory], seen)
        db.collection('catalog').document('players').set(pack({
            'players': [p.model_dump(mode='json') for p in directory],
            'updated_at': datetime.now(timezone.utc).isoformat()}), timeout=5)
        directory_count = len(directory)
    print(json.dumps({'device_records_checked':count,'active_devices':active,'directory_players':directory_count}))


if __name__ == '__main__':
    main()
