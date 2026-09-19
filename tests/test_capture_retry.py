import unittest
from aoae.capture_retry import capture_with_retry


class CaptureRetryTests(unittest.TestCase):
    def test_success_stops_without_sleep(self):
        called, waits = [], []
        result = capture_with_retry(lambda n: called.append(n) or {'status': 'CURRENT_COMPLETE'}, sleeper=waits.append)
        self.assertEqual(result['status'], 'CAPTURE_READY')
        self.assertEqual(called, [1])
        self.assertEqual(waits, [])

    def test_mismatch_then_success(self):
        called, waits = [], []
        def attempt(n):
            called.append(n)
            return {'status': 'CURRENT_COMPLETE' if n == 2 else 'INCOMPLETE_OR_STALE'}
        result = capture_with_retry(attempt, sleeper=waits.append)
        self.assertEqual(result['status'], 'CAPTURE_READY')
        self.assertEqual(called, [1, 2])
        self.assertEqual(waits, [10])

    def test_exhaustion_preserves_failures(self):
        waits = []
        result = capture_with_retry(lambda n: {'status': 'FETCH_FAILED', 'attempt': n}, sleeper=waits.append)
        self.assertEqual(result['status'], 'CAPTURE_FAILED_NO_LEDGER_ADVANCE')
        self.assertEqual(len(result['attempts']), 3)
        self.assertEqual(waits, [10, 10])

    def test_invalid_budget_rejected(self):
        for budget in (0, 4):
            with self.assertRaises(ValueError):
                capture_with_retry(lambda n: {}, max_attempts=budget)
        with self.assertRaises(ValueError):
            capture_with_retry(lambda n: {}, delay_seconds=31)
