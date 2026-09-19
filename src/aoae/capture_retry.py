"""Bounded capture retries; ledger writes are never retried here."""
import time


def capture_with_retry(attempt, max_attempts=3, delay_seconds=10, sleeper=time.sleep):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError('attempt budget must be 1..3')
    if not 0 <= delay_seconds <= 30:
        raise ValueError('retry delay must be 0..30 seconds')
    results = []
    for number in range(1, max_attempts + 1):
        result = attempt(number)
        results.append(result)
        if result['status'] == 'CURRENT_COMPLETE':
            return {'status': 'CAPTURE_READY', 'attempts': results}
        if number < max_attempts:
            sleeper(delay_seconds)
    return {'status': 'CAPTURE_FAILED_NO_LEDGER_ADVANCE', 'attempts': results}
