"""Bounded public minute capture. JSONP parsed as JSON, never executed."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import requests


SYMBOLS = ('510300', '510500', '159915', '513500', '518880', '511010')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('new workspace directory required')
    output.mkdir(parents=True)
    def capture(symbol):
        row = {'symbol': symbol, 'captured_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get('https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData',
                                    params={'symbol': ('sz' if symbol.startswith('15') else 'sh')+symbol,
                                            'scale': '1', 'ma': 'no', 'datalen': '1970'}, timeout=20)
            response.raise_for_status()
            text = response.text
            start, end = text.index('=(')+2, text.rindex(');')
            data = json.loads(text[start:end])
            if not isinstance(data, list) or not data:
                raise ValueError('empty or invalid JSONP data')
            raw = response.content
            with (output/(symbol+'.jsonp')).open('xb') as stream:
                stream.write(raw)
            with (output/(symbol+'.json')).open('x', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
            row.update(status='RECEIVED_UNREVIEWED', rows=len(data), first=data[0]['day'], last=data[-1]['day'],
                       raw_sha256=sha256(raw).hexdigest(), parsed_sha256=sha256((output/(symbol+'.json')).read_bytes()).hexdigest())
        except Exception as exc:
            row.update(status='FAILED', error_type=type(exc).__name__)
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(capture, SYMBOLS))
    manifest = {'provider': 'Sina public CN_MarketDataService.getKLineData', 'scale': 1,
                'requested_bars': 1970, 'adjustment': 'raw endpoint request', 'files': rows,
                'capital_authorized': False, 'orders_authorized': False,
                'limits': 'Unreviewed recent bars; not orderbook snapshots, historical PIT certification or observed fills.'}
    with (output/'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == '__main__':
    main()
