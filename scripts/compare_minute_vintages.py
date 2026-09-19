"""Check revisions across two saved captures without rewriting either."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--older', type=Path, required=True)
    p.add_argument('--newer', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    snapshots = []
    hashes = {}
    for directory in (args.older, args.newer):
        manifest_path = directory / 'manifest.json'
        hashes[str(manifest_path)] = sha256(manifest_path.read_bytes()).hexdigest()
        symbols = {}
        for item in json.loads(manifest_path.read_text())['files']:
            path = directory / (item['symbol'] + '.json')
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != item['parsed_sha256']:
                raise ValueError('capture hash mismatch')
            rows = json.loads(raw)
            indexed = {r['day']: r for r in rows}
            if len(indexed) != len(rows) or item['symbol'] in symbols:
                raise ValueError('duplicate bar or symbol')
            symbols[item['symbol']] = indexed
        snapshots.append(symbols)
    older, newer = snapshots
    if set(older) != set(newer):
        raise ValueError('different universes')
    checked, changes = 0, []
    for symbol in sorted(older):
        common = older[symbol].keys() & newer[symbol].keys()
        checked += len(common)
        for day in sorted(common):
            fields = [f for f in ('open', 'high', 'low', 'close', 'volume')
                      if Decimal(older[symbol][day][f]) != Decimal(newer[symbol][day][f])]
            if fields:
                changes.append({'symbol': symbol, 'day': day, 'fields': fields})
    report = {'overlap_bars': checked, 'changed_bars': changes, 'manifest_sha256': hashes,
              'status': 'OVERLAP_UNCHANGED' if checked and not changes else 'REVIEW_REQUIRED',
              'limits': 'Two retrospective capture vintages only; not proof of historical first availability or fills.',
              'capital_authorized': False}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
