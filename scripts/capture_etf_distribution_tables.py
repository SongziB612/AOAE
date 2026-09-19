"""Capture public per-fund dividend/split tables with bounded timeouts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path

import pandas as pd
import requests


def fetch(symbol, directory):
    url = f'https://fundf10.eastmoney.com/fhsp_{symbol}.html'
    result = {'symbol': symbol, 'url': url}
    try:
        response = requests.get(url, timeout=(8, 20))
        response.raise_for_status()
        response.encoding = 'utf-8'
        raw = directory / f'{symbol}.html'
        with raw.open('xb') as stream:
            stream.write(response.content)
        result['sha256'] = sha256(response.content).hexdigest()
        result['tables'] = []
        for table in pd.read_html(StringIO(response.text)):
            result['tables'].append({'columns': [str(c) for c in table.columns], 'rows': table.fillna('').astype(str).values.tolist()})
        result['status'] = 'CAPTURED_NOT_INDEPENDENTLY_VERIFIED'
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)[:250]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda s: fetch(s, args.output_dir), ['510300', '510500', '159915', '513500', '518880', '511010']))
    result = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'records': records, 'capital_authorized': False, 'redistribution_authorized': False}
    with (args.output_dir / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
