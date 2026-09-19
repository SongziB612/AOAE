"""Point-in-time metadata gate, inspired by TradingAgents date-window guards.

Original implementation; no upstream code/dependencies imported. Assertions
about publication/vintage still require source-content verification.
"""
from aoae.paired_forward import timestamp


def validate_source_timing(review, decision_at):
    """Fail closed for missing/ambiguous timestamps, revisions and future lessons.

    Publication is not observation date. Captured time refers to the exact bytes
    bound by the source digest. Use first_available_at for this specific vintage,
    never the economic period a subsequently revised statistic describes.
    """
    decision = timestamp(decision_at)
    reviewed = timestamp(review['reviewed_at'])
    if reviewed > decision:
        raise ValueError('review after decision')
    hashes = review['source_sha256']
    provenance = review.get('source_provenance', {})
    if not hashes or set(hashes) != set(provenance):
        raise ValueError('each source requires point-in-time provenance')
    for name, expected in hashes.items():
        entry = provenance[name]
        if entry['sha256'] != expected:
            raise ValueError('provenance digest mismatch')
        if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('invalid source digest')
        published = timestamp(entry['published_at'])
        available = timestamp(entry['first_available_at'])
        captured = timestamp(entry['captured_at'])
        if not published <= available <= captured <= reviewed <= decision:
            raise ValueError('source unavailable before review/decision')
        kind = entry['kind']
        if kind not in ('market_data', 'corporate_action', 'calendar', 'news', 'macro', 'decision_lesson'):
            raise ValueError('unsupported source kind')
        if kind == 'macro':
            vintage = timestamp(entry['vintage_available_at'])
            if not published <= vintage <= available:
                raise ValueError('macro vintage not available at claimed time')
        if kind == 'decision_lesson':
            resolved = timestamp(entry['outcome_known_at'])
            if resolved > available:
                raise ValueError('lesson contains not-yet-known outcome')
    return {'status': 'TIMING_METADATA_VALIDATED_NOT_FACT_VERIFIED', 'sources': len(hashes)}
