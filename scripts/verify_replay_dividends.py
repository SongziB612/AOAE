"""Bind all 2022-2025 replayed cash events to reviewed primary PDF archives."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path('research/capital_readiness/replay-dividend-primary-gate-2026-09-20.json')
    if output.exists():
        raise FileExistsError(output)
    reference_path = Path('research/capital_readiness/300k-accounting-replay-v4.json')
    bundle = [
        ('research/capital_readiness/primary-dividend-review-2026-09-16.json',
         'research/capital_readiness/primary-dividend-audit-2026-09-16.json',
         'data/audit/primary-dividend-pdfs-2026-09-16-v1/manifest.json'),
        ('research/capital_readiness/primary-dividend-review-2026-09-20.json',
         'research/capital_readiness/primary-dividend-audit-2026-09-20.json',
         'data/audit/primary-dividend-pdfs-2026-09-20-v1/manifest.json'),
        ('research/capital_readiness/primary-dividend-bond-review-2026-09-20.json',
         'research/capital_readiness/primary-dividend-bond-audit-2026-09-20.json',
         'data/audit/primary-dividend-bond-pdfs-2026-09-20-v2/manifest.json'),
    ]
    evidence, hashes = {}, {str(reference_path): digest(reference_path)}
    for review_name, audit_name, manifest_name in bundle:
        review_path, audit_path, manifest_path = map(Path, (review_name, audit_name, manifest_name))
        review, audit, manifest = map(read, (review_path, audit_path, manifest_path))
        hashes.update({str(p): digest(p) for p in (review_path, audit_path, manifest_path)})
        if manifest['review_sha256'] != hashes[str(review_path)] or audit['status'] != 'SELECTED_FIELDS_MATCH':
            raise ValueError('review or selected-field audit changed')
        checked = {(x['symbol'], x['ex_date']) for x in audit['checks']
                   if not x['differences'] and set(x['checked_fields']) ==
                   {'ex_date', 'registration_date', 'payment_date', 'cash_per_share'}}
        files = {(x['symbol'], x['ex_date']): x for x in manifest['records'] if x['status'] == 'ARCHIVED'}
        for event in review['events']:
            key = (event['symbol'], event['ex_date'])
            if key not in checked:
                continue
            if key in evidence or key not in files:
                raise ValueError('duplicate or unarchived primary event: ' + repr(key))
            source = files[key]
            pdf = manifest_path.parent / source['file']
            if source['url'] != event['source_url'] or digest(pdf) != source['sha256']:
                raise ValueError('primary archive changed: ' + repr(key))
            evidence[key] = {'review_path': str(review_path), 'pdf_path': str(pdf),
                             'pdf_sha256': source['sha256'], 'cash_per_share': event['cash_per_share'],
                             'payment_date': event['payment_date']}
    historical = [a for a in read(reference_path)['inferred_actions']
                  if '2022-01-01' <= a['date'] <= '2025-12-31' and a['cash_per_old_share'] > 0]
    actual = {(a['symbol'], a['date']): a for a in historical}
    if len(actual) != len(historical) or set(actual) != set(evidence):
        raise ValueError('cash action coverage mismatch')
    rows = []
    for key, event in sorted(evidence.items()):
        action = actual[key]
        if action['payment_date'] != event['payment_date'] or abs(
                Decimal(str(action['cash_per_old_share'])) - Decimal(event['cash_per_share'])) > Decimal('1e-12'):
            raise ValueError('replay cash or payment mismatch: ' + repr(key))
        rows.append({'symbol': key[0], 'ex_date': key[1], **event, 'status': 'MATCH'})
    result = {'status': 'REPLAYED_CASH_EVENTS_PRIMARY_MATCH', 'year_range': '2022-2025',
              'replay_cash_events': len(rows), 'rows': rows, 'input_sha256': hashes,
              'script_sha256': digest(Path(__file__)),
              'action_discovery_complete': False, 'historical_pit_admitted': False,
              'capital_authorized': False,
              'limits': ['This checks every cash event already in the replay; it does not prove no cash event was omitted.',
                         'PDFs were archived in 2026 and do not establish precise historical first availability.',
                         'Review transcription was manual; this gate only binds reviewed fields, archive hashes, and replay accounting.']}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'status': result['status'], 'replay_cash_events': len(rows), 'output': str(output)}))


if __name__ == '__main__':
    main()
