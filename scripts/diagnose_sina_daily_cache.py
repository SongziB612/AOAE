"""Bounded read-only comparison of default/static daily response and fresh URL."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import time

import akshare as ak
import pandas as pd
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    implementation = ak.fund_etf_hist_sina.__globals__
    decoder = implementation['py_mini_racer'].MiniRacer()
    decoder.eval(implementation['hk_js_decode'])  # Trusted installed decoder, not remote JS.
    url = 'https://finance.sina.com.cn/realstock/company/sh510300/hisdata_klc2/klc_kl.js'
    results = []
    for mode in ('default', 'cache_query'):
        result = {'mode': mode, 'request_started_at': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, params={'_': str(time.time_ns())} if mode == 'cache_query' else None,
                                    timeout=(8, 20))
            result.update(received_at=datetime.now(timezone.utc).isoformat(), status_code=response.status_code,
                          url=response.url, headers={k: v for k, v in response.headers.items()
                                                    if k.lower() in ('date', 'age', 'last-modified', 'cache-control', 'expires', 'etag')})
            raw = response.content
            (args.output_dir / (mode + '.js')).write_bytes(raw)
            result['sha256'] = sha256(raw).hexdigest()
            response.raise_for_status()
            match = re.fullmatch(r'\s*(?:var\s+)?[A-Za-z0-9_$]+\s*=\s*("[^"\r\n]*")\s*;?\s*(?:/\*.*?\*/\s*)*', response.text, re.DOTALL)
            if not match:
                raise ValueError('unrecognized data-only assignment')
            rows = decoder.call('d', json.loads(match[1]))
            dates = pd.to_datetime([r['date'] for r in rows], utc=True)
            result.update(rows=len(rows), latest_date=str(dates.max().date()), status='DECODED_NOT_ADMITTED')
        except Exception as exc:
            result.update(status='FAILED', error=type(exc).__name__ + ': ' + str(exc))
        results.append(result)
    report = {'results': results, 'orders_authorized': False, 'capital_authorized': False,
              'scope': 'One-symbol endpoint cache diagnosis; does not update any ledger or frozen input.'}
    (args.output_dir / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
