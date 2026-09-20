import unittest
from pathlib import Path
from platform_paths import data_directory


class PlatformPathTests(unittest.TestCase):
    def test_mac_location_unchanged(self):
        self.assertEqual(data_directory('darwin', {}, '/home/test'), Path('/home/test/Library/Application Support/Trainer'))

    def test_windows_local_app_data(self):
        self.assertEqual(data_directory('win32', {'LOCALAPPDATA': '/local'}, '/home/test'), Path('/local/Trainer'))

    def test_windows_fallback(self):
        self.assertEqual(data_directory('win32', {}, '/home/test'), Path('/home/test/AppData/Local/Trainer'))

    def test_linux(self):
        self.assertEqual(data_directory('linux', {'XDG_DATA_HOME': '/data'}, '/home/test'), Path('/data/Trainer'))

    def test_explicit_override(self):
        for platform in ('win32', 'darwin', 'linux'):
            self.assertEqual(data_directory(platform, {'TRAINER_DATA_DIR': '/isolated'}, '/home/test'), Path('/isolated'))
