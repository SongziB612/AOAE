from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from aoae.research_freeze import verify_freeze


class FreezeTests(unittest.TestCase):
    def test_intact_and_mutated_input(self):
        with patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'read_bytes', return_value=b'original') as read:
            root = Path.cwd()
            record = {'input_sha256': {'input': sha256(b'original').hexdigest()}, 'orders_authorized': False, 'capital_authorized': False, 'broker_connection_authorized': False}
            self.assertEqual(verify_freeze(root, record)['status'], 'INTACT')
            read.return_value = b'changed'
            self.assertEqual(verify_freeze(root, record)['status'], 'INVALIDATED')

    def test_missing_authorization_rejected(self):
        with self.assertRaises(ValueError):
            verify_freeze(Path('.'), {})

    def test_external_path_rejected(self):
        record = {'input_sha256': {'../outside': 'x'}, 'orders_authorized': False, 'capital_authorized': False, 'broker_connection_authorized': False}
        with self.assertRaisesRegex(ValueError, 'outside'):
            verify_freeze(Path.cwd(), record)
