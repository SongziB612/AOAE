"""Session-based chronological partitions, with explicit gaps and no holdout read."""
from datetime import date

from aoae.universal_readiness import validate_protocol


def partition_sessions(sessions, protocol):
    validate_protocol(protocol)
    parsed = [date.fromisoformat(day) for day in sessions]
    if not parsed or parsed != sorted(set(parsed)):
        raise ValueError('sessions must be nonempty unique chronological dates')
    cutoff = date.fromisoformat(protocol['final_holdout']['start'])
    if parsed[-1] >= cutoff:
        raise ValueError('final holdout dates cannot enter development partition')
    parts, excluded = {}, {}
    names = ('train', 'validation', 'test')
    for i, name in enumerate(names):
        start, end = map(date.fromisoformat, protocol['development_periods'][name])
        rows = [day for day in parsed if start <= day <= end]
        left = protocol['embargo_sessions'] if i else 0
        right = protocol['purge_sessions'] if i < len(names) - 1 else 0
        if len(rows) <= left + right:
            raise ValueError('insufficient sessions after purge/embargo: ' + name)
        parts[name] = [d.isoformat() for d in rows[left:len(rows) - right if right else None]]
        excluded[name] = [d.isoformat() for d in rows[:left] + (rows[-right:] if right else [])]
    return {'partitions': parts, 'excluded': excluded,
            'calendar_status': 'INPUT_SESSIONS_ONLY_EXCHANGE_COMPLETENESS_NOT_CERTIFIED',
            'final_holdout_read': False,
            'scope': 'Date partition only. Warm-up, labels, normalization and fitting must separately respect these boundaries.'}
