"""Public Tencent quote vs captured Sina minute/daily close consistency."""
import argparse
import csv
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--minutes', type=Path, required=True)
    p.add_argument('--daily-dir', type=Path, required=True)
    p.add_argument('--day', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError('new workspace directory required')
    codes = ['sh510300', 'sh510500', 'sz159915', 'sh513500', 'sh518880', 'sh511010']
    r = requests.get('https://qt.gtimg.cn/q='+','.join(codes), timeout=20)
    r.raise_for_status()
    now = datetime.now(timezone.utc)
    matches = re.findall(r'v_((?:sh|sz)\d{6})="([^"]*)";', r.content.decode('gbk'))
    if len(matches) != len(codes) or {x[0] for x in matches} != set(codes):
        raise ValueError('missing/duplicate quote')
    rows, hashes = [], {}
    for code, text in matches:
        f = text.split('~')
        if len(f) < 35 or f[2] != code[2:]:
            raise ValueError('unexpected quote schema')
        at = datetime.strptime(f[30], '%Y%m%d%H%M%S').replace(tzinfo=timezone(timedelta(hours=8)))
        if at.date().isoformat() != args.day or at > now or at.hour < 15:
            raise ValueError('quote not from requested closed session')
        price, previous = Decimal(f[3]), Decimal(f[4])
        if not all(x.is_finite() and x > 0 for x in (price, previous)):
            raise ValueError('invalid quote prices')
        path = args.minutes/(code[2:]+'.json')
        bars = json.loads(path.read_text())
        last = next(x for x in bars if x['day'] == args.day+' 15:00:00')
        daily = args.daily_dir/(code[2:]+'.csv')
        with daily.open(encoding='utf-8-sig') as stream:
            past = [x for x in csv.DictReader(stream) if x['date'] < args.day]
        if not past:
            raise ValueError('no preceding daily observation')
        prior = max(past, key=lambda x: x['date'])
        rows.append({'symbol': code[2:], 'quote_at': at.isoformat(), 'quote_last_price': str(price),
                     'sina_minute_last_close': last['close'], 'close_match': price == Decimal(last['close']),
                     'prior_observed_day': prior['date'], 'quote_previous_close': str(previous),
                     'prior_daily_close_match': previous == Decimal(prior['close'])})
        hashes[str(path)] = sha256(path.read_bytes()).hexdigest()
        hashes[str(daily)] = sha256(daily.read_bytes()).hexdigest()
    output.mkdir(parents=True)
    with (output/'quotes-gbk.txt').open('xb') as stream:
        stream.write(r.content)
    report = {'status': 'PRICES_MATCH' if all(x['close_match'] and x['prior_daily_close_match'] for x in rows) else 'MISMATCH',
              'captured_at_utc': now.isoformat(), 'rows': rows, 'input_sha256': hashes,
              'raw_sha256': sha256(r.content).hexdigest(), 'capital_authorized': False, 'orders_authorized': False,
              'limits': 'Public sources may share upstream prices. Quote field positions were inspected, not exchange-certified. Latest post-close quotes do not certify historical corporate actions, tradability, minute-label semantics or executable fills.'}
    with (output/'result.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(report['status'], rows)


if __name__ == '__main__':
    main()
