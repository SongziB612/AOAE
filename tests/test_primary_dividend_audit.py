import unittest
from scripts.audit_primary_dividends import audit


class PrimaryDividendAuditTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'records': [{'symbol': '510300', 'tables': [{
            'columns': ['除息日', '权益登记日', '每10份分红', '分红发放日'],
            'rows': [['2026-01-19', '2026-01-16', '每10份派现金1.2300元', '2026-01-27']]}]}]}
        self.event = {'symbol': '510300', 'ex_date': '2026-01-19',
                      'registration_date': '2026-01-16', 'payment_date': '2026-01-27',
                      'cash_per_share': '0.123', 'source_url': 'test'}

    def test_exact_amount_and_dates(self):
        result = audit(self.manifest, {'events': [self.event]})
        self.assertEqual(result['fully_checked_selected_events'], 1)
        self.assertFalse(result['point_in_time_admitted'])

    def test_early_settlement_is_not_payment(self):
        self.event['payment_date'] = '2026-01-26'
        self.assertEqual(audit(self.manifest, {'events': [self.event]})['status'], 'MISMATCH')

    def test_partial_evidence_is_not_full_review(self):
        event = {k: self.event[k] for k in ('symbol', 'ex_date', 'source_url')}
        result = audit(self.manifest, {'events': [event]})
        self.assertEqual(result['fully_checked_selected_events'], 0)
        self.assertFalse(result['full_action_coverage_verified'])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.manifest, {'events': [self.event, self.event]})
