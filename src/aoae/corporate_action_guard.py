"""Bind known primary corporate actions to prospective signal inputs.

This rejects omissions of known events; it is not a completeness oracle for
events that nobody has discovered yet.
"""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from aoae.paired_forward import timestamp


def _bound_json(root, name, expected_sha256):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('corporate action evidence outside workspace')
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('corporate action evidence changed: ' + name)
    return json.loads(raw)


def verify_known_action_anchors(root, actions, first_day, signal_day, symbols, decision_at):
    """Check discovered primary events, and return a digest to bind the signal."""
    catalog_path = root / 'configs/forward_action_anchors.json'
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw)
    if (catalog.get('status') != 'KNOWN_EVENTS_ONLY_NOT_COMPLETE'
            or catalog.get('full_action_discovery_complete') is not False
            or catalog.get('capital_authorized') is not False):
        raise ValueError('invalid known-action catalog status')
    indexed = {(a.symbol, str(a.date.date())): a for a in actions}
    if len(indexed) != len(actions):
        raise ValueError('duplicate signal action')
    seen, matched = set(), []
    for event in catalog['events']:
        bundle_id = event.get('evidence_bundle_id')
        bundle = (catalog.get('evidence_bundles', {}).get(bundle_id)
                  if bundle_id is not None else catalog.get('evidence_bundle', {}))
        if bundle is None:
            raise ValueError('unknown corporate action evidence bundle')
        item = {**bundle, **event}
        key = (item['symbol'], item['date'])
        if key in seen:
            raise ValueError('duplicate known-action anchor')
        seen.add(key)
        date.fromisoformat(item['date'])
        date.fromisoformat(item['payment_date'])
        if date.fromisoformat(item['publication_date']) > date.fromisoformat(item['date']):
            raise ValueError('known action published after ex-date')
        if not first_day <= item['date'] <= signal_day or item['symbol'] not in symbols:
            continue
        review = _bound_json(root, item['review_path'], item['review_sha256'])
        audit = _bound_json(root, item['audit_path'], item['audit_sha256'])
        manifest = _bound_json(root, item['archive_manifest_path'], item['archive_manifest_sha256'])
        if not any(e['symbol'] == key[0] and e['ex_date'] == key[1]
                   and e['cash_per_share'] == item['cash_per_old_share']
                   and e['payment_date'] == item['payment_date']
                   and e['publication_date'] == item['publication_date']
                   and e['source_url'] == item['source_url'] for e in review['events']):
            raise ValueError('primary review does not match known action')
        if manifest.get('review_sha256') != item['review_sha256']:
            raise ValueError('primary archive does not bind review')
        audit_inputs = {name.replace('\\', '/'): digest
                        for name, digest in audit.get('input_sha256', {}).items()}
        if audit_inputs.get(item['review_path']) != item['review_sha256']:
            raise ValueError('secondary audit does not bind review')
        if audit['status'] != 'SELECTED_FIELDS_MATCH' or not any(
                c['symbol'] == key[0] and c['ex_date'] == key[1]
                and not c['differences'] and set(c['checked_fields']) ==
                {'ex_date', 'registration_date', 'payment_date', 'cash_per_share'}
                for c in audit['checks']):
            raise ValueError('independent selected-field check missing')
        source = next((r for r in manifest['records'] if r['symbol'] == key[0]
                       and r['ex_date'] == key[1] and r['status'] == 'ARCHIVED'), None)
        if (source is None or source['url'] != item['source_url']
                or source['sha256'] != item['primary_pdf_sha256']
                or timestamp(source['received_at_utc']) > timestamp(decision_at)):
            raise ValueError('primary archive not available or mismatched')
        pdf = (root / item['primary_pdf_path']).resolve()
        if (not pdf.is_relative_to(root.resolve()) or pdf.name != source['file']
                or sha256(pdf.read_bytes()).hexdigest() != item['primary_pdf_sha256']):
            raise ValueError('primary PDF changed or missing')
        observed = indexed.get(key)
        if (observed is None or Decimal(str(observed.ratio)) != Decimal(item['ratio'])
                or Decimal(str(observed.cash_per_old_share)) != Decimal(item['cash_per_old_share'])
                or observed.payment_date is None
                or str(observed.payment_date.date()) != item['payment_date']):
            raise ValueError('known corporate action missing or mismatched: ' + repr(key))
        matched.append(key)
    return {'catalog_sha256': sha256(raw).hexdigest(), 'matched': matched,
            'full_action_discovery_complete': False}
