"""Bounded public read-only capture; no eval of downloaded factor payloads."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import requests
import py_mini_racer
from akshare.stock.cons import hk_js_decode


def capture(symbol, output, source_dir=None):
    prefix = 'sz' if symbol.startswith('15') else 'sh'
    base = f'https://finance.sina.com.cn/realstock/company/{prefix}{symbol}'
    record = {'symbol': symbol, 'sources': {}}
    for kind, url in [('prices', base + '/hisdata_klc2/klc_kl.js'), ('factors', base + '/hfq.js')]:
        try:
            if source_dir is None:
                response = requests.get(url, timeout=(8, 20))
                response.raise_for_status()
                payload = response.content
            else:
                payload = (source_dir / f'{symbol}-{kind}.txt').read_bytes()
            path = output / f'{symbol}-{kind}.txt'
            with path.open('xb') as stream:
                stream.write(payload)
            source = {'url': url, 'sha256': sha256(payload).hexdigest(), 'path': str(path)}
            record['sources'][kind] = source
            body = payload.decode('utf-8').split('=', 1)[1].strip()
            # Parse a JSON value only; do not execute appended JS/comments.
            parsed, _ = json.JSONDecoder().raw_decode(body)
            if kind == 'prices':
                with py_mini_racer.MiniRacer() as runtime:
                    runtime.eval(hk_js_decode)
                    decoded = runtime.call('d', parsed)
                frame = pd.DataFrame(decoded)
                frame['date'] = pd.to_datetime(frame['date']).dt.tz_localize(None).dt.normalize()
                frame = frame[(frame['date'] >= '2015-01-01') & (frame['date'] <= '2026-08-31')].sort_values('date')
                if frame.empty or frame.date.duplicated().any():
                    raise ValueError('empty or duplicate dates')
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    frame[col] = pd.to_numeric(frame[col], errors='raise')
                if frame[['open', 'high', 'low', 'close', 'volume']].isna().any().any():
                    raise ValueError('missing values')
                if (frame[['open', 'high', 'low', 'close']] <= 0).any().any():
                    raise ValueError('nonpositive prices')
                csv = output / f'{symbol}.csv'
                frame.to_csv(csv, index=False, mode='x', date_format='%Y-%m-%d')
                source.update(rows=len(frame), first=str(frame.date.iloc[0].date()), last=str(frame.date.iloc[-1].date()), csv_sha256=sha256(csv.read_bytes()).hexdigest())
            else:
                decoded = parsed
                if not isinstance(decoded, dict) or 'data' not in decoded:
                    raise ValueError('unsupported factor schema')
                source['decoded'] = decoded
            source['status'] = 'CAPTURED_NOT_ADMITTED'
        except Exception as exc:
            record.setdefault('errors', {})[kind] = type(exc).__name__ + ': ' + str(exc)[:250]
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--source-dir', type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    symbols = ['510300', '510500', '159915', '513500', '518880', '511010']
    # V8 initialization is process-global and unsafe under concurrent first use.
    with ThreadPoolExecutor(max_workers=1) as pool:
        records = list(pool.map(lambda symbol: capture(symbol, args.output_dir, args.source_dir), symbols))
    result = {'processed_at_utc': datetime.now(timezone.utc).isoformat(), 'source_dir': str(args.source_dir) if args.source_dir else None, 'records': records,
              'status': 'UNVERIFIED_PUBLIC_EVIDENCE', 'capital_authorized': False,
              'redistribution_authorized': False,
              'warning': 'Adjustment factors are not a verified dividend payment or split ledger.'}
    with (args.output_dir / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
