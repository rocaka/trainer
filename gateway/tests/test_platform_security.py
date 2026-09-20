import unittest
from unittest.mock import patch
import platform_security


class PlatformSecurityTests(unittest.TestCase):
    def test_windows_fails_closed(self):
        with patch.object(platform_security.os, 'name', 'nt'):
            self.assertFalse(platform_security.supports_secure_submission())
            with self.assertRaisesRegex(ValueError, '代码提交已禁用'):
                platform_security.require_secure_submission()

    def test_missing_directory_handle_support_fails_closed(self):
        with patch.object(platform_security.os, 'supports_dir_fd', set()):
            self.assertFalse(platform_security.supports_secure_submission())
