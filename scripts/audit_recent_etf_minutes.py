"""Verify captured hashes and summarize price-label movement, not model PnL."""
import argparse
import csv
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from aoae.minute_diagnostics import inspect_bars


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--daily-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root) or args.output.exists():
        raise ValueError('new workspace output required')
    manifest = json.loads((args.capture/'manifest.json').read_text())
    details, consistency, sources = {}, [], {}
    for info in manifest['files']:
        if info['status'] != 'RECEIVED_UNREVIEWED':
            raise ValueError('incomplete capture')
        symbol = info['symbol']
        path = args.capture/(symbol+'.json')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != info['parsed_sha256'] or sha256((args.capture/(symbol+'.jsonp')).read_bytes()).hexdigest() != info['raw_sha256']:
            raise ValueError('changed capture')
        days = inspect_bars(json.loads(raw), info['captured_at_utc'])
        details[symbol] = days
        sources[str(path)] = sha256(raw).hexdigest()
        daily = args.daily_dir/(symbol+'.csv')
        sources[str(daily)] = sha256(daily.read_bytes()).hexdigest()
        with daily.open(encoding='utf-8-sig') as stream:
            closes = {r['date']: r['close'] for r in csv.DictReader(stream)}
        for d in days:
            if d['day'] in closes and d['last_close'] is not None:
                difference = abs(Decimal(d['last_close'])-Decimal(closes[d['day']]))
                consistency.append({'symbol': symbol, 'day': d['day'], 'close_difference': str(difference)})
    risks = [s for s in details if s != '511010']
    common = sorted(set.intersection(*[{d['day'] for d in details[s] if d['anchor_eligible']} for s in risks]))
    summaries = {}
    for offset in ('1', '5'):
        values = [Decimal(d['signed_close_to_close_proxy_bps'][offset]) for s in risks for d in details[s] if d['day'] in common]
        summaries[offset] = {'asset_day_rows': len(values), 'distinct_days': len(common),
                             'median_absolute_bps': str(median(map(abs, values))) if values else None,
                             'largest_up_bps': str(max(values)) if values else None,
                             'largest_down_bps': str(min(values)) if values else None}
    result = {'status': 'RECENT_BAR_DIAGNOSTIC_NOT_EXECUTION_VALIDATION', 'common_risk_asset_anchor_days': common,
              'details': details, 'proxy_summaries': summaries, 'daily_consistency': consistency,
              'daily_close_mismatches': sum(Decimal(r['close_difference']) != 0 for r in consistency),
              'source_sha256': sources, 'capital_authorized': False, 'orders_authorized': False,
              'limits': ['Same-source daily consistency is not independent provenance verification.',
                         '09:31 versus 09:32/09:36 bar closes, not orders 1/5 minutes after open; bar timestamp semantics unverified.',
                         'Missing minute labels reported, never forward filled; auction conventions may differ.',
                         'Recent correlated asset-days are not independent strategy trades; no profit inference.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'common_days': common, 'proxies': summaries, 'close_checks': len(consistency), 'mismatches': result['daily_close_mismatches']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
