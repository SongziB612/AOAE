"""Measure a newly verified distribution's effect on a raw-price signal."""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd

from aoae.corporate_action_guard import verify_known_action_anchors
from aoae.corporate_action_replay import Action, total_return_signals


ROOT = Path(__file__).resolve().parents[1]


def inside(path):
    result = path.resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError('path outside workspace')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--secondary-manifest', type=Path, required=True)
    parser.add_argument('--symbol', default='511010')
    parser.add_argument('--ex-date', default='2026-09-18')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    price_path, manifest_path, output = map(inside,
                                           (args.prices, args.secondary_manifest, args.output))
    if output.exists():
        raise FileExistsError(output)
    price_rows = list(csv.DictReader(price_path.open(encoding='utf-8-sig', newline='')))
    days = [row['date'] for row in price_rows]
    if days != sorted(set(days)) or args.ex_date not in days:
        raise ValueError('missing/duplicate/unsorted ex-date prices')
    i = days.index(args.ex_date)
    if i == 0:
        raise ValueError('previous close absent')
    prior = Decimal(price_rows[i - 1]['close'])
    current = Decimal(price_rows[i]['close'])
    if min(prior, current) <= 0:
        raise ValueError('invalid price')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    record = next((r for r in manifest['records'] if r['symbol'] == args.symbol), None)
    if not record or record['status'] != 'CAPTURED_NOT_INDEPENDENTLY_VERIFIED':
        raise ValueError('secondary record missing')
    html = manifest_path.parent / (args.symbol + '.html')
    if sha256(html.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('secondary HTML changed')
    rows = []
    for table in record['tables']:
        if '除息日' not in table['columns']:
            continue
        for values in table['rows']:
            parsed = dict(zip(table['columns'], values))
            if parsed['除息日'] == args.ex_date:
                rows.append(parsed)
    if len(rows) != 1:
        raise ValueError('secondary event missing or duplicated')
    row = rows[0]
    match = re.fullmatch(r'每10份派现金([0-9.]+)元', row['每10份分红'])
    if not match:
        raise ValueError('unparsed secondary cash field')
    cash = Decimal(match[1]) / Decimal(10)
    action = Action(args.symbol, pd.Timestamp(args.ex_date), 1., float(cash),
                    pd.Timestamp(row['分红发放日']))
    decision_at = datetime.now(timezone.utc).isoformat()
    anchored = verify_known_action_anchors(ROOT, [action], days[0], args.ex_date,
                                           (args.symbol,), decision_at)
    panel = pd.DataFrame({args.symbol: [float(prior), float(current)]},
                         index=pd.to_datetime([days[i - 1], args.ex_date]))
    modeled_gross = Decimal(str(total_return_signals(panel, [action]).iloc[-1, 0]))
    raw_return = current / prior - 1
    adjusted_return = (current + cash) / prior - 1
    if abs(modeled_gross - (adjusted_return + 1)) > Decimal('1e-12'):
        raise ValueError('strategy total-return engine disagrees with exact cash arithmetic')
    catalog_path = ROOT / 'configs/forward_action_anchors.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    matching_anchors = [event for event in catalog['events']
                        if (event['symbol'], event['date']) == (args.symbol, args.ex_date)]
    if len(matching_anchors) != 1:
        raise ValueError('known-action catalog event missing or duplicated')
    anchor = {**catalog.get('evidence_bundle', {}), **matching_anchors[0]}
    bound_paths = [price_path, manifest_path, html, Path(__file__),
                   ROOT / 'src/aoae/corporate_action_guard.py',
                   ROOT / 'src/aoae/corporate_action_replay.py', catalog_path]
    bound_paths.extend(ROOT / anchor[key] for key in
                       ('review_path', 'audit_path', 'archive_manifest_path', 'primary_pdf_path'))
    result = {'status': 'KNOWN_DIVIDEND_CORRECTED_IN_SIGNAL_ENGINE',
              'symbol': args.symbol, 'prior_day': days[i - 1], 'ex_date': args.ex_date,
              'previous_raw_close_cny': str(prior), 'ex_date_raw_close_cny': str(current),
              'cash_per_share_cny': str(cash), 'payment_date': row['分红发放日'],
              'raw_close_return': str(raw_return),
              'cash_adjusted_total_return': str(adjusted_return),
              'dividend_adjustment_bps': str(cash / prior * Decimal(10000)),
              'raw_price_false_loss': raw_return < 0 < adjusted_return,
              'known_action_catalog_sha256': anchored['catalog_sha256'],
              'matched_known_actions': anchored['matched'],
              'input_sha256': {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                               for path in bound_paths},
              'full_action_discovery_complete': False,
              'market_observation_not_broker_fill': True,
              'capital_authorized': False,
              'economic_interpretation': 'Cash dividend offsets ex-date price decline; it is not incremental alpha.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ('status', 'raw_close_return',
                                            'cash_adjusted_total_return', 'dividend_adjustment_bps')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
