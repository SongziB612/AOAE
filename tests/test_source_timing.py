from copy import deepcopy
import unittest
from aoae.source_timing import validate_source_timing


class SourceTimingTests(unittest.TestCase):
    def setUp(self):
        self.at = '2026-09-10T08:00:00+00:00'
        self.source = {'sha256': 'a' * 64, 'kind': 'news',
                       'published_at': '2026-09-10T07:00:00+00:00',
                       'first_available_at': '2026-09-10T07:01:00+00:00',
                       'captured_at': '2026-09-10T07:02:00+00:00'}
        self.review = {'reviewed_at': '2026-09-10T07:03:00+00:00', 'source_sha256': {'fixture': 'a' * 64},
                       'source_provenance': {'fixture': self.source}}

    def test_valid_input_is_not_modified_or_authorized(self):
        before = deepcopy(self.review)
        result = validate_source_timing(self.review, self.at)
        self.assertEqual(result['sources'], 1)
        self.assertNotIn('capital_authorized', result)
        self.assertEqual(before, self.review)

    def test_future_source_rejected(self):
        self.source['first_available_at'] = '2026-09-11T00:00:00+00:00'
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_review_before_capture_rejected(self):
        self.source['captured_at'] = '2026-09-10T07:04:00+00:00'
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_missing_provenance_and_ambiguous_timezone_rejected(self):
        self.review['source_provenance'] = {}
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)
        self.review['source_provenance'] = {'fixture': self.source}
        self.source['published_at'] = '2026-09-10T07:00:00'
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_digest_mismatch_rejected(self):
        self.source['sha256'] = 'b' * 64
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_future_macro_revision_rejected(self):
        self.source['kind'] = 'macro'
        self.source['vintage_available_at'] = '2026-09-11T07:00:00+00:00'
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_unresolved_lesson_rejected(self):
        self.source['kind'] = 'decision_lesson'
        self.source['outcome_known_at'] = '2026-09-15T07:00:00+00:00'
        with self.assertRaises(ValueError):
            validate_source_timing(self.review, self.at)

    def test_timezone_equivalence(self):
        self.source['published_at'] = '2026-09-10T15:00:00+08:00'
        self.assertEqual(validate_source_timing(self.review, self.at)['sources'], 1)
