"""Content-bound research freeze; never grants capital or claims observation."""
from hashlib import sha256
from pathlib import Path


def verify_freeze(root: Path, record: dict) -> dict:
    root = root.resolve()
    if any(record.get(k) is not False for k in ('capital_authorized', 'orders_authorized', 'broker_connection_authorized')):
        raise ValueError('research authorization flags must be false')
    hashes = record.get('input_sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('empty freeze')
    changed = []
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('input outside research root')
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(relative)
    return {'status': 'INTACT' if not changed else 'INVALIDATED', 'changed_inputs': changed,
            'eligible_to_collect_new_evidence': not changed, 'capital_authorized': False,
            'note': 'Integrity does not prove execution readiness, data correctness or profitability.'}
