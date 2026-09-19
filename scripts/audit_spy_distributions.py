"""Cross-check public SPY ex-date amounts against issuer payable-date table."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    issuer = args.data_dir / 'spdr-historical-distributions.xlsx'
    vendor = args.data_dir / 'SPY.json'
    frame = pd.read_excel(issuer)
    frame = frame[frame['TICKER'].str.strip() == 'SPY'].copy()
    frame['ex'] = pd.to_datetime(frame['EX-DATE'], format='%m/%d/%Y')
    frame['pay'] = pd.to_datetime(frame['PAYABLE DATE'], format='%m/%d/%Y')
    frame = frame[(frame.ex >= '2007-01-01') & (frame.ex <= '2025-12-31')]
    if frame.empty or frame.ex.duplicated().any() or (frame.pay < frame.ex).any():
        raise ValueError('invalid issuer distribution dates')
    amounts = frame[['DIVIDEND ($)', 'SHORT TERM CAPITAL GAIN ($)', 'LONG TERM CAPITAL GAIN ($)']].fillna(0).sum(axis=1)
    issuer_by_day = {str(day.date()): float(value) for day, value in zip(frame.ex, amounts, strict=True)}
    chart = json.loads(vendor.read_bytes())['chart']['result'][0]
    events = chart['events']['dividends'].values()
    vendor_by_day = {datetime.fromtimestamp(e['date'], timezone.utc).date().isoformat(): e['amount'] for e in events}
    common = sorted(set(issuer_by_day) & set(vendor_by_day))
    differences = [abs(issuer_by_day[d] - vendor_by_day[d]) for d in common]
    missing = sorted(set(issuer_by_day) ^ set(vendor_by_day))
    # A declared 0.001 USD rounding envelope; exact mismatch also reported.
    limit = .0005001
    result = {
        'scope': 'SPY only, ex-dates in 2007-2025; currently published issuer table, not historical announcement archive.',
        'status': 'MATCH_WITHIN_DECLARED_ROUNDING' if not missing and common and max(differences) <= limit else 'REVIEW_REQUIRED',
        'issuer_events': len(frame), 'vendor_events': len(vendor_by_day), 'matched_dates': len(common),
        'unmatched_dates': missing, 'maximum_amount_difference_usd_per_share': max(differences, default=None),
        'exact_amount_mismatches_above_1e_9': sum(d > 1e-9 for d in differences),
        'declared_rounding_tolerance_usd': limit,
        'payable_delay_calendar_days_min': int((frame.pay - frame.ex).dt.days.min()),
        'payable_delay_calendar_days_max': int((frame.pay - frame.ex).dt.days.max()),
        'source_url': 'https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx',
        'issuer_sha256': sha256(issuer.read_bytes()).hexdigest(),
        'vendor_sha256': sha256(vendor.read_bytes()).hexdigest(),
        'auditor_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'historical_announcement_times_verified': False, 'investor_tax_verified': False,
        'other_five_etfs_verified': False, 'data_admitted': False, 'capital_authorized': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
