import subprocess
import unittest
from unittest.mock import patch
import system_credentials as credentials


class CredentialTests(unittest.TestCase):
    def test_isolated_mode_never_reads_system_store(self):
        with patch.dict(credentials.os.environ, TRAINER_DESKTOP_ISOLATED='1'), patch.object(credentials, 'windows_api') as api, patch.object(credentials.subprocess, 'run') as run:
            self.assertEqual(credentials.read_secret('com.trainer.github', 'oauth'), '')
            api.assert_not_called()
            run.assert_not_called()

    def test_known_service(self):
        self.assertEqual(credentials.validate('com.trainer.github', 'oauth'), 'Trainer/com.trainer.github/oauth')

    def test_host_scoped_service(self):
        self.assertIn('trainer-ai-', credentials.validate('trainer-ai-' + 'a' * 64, 'Trainer'))

    def test_reject_other_apps_and_accounts(self):
        for service, account in [('other', 'Trainer'), ('com.trainer.github', 'Trainer'), ('trainer-ai-x', 'Trainer')]:
            with self.assertRaises(ValueError): credentials.validate(service, account)

    def test_windows_dispatch(self):
        with patch.object(credentials.sys, 'platform', 'win32'), patch.object(credentials, 'read_windows', return_value='test-only') as read:
            self.assertEqual(credentials.read_secret('com.trainer.github', 'oauth'), 'test-only')
            read.assert_called_once_with('com.trainer.github', 'oauth')

    def test_mac_keeps_existing_keychain(self):
        with patch.object(credentials.sys, 'platform', 'darwin'), patch.object(credentials.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'test-only\n')) as run:
            self.assertEqual(credentials.read_secret('com.trainer.github', 'oauth'), 'test-only')
            self.assertIn('/usr/bin/security', run.call_args.args[0])

    def test_unsupported_has_no_file_fallback(self):
        with patch.object(credentials.sys, 'platform', 'linux'):
            self.assertEqual(credentials.read_secret('com.trainer.github', 'oauth'), '')

    def test_invalid_values_never_call_native_api(self):
        with patch.object(credentials, 'windows_api') as api:
            for value in ('', '\x00', 'a' * 2561):
                with self.assertRaises(ValueError): credentials.write_windows('trainer-openai-api-key', 'Trainer', value)
            api.assert_not_called()
