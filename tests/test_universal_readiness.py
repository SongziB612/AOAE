import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from aoae.universal_readiness import preflight, validate_protocol


class UniversalReadinessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.protocol = json.loads((Path(__file__).resolve().parents[1] /
            'configs/universal_real_protocol.json').read_text(encoding='utf-8'))

    def test_locked_protocol(self):
        validate_protocol(self.protocol)

    def test_missing_data_blocks_and_does_not_authorize_capital(self):
        with patch.object(Path, 'is_file', return_value=False), patch.object(Path, 'read_bytes', side_effect=AssertionError('must not read missing data')):
            result = preflight(self.root, self.protocol)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['data_admitted'])
        self.assertFalse(result['capital_authorized'])
        self.assertFalse(result['holdout_contents_read'])

    def test_overlap_rejected(self):
        self.protocol['development_periods']['test'][0] = '2018-01-01'
        with self.assertRaises(ValueError):
            validate_protocol(self.protocol)

    def test_short_embargo_rejected(self):
        self.protocol['embargo_sessions'] = 0
        with self.assertRaises(ValueError):
            validate_protocol(self.protocol)

    def test_unsealed_holdout_rejected(self):
        self.protocol['final_holdout']['access'] = 'OPEN'
        with self.assertRaises(ValueError):
            validate_protocol(self.protocol)

    def test_no_path_escape(self):
        self.protocol['manifest_path'] = '../outside.json'
        with self.assertRaises(ValueError):
            preflight(self.root, self.protocol)

    def test_capital_switch_rejected(self):
        self.protocol['capital_authorized'] = True
        with self.assertRaises(ValueError):
            validate_protocol(self.protocol)

    def test_complete_metadata_still_does_not_admit_data(self):
        ref = {'path': 'sealed.bin', 'sha256': '0' * 64, 'source': 'test fixture'}
        manifest = {'protocol_id': self.protocol['protocol_id'],
                    'universe': self.protocol['universe'],
                    'evidence': {key: copy.copy(ref) for key in self.protocol['required_evidence']}}
        def read_manifest_only(path):
            self.assertEqual(path, (self.root / self.protocol['manifest_path']).resolve())
            return json.dumps(manifest).encode('utf-8')
        with patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'read_bytes', read_manifest_only):
            result = preflight(self.root, self.protocol)
            self.assertEqual(result['status'], 'READY_FOR_INDEPENDENT_DATA_REVIEW')
            self.assertFalse(result['data_admitted'])
            self.assertFalse(result['price_contents_read'])
            manifest['universe'] = ['510300']
            self.assertIn('UNIVERSE_MISMATCH', preflight(self.root, self.protocol)['blockers'])


if __name__ == '__main__':
    unittest.main()
