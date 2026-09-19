"""Bounded unauthenticated historical capture, quarantined NOT admitted.

No account/API key, no strategy, no adjusted-close trading, no holdout request.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import requests


def capture(symbol, output, start, end):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol
    params = {'period1': start, 'period2': end, 'interval': '1d',
              'events': 'div,splits', 'includeAdjustedClose': 'true'}
    record = {'symbol': symbol, 'url': url, 'parameters': params,
              'status': 'FAILED', 'data_admitted': False}
    try:
        response = requests.get(url, params=params, timeout=(10, 30),
                                headers={'User-Agent': 'AOAE-research/0.1'})
        record.update(http_status=response.status_code, server_date=response.headers.get('Date'))
        response.raise_for_status()
        payload = response.content
        with (output / (symbol + '.json')).open('xb') as stream:
            stream.write(payload)
        record['sha256'] = sha256(payload).hexdigest()
        parsed = response.json()['chart']
        if parsed['error']:
            raise ValueError('provider returned chart error')
        chart = parsed['result'][0]
        timestamps = chart['timestamp']
        if not timestamps or len(set(timestamps)) != len(timestamps) or any(t < start or t >= end for t in timestamps):
            raise ValueError('empty, duplicate or out-of-request timestamps')
        record.update(status='CAPTURED_QUARANTINED', observations=len(timestamps),
                      first_utc=datetime.fromtimestamp(min(timestamps), timezone.utc).isoformat(),
                      last_utc=datetime.fromtimestamp(max(timestamps), timezone.utc).isoformat(),
                      dividend_events=len(chart.get('events', {}).get('dividends', {})),
                      split_events=len(chart.get('events', {}).get('splits', {})))
    except Exception as exc:
        record['error'] = type(exc).__name__ + ': ' + str(exc)[:200]
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if not output.is_relative_to(root / 'data'):
        raise ValueError('raw evidence must remain under data/')
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((root / 'configs/universal_real_protocol.json').read_text(encoding='utf-8'))
    start = int(datetime(2007, 1, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda s: capture(s, output, start, end), protocol['universe']))
    result = {'capture_time_utc': datetime.now(timezone.utc).isoformat(), 'records': records,
              'status': 'QUARANTINED', 'data_admitted': False, 'capital_authorized': False,
              'redistribution_authorized': False,
              'limits': ['Current vendor snapshot, not historical availability vintages.',
                         'Dividend ex-dates do not establish payable dates or withholding.',
                         'Raw column adjustment semantics, permissions, calendar, and cross-provider values require review.',
                         'No future final holdout requested. No returns or strategy statistics calculated.']}
    with (output / 'capture-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
