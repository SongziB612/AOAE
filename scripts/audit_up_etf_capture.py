"""Raw snapshot quality check, not PIT admission; never calculates strategy PnL."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

from aoae.universal_temporal import partition_sessions


def audit(directory, protocol):
    manifest = json.loads((directory / 'capture-manifest.json').read_text(encoding='utf-8'))
    records = manifest['records']
    if [r['symbol'] for r in records] != protocol['universe']:
        raise ValueError('universe mismatch')
    results, calendars = [], []
    for record in records:
        if record['status'] != 'CAPTURED_QUARANTINED':
            raise ValueError('uncaptured symbol')
        payload = (directory / (record['symbol'] + '.json')).read_bytes()
        if sha256(payload).hexdigest() != record['sha256']:
            raise ValueError('snapshot hash mismatch')
        chart = json.loads(payload)['chart']['result'][0]
        if chart['meta']['symbol'] != record['symbol'] or chart['meta']['currency'] != 'USD':
            raise ValueError('symbol/currency mismatch')
        times = chart['timestamp']
        if times != sorted(set(times)) or len(times) != record['observations']:
            raise ValueError('invalid timestamps')
        days = [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in times]
        if len(set(days)) != len(days) or any(not '2007-01-01' <= d <= '2025-12-31' for d in days):
            raise ValueError('duplicate or out-of-scope dates')
        bars = chart['indicators']['quote'][0]
        if any(len(bars[k]) != len(times) for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('column length mismatch')
        issues = []
        for i, day in enumerate(days):
            values = [bars[k][i] for k in ('open', 'high', 'low', 'close', 'volume')]
            if any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
                issues.append({'date': day, 'reason': 'null_or_nonfinite'})
                continue
            o, h, l, c, volume = values
            if min(o, h, l, c) <= 0 or not l <= min(o, c) <= max(o, c) <= h or volume <= 0:
                issues.append({'date': day, 'reason': 'invalid_ohlc_or_nonpositive_volume'})
        dividends = list(chart.get('events', {}).get('dividends', {}).values())
        if any(not math.isfinite(d['amount']) or d['amount'] <= 0 or d['date'] not in times for d in dividends):
            raise ValueError('invalid dividend or ex-date outside bars')
        results.append({'symbol': record['symbol'], 'rows': len(days), 'first': days[0], 'last': days[-1],
                        'raw_sha256': record['sha256'], 'quality_issues': issues,
                        'dividend_ex_events': len(dividends),
                        'split_events': len(chart.get('events', {}).get('splits', {})),
                        'payment_dates_verified': False})
        calendars.append(days)
    aligned = all(days == calendars[0] for days in calendars)
    partition = partition_sessions(calendars[0], protocol) if aligned else None
    return {'status': 'QUALITY_CHECKED_NOT_ADMITTED', 'records': results,
            'observed_calendars_aligned': aligned, 'total_asset_rows': sum(r['rows'] for r in results),
            'unique_observed_sessions': len(set(d for dates in calendars for d in dates)),
            'quality_issue_count': sum(len(r['quality_issues']) for r in results),
            'partitions': partition, 'data_admitted': False, 'capital_authorized': False,
            'blocked_by': ['Historical availability/vintage provenance not established',
                          'Dividend payable dates and investor-specific withholding not established',
                          'Official exchange calendar completeness and cross-source prices not established',
                          'Vendor research permission and raw-price adjustment semantics not reviewed',
                          'Broker/venue execution costs and tradability not established'],
            'interpretation': 'Current public vendor snapshot; aligned rows are not independent samples or a certified exchange calendar. No returns or strategy performance evaluated.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path(__file__).resolve().parents[1]
    protocol_path = root / 'configs/universal_real_protocol.json'
    result = audit(args.data_dir, json.loads(protocol_path.read_text(encoding='utf-8')))
    result['protocol_sha256'] = sha256(protocol_path.read_bytes()).hexdigest()
    result['capture_manifest_sha256'] = sha256((args.data_dir / 'capture-manifest.json').read_bytes()).hexdigest()
    result['source_sha256'] = {name: sha256((root / name).read_bytes()).hexdigest() for name in
        ('scripts/audit_up_etf_capture.py', 'src/aoae/universal_temporal.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'partitions'}, indent=2))


if __name__ == '__main__':
    main()
