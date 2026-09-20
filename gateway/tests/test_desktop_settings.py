import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from desktop_settings import public_settings, save_settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = {'endpoint': 'https://example.invalid/v1', 'model': 'test-model',
                        'protocol': 'chat-completions', 'secret': 'FAKE-KEY-FOR-TEST', 'consent': True}
        self.write = Mock()
        self.read = Mock(return_value='')

    def test_saves_only_public_fields(self):
        result = save_settings(self.root, self.payload, self.read, self.write)
        self.assertTrue(result['saved'])
        self.assertNotIn(self.payload['secret'], json.dumps(result))
        saved = (self.root / 'ai-service.json').read_text()
        self.assertNotIn(self.payload['secret'], saved)
        self.assertEqual(json.loads(saved)['endpoint'], 'https://example.invalid/v1/chat/completions')
        self.write.assert_called_once()

    def test_requires_consent_before_mutation(self):
        with self.assertRaises(ValueError):
            save_settings(self.root, {**self.payload, 'consent': False}, self.read, self.write)
        self.write.assert_not_called()
        self.assertFalse((self.root / 'ai-service.json').exists())

    def test_rejects_remote_http_and_credentials_in_url(self):
        for endpoint in ('http://example.invalid', 'https://user:pass@example.invalid', 'https://example.invalid:broken'):
            with self.assertRaises(ValueError):
                save_settings(self.root, {**self.payload, 'endpoint': endpoint}, self.read, self.write)
        self.write.assert_not_called()

    def test_failure_keeps_old_config(self):
        path = self.root / 'ai-service.json'
        path.write_text('{"enabled":false}')
        self.write.side_effect = ValueError('Credential Manager failed')
        with self.assertRaises(ValueError):
            save_settings(self.root, self.payload, self.read, self.write)
        self.assertEqual(path.read_text(), '{"enabled":false}')

    def test_blank_key_only_reuses_matching_host(self):
        with self.assertRaises(ValueError):
            save_settings(self.root, {**self.payload, 'secret': ''}, self.read, self.write)
        self.read.return_value = 'existing-test-key'
        result = save_settings(self.root, {**self.payload, 'secret': ''}, self.read, self.write)
        self.assertTrue(result['saved'])
        self.write.assert_not_called()

    def test_read_does_not_return_key_or_unknown_properties(self):
        (self.root / 'ai-service.json').write_text(json.dumps({**self.payload, 'enabled': True}))
        self.read.return_value = 'private-test-key'
        result = public_settings(self.root, self.read)
        self.assertTrue(result['hasKey'])
        self.assertNotIn('secret', result)
        self.assertNotIn('private-test-key', json.dumps(result))
