"""Fail-closed metadata preflight. Never loads price files or opens holdouts."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path


def validate_protocol(protocol):
    previous = None
    for name in ('train', 'validation', 'test'):
        start, end = map(date.fromisoformat, protocol['development_periods'][name])
        if start > end or (previous is not None and start <= previous):
            raise ValueError('overlapping or reversed development periods')
        previous = end
    holdout = protocol['final_holdout']
    start, end, release = [date.fromisoformat(holdout[k]) for k in
                           ('start', 'end', 'release_not_before')]
    if not previous < start <= end < release:
        raise ValueError('invalid holdout boundaries')
    if holdout['access'] != 'SEALED_NO_RESEARCH_READ':
        raise ValueError('holdout must remain sealed')
    horizon = protocol['max_label_horizon_sessions']
    if type(horizon) is not int or horizon < 1:
        raise ValueError('invalid label horizon')
    for key in ('purge_sessions', 'embargo_sessions'):
        if type(protocol[key]) is not int or protocol[key] < horizon:
            raise ValueError('purge/embargo shorter than label horizon')
    universe = protocol['universe']
    if not universe or len(universe) != len(set(universe)):
        raise ValueError('invalid universe')
    evidence = protocol['required_evidence']
    if not evidence or len(evidence) != len(set(evidence)):
        raise ValueError('invalid evidence requirements')
    if protocol.get('capital_authorized') is not False or protocol.get('orders_authorized') is not False:
        raise ValueError('research cannot authorize trading')


def confined(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('path outside repository')
    return path


def preflight(root, protocol):
    """Checks references, not truth of vendor claims or historical PIT quality.

    A complete manifest is only ready for human/independent data review, never
    admitted automatically. Evidence file content, including holdout, is unread.
    """
    root = Path(root).resolve()
    validate_protocol(protocol)
    manifest_path = confined(root, protocol['manifest_path'])
    blockers = []
    digest = None
    if not manifest_path.is_file():
        blockers.append('MISSING_US_ETF_ADMISSION_MANIFEST')
    else:
        payload = manifest_path.read_bytes()
        digest = sha256(payload).hexdigest()
        manifest = json.loads(payload)
        if manifest.get('protocol_id') != protocol['protocol_id']:
            blockers.append('PROTOCOL_MISMATCH')
        if manifest.get('universe') != protocol['universe']:
            blockers.append('UNIVERSE_MISMATCH')
        for key in protocol['required_evidence']:
            ref = manifest.get('evidence', {}).get(key, {})
            hash_value = ref.get('sha256', '')
            valid_hash = isinstance(hash_value, str) and len(hash_value) == 64 and all(c in '0123456789abcdef' for c in hash_value)
            if not ref.get('path') or not valid_hash or not ref.get('source'):
                blockers.append('MISSING_EVIDENCE_REFERENCE:' + key)
            elif not confined(root, ref['path']).is_file():
                blockers.append('MISSING_EVIDENCE_FILE:' + key)
    return {
        'status': 'BLOCKED' if blockers else 'READY_FOR_INDEPENDENT_DATA_REVIEW',
        'blockers': blockers,
        'manifest_sha256': digest,
        'data_admitted': False,
        'holdout_contents_read': False,
        'price_contents_read': False,
        'scope': 'Metadata completeness only; file hashes, vendor rights, PIT vintages and execution must be independently verified before admission.',
        'remaining_research_gates': [
            'Independently verified raw bars, actions and availability vintages',
            'Real exchange calendar, whole-share and cash/receivable execution integration',
            'Frozen candidate and statistical/family-testing protocol before holdout',
            'Net executable OOS advantage versus matched simple baselines',
            'Prospective fills and tail/capacity evidence',
            'Explicit capital ownership/mandate and broker authorization'
        ],
        'capital_authorized': False, 'orders_authorized': False
    }
