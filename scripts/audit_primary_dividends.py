"""Compare explicitly reviewed primary fields, never infer missing coverage."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re


def audit(manifest, review):
    events = {}
    for record in manifest['records']:
        for table in record.get('tables', []):
            if '除息日' not in table['columns']:
                continue
            for row in table['rows']:
                values = dict(zip(table['columns'], row))
                if '暂无' in str(row):
                    continue
                key = (record['symbol'], values['除息日'])
                if key in events:
                    raise ValueError('duplicate secondary event')
                events[key] = values
    checks, seen = [], set()
    mapping = {'registration_date': '权益登记日', 'payment_date': '分红发放日'}
    for event in review['events']:
        key = (event['symbol'], event['ex_date'])
        if key in seen:
            raise ValueError('duplicate primary event')
        seen.add(key)
        row = events.get(key)
        differences = [] if row else ['event_missing']
        checked = ['ex_date']
        if row:
            for field, column in mapping.items():
                if field in event:
                    checked.append(field)
                    if row[column] != event[field]:
                        differences.append(field)
            if 'cash_per_share' in event:
                checked.append('cash_per_share')
                match = re.fullmatch(r'每10份派现金([0-9.]+)元', row['每10份分红'])
                if not match or Decimal(match[1]) / 10 != Decimal(event['cash_per_share']):
                    differences.append('cash_per_share')
        checks.append({'symbol': key[0], 'ex_date': key[1], 'checked_fields': checked,
                       'differences': differences, 'source_url': event['source_url']})
    return {'status': 'MISMATCH' if any(c['differences'] for c in checks) else 'SELECTED_FIELDS_MATCH',
            'checks': checks, 'secondary_event_count_all_dates': len(events),
            'fully_checked_selected_events': sum(len(c['checked_fields']) == 4 and not c['differences'] for c in checks),
            'unreviewed_event_keys': [list(k) for k in sorted(set(events) - seen)],
            'full_action_coverage_verified': False, 'point_in_time_admitted': False,
            'capital_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    for record in manifest['records']:
        raw = args.manifest.parent / (record['symbol'] + '.html')
        if sha256(raw.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('secondary raw HTML hash mismatch')
    result = audit(manifest, json.loads(args.review.read_text(encoding='utf-8')))
    result['input_sha256'] = {str(p): sha256(p.read_bytes()).hexdigest()
                              for p in (args.manifest, args.review, Path(__file__))}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'input_sha256', 'unreviewed_event_keys')}))


if __name__ == '__main__':
    main()
