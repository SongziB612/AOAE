"""Cross-check all discovered cash actions with archived primary notices."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd

from aoae.corporate_action_guard import verify_known_action_anchors
from aoae.corporate_action_replay import Action


ROOT = Path(__file__).resolve().parents[1]


def within_root(path):
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError('path outside workspace')
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--secondary-manifest', type=Path, required=True)
    parser.add_argument('--start', default='2022-01-01')
    parser.add_argument('--through', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest_path, output = map(within_root, (args.secondary_manifest, args.output))
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    catalog_path = ROOT / 'configs/forward_action_anchors.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    symbols = {event['symbol'] for event in catalog['events']}
    secondary = {}
    raw_hashes = {}
    for record in manifest['records']:
        if record['symbol'] not in symbols:
            continue
        if record['status'] != 'CAPTURED_NOT_INDEPENDENTLY_VERIFIED':
            raise ValueError('secondary capture incomplete')
        html = manifest_path.parent / (record['symbol'] + '.html')
        raw_hashes[str(html.relative_to(ROOT))] = sha256(html.read_bytes()).hexdigest()
        if raw_hashes[str(html.relative_to(ROOT))] != record['sha256']:
            raise ValueError('secondary HTML changed')
        for table in record['tables']:
            if '除息日' not in table['columns']:
                continue
            for values in table['rows']:
                row = dict(zip(table['columns'], values))
                day = row['除息日']
                if not args.start <= day <= args.through:
                    continue
                match = re.fullmatch(r'每10份派现金([0-9.]+)元', row['每10份分红'])
                if not match:
                    raise ValueError('unparsed secondary dividend')
                key = (record['symbol'], day)
                if key in secondary:
                    raise ValueError('duplicate secondary event')
                secondary[key] = Action(record['symbol'], pd.Timestamp(day), 1.,
                                        float(Decimal(match[1]) / 10),
                                        pd.Timestamp(row['分红发放日']))
    expected = {(e['symbol'], e['date']) for e in catalog['events']
                if args.start <= e['date'] <= args.through}
    if set(secondary) != expected:
        raise ValueError('known-action catalog differs from latest secondary event set')
    checked = verify_known_action_anchors(ROOT, list(secondary.values()), args.start,
                                          args.through, symbols,
                                          datetime.now(timezone.utc).isoformat())
    if set(map(tuple, checked['matched'])) != expected:
        raise ValueError('not all primary anchors matched')
    result = {'status': 'DISCOVERED_CASH_ACTIONS_PRIMARY_AND_SECONDARY_MATCH',
              'start': args.start,
              'through': args.through, 'events': [list(key) for key in sorted(expected)],
              'matched_primary_events': len(expected),
              'known_action_catalog_sha256': checked['catalog_sha256'],
              'input_sha256': {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                               for path in (manifest_path, catalog_path, Path(__file__))},
              'secondary_raw_sha256': raw_hashes,
              'full_action_discovery_complete': False,
              'historical_first_available_time_verified': False,
              'capital_authorized': False,
              'limits': ['The secondary table may omit an event; its selected rows are not a complete official announcements inventory.',
                         'The archive date does not prove intraday historical first availability.',
                         'Only cash distributions, not every split, suspension or tradability condition, are checked.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({'status': result['status'], 'matched_primary_events': len(expected),
                      'output': str(output)}))


if __name__ == '__main__':
    main()
